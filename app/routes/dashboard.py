from flask import Blueprint, render_template, request, redirect, url_for, session
from app import db
from app.models import JournalEntry, Account, Budget, Category
from datetime import datetime, timedelta
import json
from app.utils import get_account_tree

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard', methods=['GET', 'POST'])
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
        period = request.args.get('period')
        if period == 'ytd':
            start_date = today.replace(month=1, day=1)
        elif period == 'current_month':
            start_date = today.replace(day=1)
        elif period == 'last_3_months':
            start_date = today - timedelta(days=90)
        else: # Default to last 6 months
            start_date = today - timedelta(days=180)

    # Monthly data for bar chart
    income_by_month_query = db.session.query(
        db.func.strftime('%Y-%m', JournalEntry.date).label('month'),
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.credit_account_id == Account.id).filter(
        Account.type.in_(['Revenue', 'Income']),
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date,
        JournalEntry.date <= end_date
    ).group_by('month')

    expense_by_month_query = db.session.query(
        db.func.strftime('%Y-%m', JournalEntry.date).label('month'),
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date,
        JournalEntry.date <= end_date
    ).group_by('month')

    income_by_month = {r.month: r.total for r in income_by_month_query.all()}
    expense_by_month = {r.month: r.total for r in expense_by_month_query.all()}

    all_months = sorted(list(set(income_by_month.keys()) | set(expense_by_month.keys())))

    bar_chart_labels = json.dumps(all_months)
    bar_chart_income = json.dumps([income_by_month.get(m, 0) for m in all_months])
    bar_chart_expense = json.dumps([expense_by_month.get(m, 0) for m in all_months])

    # Expense breakdown for the selected period for the pie chart
    expense_breakdown_query = db.session.query(
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date,
        JournalEntry.date <= end_date,
        JournalEntry.category != None,
        JournalEntry.category != ''
    ).group_by(JournalEntry.category)

    expense_breakdown = expense_breakdown_query.all()

    pie_chart_labels = json.dumps([item.category for item in expense_breakdown])
    pie_chart_data = json.dumps([item.total for item in expense_breakdown])

    # Income breakdown for the selected period for the pie chart
    income_breakdown_query = db.session.query(
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.credit_account_id == Account.id).filter(
        Account.type.in_(['Revenue', 'Income']),
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date,
        JournalEntry.date <= end_date,
        JournalEntry.category != None,
        JournalEntry.category != ''
    ).group_by(JournalEntry.category)

    income_breakdown = income_breakdown_query.all()

    income_pie_chart_labels = json.dumps([item.category for item in income_breakdown])
    income_pie_chart_data = json.dumps([item.total for item in income_breakdown])

    # KPIs for the selected period
    revenue_accounts = Account.query.filter_by(client_id=session['client_id'], type='Revenue', parent_id=None).all()
    revenue_data = get_account_tree(revenue_accounts, start_date, end_date)
    income_this_period = sum(item['balance'] for item in revenue_data)
    
    expense_accounts = Account.query.filter_by(client_id=session['client_id'], type='Expense', parent_id=None).all()
    expense_data = get_account_tree(expense_accounts, start_date, end_date)
    expenses_this_period = sum(item['balance'] for item in expense_data)

    m_income = income_this_period
    m_expenses = abs(expenses_this_period)
    net_profit = m_income - m_expenses

    # Account summaries (these are not date-filtered in the original, so keep as is)
    asset_accounts = Account.query.filter_by(type='Asset', client_id=session['client_id']).all()
    liability_accounts = Account.query.filter_by(type='Liability', client_id=session['client_id']).all()

    asset_balances = {}
    for account in asset_accounts:
        debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id == account.id).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id == account.id).scalar() or 0
        asset_balances[account.name] = account.opening_balance + debits - credits

    liability_balances = {}
    for account in liability_accounts:
        debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id == account.id).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id == account.id).scalar() or 0
        liability_balances[account.name] = account.opening_balance + credits - debits

    # Budget performance data
    def get_all_descendants(budget):
        descendants = []
        for child in budget.children:
            descendants.append(child)
            descendants.extend(get_all_descendants(child))
        return descendants

    budgets = Budget.query.filter_by(client_id=session['client_id'], parent_id=None).all()
    performance_data = []
    for budget in budgets:
        all_budgets_in_tree = get_all_descendants(budget)
        total_budgeted = budget.amount + sum(b.amount for b in all_budgets_in_tree)

        history = []
        today = datetime.now().date()
        current_date = budget.start_date

        while current_date <= today:
            if budget.period == 'monthly':
                period_start = current_date.replace(day=1)
                next_month = current_date.replace(day=28) + timedelta(days=4)
                period_end = next_month - timedelta(days=next_month.day)
                period_name = period_start.strftime("%B %Y")
                current_date = period_end + timedelta(days=1)
            elif budget.period == 'quarterly':
                quarter = (current_date.month - 1) // 3 + 1
                period_start = datetime(current_date.year, 3 * quarter - 2, 1).date()
                period_end = (datetime(current_date.year, 3 * quarter % 12 + 1, 1) - timedelta(days=1)).date()
                period_name = f"Q{quarter} {period_start.year}"
                current_date = period_end + timedelta(days=1)
            else: # yearly
                period_start = datetime(current_date.year, 1, 1).date()
                period_end = datetime(current_date.year, 12, 31).date()
                period_name = str(period_start.year)
                current_date = period_end + timedelta(days=1)

            all_categories = []
            all_keywords = []
            for b in all_budgets_in_tree:
                for c in b.categories:
                    all_categories.append(c.name)
                if b.keywords:
                    all_keywords.extend([k.strip() for k in b.keywords.split(',')])

            actual_spent = 0
            if all_categories or all_keywords:
                base_filters = [
                    JournalEntry.client_id == session['client_id'],
                    JournalEntry.date >= period_start,
                    JournalEntry.date <= period_end,
                    Account.type == 'Expense' # This filter should always apply
                ]

                category_conditions = []
                if all_categories:
                    category_conditions.append(JournalEntry.category.in_(all_categories))

                keyword_conditions = []
                if all_keywords:
                    keyword_conditions.append(db.or_(*[JournalEntry.description.ilike(f'%{kw}%') for kw in all_keywords]))

                # Combine category and keyword conditions with OR
                combined_conditions = []
                if category_conditions:
                    combined_conditions.append(db.or_(*category_conditions))
                if keyword_conditions:
                    combined_conditions.append(db.or_(*keyword_conditions))

                final_filters = base_filters
                if combined_conditions:
                    final_filters.append(db.or_(*combined_conditions))

                actual_spent = db.session.query(db.func.sum(JournalEntry.amount)) \
                    .join(Account, JournalEntry.debit_account_id == Account.id) \
                    .filter(*final_filters).scalar() or 0

            history.append({
                'period_name': period_name,
                'budgeted': total_budgeted,
                'actual': actual_spent,
                'difference': total_budgeted - actual_spent
            })

        performance_data.append({
            'name': budget.name,
            'period': budget.period,
            'amount': total_budgeted,
            'history': history
        })

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
                           performance_data=performance_data)
