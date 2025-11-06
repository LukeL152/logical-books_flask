from flask import Blueprint, render_template, request, redirect, url_for, session
from app import db
from app.models import JournalEntries, Account, Budget
from datetime import datetime, timedelta
import json
from dateutil.relativedelta import relativedelta
from app.utils import get_account_tree, get_budgets_actual_spent, get_num_periods

dashboard_bp = Blueprint('dashboard', __name__)

def get_performance_data_recursive(budget, start_date, end_date):
    performance_data = []
    all_budgets_for_summary = []

    # Get performance data for the current budget
    num_periods = get_num_periods(start_date, end_date, budget.period)
    total_budgeted = budget.total_budgeted * num_periods
    
    actual_spendings = get_budgets_actual_spent([budget.id], start_date, end_date)
    actual_spent = actual_spendings.get(budget.id, {'actual_spent': 0.0})['actual_spent']
    difference = total_budgeted - actual_spent

    num_days = (end_date - start_date).days + 1
    num_months = get_num_periods(start_date, end_date, 'monthly')

    avg_daily_spent = actual_spent / num_days if num_days > 0 else 0
    avg_monthly_spent = actual_spent / num_months if num_months > 0 else 0
    
    all_budgets_for_summary.append({
        'name': budget.name,
        'budgeted': total_budgeted,
        'actual': actual_spent,
        'difference': difference,
        'id': budget.id
    })
    
    history = []
    
    # Calculate the number of periods based on the dashboard's date range
    num_periods_to_display = get_num_periods(start_date, end_date, budget.period)

    # Iterate backwards from the dashboard's end_date
    current_end_of_period = end_date
    for i in range(num_periods_to_display):
        if budget.period == 'monthly':
            period_start = current_end_of_period.replace(day=1)
            period_end = current_end_of_period
            period_name = period_start.strftime("%B %Y")
            current_end_of_period = period_start - timedelta(days=1) # Move to end of previous month
        elif budget.period == 'quarterly':
            # Calculate start and end of current quarter
            current_quarter_start_month = (current_end_of_period.month - 1) // 3 * 3 + 1
            period_start = current_end_of_period.replace(month=current_quarter_start_month, day=1)
            period_end = (period_start + relativedelta(months=3)) - timedelta(days=1)
            period_name = f"Q{(current_quarter_start_month - 1) // 3 + 1} {current_end_of_period.year}"
            current_end_of_period = period_start - timedelta(days=1) # Move to end of previous quarter
        else: # yearly
            period_start = current_end_of_period.replace(month=1, day=1)
            period_end = current_end_of_period.replace(month=12, day=31)
            period_name = str(current_end_of_period.year)
            current_end_of_period = period_start - timedelta(days=1) # Move to end of previous year

        # Ensure the period is within the dashboard's overall start_date and end_date
        effective_period_start = max(period_start, start_date)
        effective_period_end = min(period_end, end_date)

        if budget.is_miscellaneous:
            total_expenses = db.session.query(db.func.sum(JournalEntries.amount)).join(Account, JournalEntries.debit_account_id == Account.id).filter(
                Account.type == 'Expense',
                JournalEntries.client_id == budget.client_id,
                JournalEntries.date >= effective_period_start,
                JournalEntries.date <= effective_period_end
            ).scalar() or 0

            non_misc_budgets = Budget.query.filter(Budget.client_id == budget.client_id, Budget.is_miscellaneous == False).all()
            non_misc_budget_ids = [b.id for b in non_misc_budgets]
            non_misc_actual_spendings = get_budgets_actual_spent(non_misc_budget_ids, effective_period_start, effective_period_end)
            total_non_misc_spent = sum(s['actual_spent'] for s in non_misc_actual_spendings.values())

            hist_actual_spent = total_expenses - total_non_misc_spent
        else:
            hist_actual_spendings = get_budgets_actual_spent([budget.id], effective_period_start, effective_period_end)
            hist_actual_spent = hist_actual_spendings.get(budget.id, {'actual_spent': 0.0})['actual_spent']

        history.append({
            'period_name': period_name,
            'budgeted': budget.total_budgeted,
            'actual': hist_actual_spent,
            'difference': budget.total_budgeted - hist_actual_spent
        })
    history.reverse()

    performance_data.append({
        'id': budget.id,
        'name': budget.name,
        'period': budget.period,
        'amount': budget.amount,  # This is the original 'amount'
        'budgeted': total_budgeted,  # Use total_budgeted
        'actual': actual_spent,  # Add this
        'difference': total_budgeted - actual_spent,  # Use total_budgeted
        'avg_daily_spent': avg_daily_spent,
        'avg_monthly_spent': avg_monthly_spent,
        'history': history,
        'level': 0, # This will be updated later
        'parent_id': budget.parent_id,
        'has_children': bool(budget.children.first())
    })
    
    for child in budget.children:
        child_performance_data, child_summary_data = get_performance_data_recursive(child, start_date, end_date)
        performance_data.extend(child_performance_data)
        all_budgets_for_summary.extend(child_summary_data)
        
    return performance_data, all_budgets_for_summary

@dashboard_bp.route('/', methods=['GET', 'POST'])
def dashboard():
    client_id = session.get('client_id')
    if not client_id:
        return redirect(url_for('clients.clients'))

    today = datetime.now().date()
    start_date = None
    end_date = today

    if request.method == 'POST':
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
    else:
        period = request.args.get('period', 'ytd') # Default to ytd
        if period == 'current_month':
            start_date = today.replace(day=1)
        elif period == 'last_3_months':
            start_date = today - timedelta(days=90)
        elif period == 'last_6_months':
            start_date = today - timedelta(days=180)
        else: # Default to ytd
            start_date = today.replace(month=1, day=1)

    # Monthly data for bar chart
    income_by_month_query = db.session.query(
        db.func.strftime('%Y-%m', JournalEntries.date).label('month'),
        db.func.sum(JournalEntries.amount).label('total')
    ).join(Account, JournalEntries.credit_account_id == Account.id).filter(
        Account.type.in_(['Revenue', 'Income']),
        JournalEntries.client_id == session['client_id'],
        JournalEntries.date >= start_date,
        JournalEntries.date <= end_date
    ).group_by('month')

    expense_by_month_query = db.session.query(
        db.func.strftime('%Y-%m', JournalEntries.date).label('month'),
        db.func.sum(JournalEntries.amount).label('total')
    ).join(Account, JournalEntries.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntries.client_id == session['client_id'],
        JournalEntries.date >= start_date,
        JournalEntries.date <= end_date
    ).group_by('month')

    income_by_month = {r.month: r.total for r in income_by_month_query.all()}
    expense_by_month = {r.month: r.total for r in expense_by_month_query.all()}

    all_months = sorted(list(set(income_by_month.keys()) | set(expense_by_month.keys())))

    bar_chart_labels = json.dumps(all_months)
    bar_chart_income = json.dumps([income_by_month.get(m, 0) for m in all_months])
    bar_chart_expense = json.dumps([expense_by_month.get(m, 0) for m in all_months])

    # Expense breakdown for the selected period for the pie chart
    expense_breakdown_query = db.session.query(
        JournalEntries.category,
        db.func.sum(JournalEntries.amount).label('total')
    ).join(Account, JournalEntries.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntries.client_id == session['client_id'],
        JournalEntries.date >= start_date,
        JournalEntries.date <= end_date,
        JournalEntries.category != None,
        JournalEntries.category != ''
    ).group_by(JournalEntries.category)

    expense_breakdown = expense_breakdown_query.all()

    pie_chart_labels = json.dumps([item.category for item in expense_breakdown])
    pie_chart_data = json.dumps([item.total for item in expense_breakdown])

    # Income breakdown for the selected period for the pie chart
    income_breakdown_query = db.session.query(
        JournalEntries.category,
        db.func.sum(JournalEntries.amount).label('total')
    ).join(Account, JournalEntries.credit_account_id == Account.id).filter(
        Account.type.in_(['Revenue', 'Income']),
        JournalEntries.client_id == session['client_id'],
        JournalEntries.date >= start_date,
        JournalEntries.date <= end_date,
        JournalEntries.category != None,
        JournalEntries.category != ''
    ).group_by(JournalEntries.category)

    income_breakdown = income_breakdown_query.all()

    income_pie_chart_labels = json.dumps([item.category for item in income_breakdown])
    income_pie_chart_data = json.dumps([item.total for item in income_breakdown])

    # KPIs for the selected period
    income_this_period = db.session.query(db.func.sum(JournalEntries.amount)).join(Account, JournalEntries.credit_account_id == Account.id).filter(
        Account.type.in_(['Revenue', 'Income']),
        JournalEntries.client_id == session['client_id'],
        JournalEntries.date >= start_date,
        JournalEntries.date <= end_date
    ).scalar() or 0
    
    expenses_this_period = db.session.query(db.func.sum(JournalEntries.amount)).join(Account, JournalEntries.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntries.client_id == session['client_id'],
        JournalEntries.date >= start_date,
        JournalEntries.date <= end_date
    ).scalar() or 0

    m_income = income_this_period
    m_expenses = abs(expenses_this_period)
    net_profit = m_income - m_expenses

    # Calculate average KPIs
    num_days = (end_date - start_date).days + 1
    num_months = get_num_periods(start_date, end_date, 'monthly')

    avg_daily_income = m_income / num_days if num_days > 0 else 0
    avg_monthly_income = m_income / num_months if num_months > 0 else 0

    avg_daily_expense = m_expenses / num_days if num_days > 0 else 0
    avg_monthly_expense = m_expenses / num_months if num_months > 0 else 0

    avg_daily_net_income = net_profit / num_days if num_days > 0 else 0
    avg_monthly_net_income = net_profit / num_months if num_months > 0 else 0

    # Account summaries (these are not date-filtered in the original, so keep as is)
    asset_accounts = Account.query.filter_by(type='Asset', client_id=session['client_id']).all()
    liability_accounts = Account.query.filter_by(type='Liability', client_id=session['client_id']).all()

    asset_balances = {}
    for account in asset_accounts:
        debits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.debit_account_id == account.id).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.credit_account_id == account.id).scalar() or 0
        asset_balances[account.name] = account.opening_balance + debits - credits

    liability_balances = {}
    for account in liability_accounts:
        debits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.debit_account_id == account.id).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.credit_account_id == account.id).scalar() or 0
        liability_balances[account.name] = account.opening_balance + credits - debits

    # Budget performance data
    budgets = Budget.query.filter_by(client_id=session['client_id'], parent_id=None).all()
    performance_data = []
    all_budgets_for_summary = []
    misc_budget = None
    non_misc_budgets = []
    for budget in budgets:
        if budget.is_miscellaneous:
            misc_budget = budget
        else:
            non_misc_budgets.append(budget)

    for budget in budgets:
        child_performance_data, child_summary_data = get_performance_data_recursive(budget, start_date, end_date)
        performance_data.extend(child_performance_data)
        all_budgets_for_summary.extend(child_summary_data)

    if misc_budget:
        non_misc_budget_ids = [b.id for b in non_misc_budgets]
        non_misc_actual_spendings = get_budgets_actual_spent(non_misc_budget_ids, start_date, end_date)
        total_non_misc_spent = sum(s['actual_spent'] for s in non_misc_actual_spendings.values())
        misc_actual_spent = m_expenses - total_non_misc_spent

        for p_data in performance_data:
            if p_data['id'] == misc_budget.id:
                p_data['actual'] = misc_actual_spent
                p_data['difference'] = p_data['budgeted'] - misc_actual_spent
                p_data['avg_daily_spent'] = misc_actual_spent / ((end_date - start_date).days + 1) if (end_date - start_date).days + 1 > 0 else 0
                p_data['avg_monthly_spent'] = misc_actual_spent / get_num_periods(start_date, end_date, 'monthly') if get_num_periods(start_date, end_date, 'monthly') > 0 else 0



    # Remove duplicates from all_budgets_for_summary
    all_budgets_for_summary = [dict(t) for t in {tuple(d.items()) for d in all_budgets_for_summary}]

    # Calculate Overall Budget Health
    all_transaction_ids = set()
    for b in all_budgets_for_summary:
        budget_spendings = get_budgets_actual_spent([b['id']], start_date, end_date)
        all_transaction_ids.update(budget_spendings.get(b['id'], {'transaction_ids': set()})['transaction_ids'])

    overall_budgeted = sum(b['budgeted'] for b in all_budgets_for_summary)
    overall_actual = m_expenses
    overall_difference = overall_budgeted - overall_actual


    return render_template('dashboard.html', 
                           m_income=m_income, 
                           m_expenses=m_expenses, 
                           net_profit=net_profit, 
                           expense_breakdown=expense_breakdown, 
                           asset_balances=asset_balances, 
                           liability_balances=liability_balances,
                           bar_chart_labels=bar_chart_labels,
                           bar_chart_income=bar_chart_income,
                           bar_chart_expense=bar_chart_expense,
                           pie_chart_labels=pie_chart_labels,
                           pie_chart_data=pie_chart_data,
                           income_pie_chart_labels=income_pie_chart_labels,
                           income_pie_chart_data=income_pie_chart_data,
                           start_date=start_date.strftime('%Y-%m-%d'),
                           end_date=end_date.strftime('%Y-%m-%d'),
                           performance_data=performance_data,
                           overall_budgeted=overall_budgeted,
                           overall_actual=overall_actual,
                           overall_difference=overall_difference,

                           avg_daily_income=avg_daily_income,
                           avg_monthly_income=avg_monthly_income,
                           avg_daily_expense=avg_daily_expense,
                           avg_monthly_expense=avg_monthly_expense,
                           avg_daily_net_income=avg_daily_net_income,
                           avg_monthly_net_income=avg_monthly_net_income)
