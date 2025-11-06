from flask import Blueprint, render_template, request, session, make_response, redirect, url_for, flash, jsonify
from app import db
from app.models import Account, JournalEntries, Reconciliation, Budget, AuditTrail, Transaction, Category
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import csv
import io
import json
from app.utils import get_account_tree, get_budgets_actual_spent, get_num_periods, get_miscellaneous_historical_performance, get_miscellaneous_spending_breakdown

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/ledger')
def ledger():
    accounts = Account.query.filter_by(client_id=session['client_id'], parent_id=None).order_by(Account.name).all()
    ledger_data = get_account_tree(accounts)
    return render_template('ledger.html', ledger_data=ledger_data)

@reports_bp.route('/income_statement')
def income_statement():
    revenue_accounts = Account.query.filter_by(client_id=session['client_id'], type='Revenue', parent_id=None).all()
    expense_accounts = Account.query.filter_by(client_id=session['client_id'], type='Expense', parent_id=None).all()

    revenue_data = get_account_tree(revenue_accounts)
    expense_data = get_account_tree(expense_accounts)

    total_revenue = sum(item['balance'] for item in revenue_data)
    total_expenses = sum(item['balance'] for item in expense_data)
    net_income = total_revenue - total_expenses

    return render_template('income_statement.html', 
                           revenue_data=revenue_data, 
                           expense_data=expense_data, 
                           total_revenue=total_revenue, 
                           total_expenses=total_expenses, 
                           net_income=net_income)

@reports_bp.route('/balance_sheet')
def balance_sheet():
    asset_accounts = Account.query.filter(Account.type.in_(['Asset', 'Accounts Receivable', 'Inventory', 'Fixed Asset', 'Accumulated Depreciation'])).filter_by(client_id=session['client_id'], parent_id=None).all()
    liability_accounts = Account.query.filter(Account.type.in_(['Liability', 'Accounts Payable', 'Long-Term Debt'])).filter_by(client_id=session['client_id'], parent_id=None).all()
    equity_accounts = Account.query.filter_by(client_id=session['client_id'], type='Equity', parent_id=None).all()

    asset_data = get_account_tree(asset_accounts)
    liability_data = get_account_tree(liability_accounts)
    equity_data = get_account_tree(equity_accounts)

    total_assets = sum(item['balance'] for item in asset_data)
    total_liabilities = sum(item['balance'] for item in liability_data)
    total_equity_from_accounts = sum(item['balance'] for item in equity_data)

    # Calculate Net Income to be added to Equity
    revenue_accounts = Account.query.filter_by(client_id=session['client_id'], type='Revenue', parent_id=None).all()
    expense_accounts = Account.query.filter_by(client_id=session['client_id'], type='Expense', parent_id=None).all()

    revenue_data = get_account_tree(revenue_accounts)
    expense_data = get_account_tree(expense_accounts)

    total_revenue = sum(item['balance'] for item in revenue_data)
    total_expenses = sum(item['balance'] for item in expense_data)
    net_income = total_revenue - total_expenses

    # Correct total equity includes net income
    total_equity = total_equity_from_accounts + net_income

    # Check if books are balanced
    is_balanced = round(total_assets, 2) == round(total_liabilities + total_equity, 2)

    return render_template('balance_sheet.html', 
                           asset_data=asset_data, 
                           liability_data=liability_data, 
                           equity_data=equity_data, 
                           total_assets=total_assets, 
                           total_liabilities=total_liabilities, 
                           total_equity=total_equity,
                           is_balanced=is_balanced)

@reports_bp.route('/statement_of_cash_flows')
def statement_of_cash_flows():
    # For simplicity, we'll calculate this for the entire history of the client.
    # A more advanced implementation would allow for date range filtering.

    # Net Income
    revenue = db.session.query(db.func.sum(JournalEntries.amount)).join(Account, JournalEntries.credit_account_id == Account.id).filter(Account.type == 'Revenue', JournalEntries.client_id == session['client_id']).scalar() or 0
    expenses = db.session.query(db.func.sum(JournalEntries.amount)).join(Account, JournalEntries.debit_account_id == Account.id).filter(Account.type == 'Expense', JournalEntries.client_id == session['client_id']).scalar() or 0
    net_income = revenue - expenses

    # Depreciation
    depreciation = 0  # Placeholder

    # Change in Accounts Receivable
    ar_accounts = Account.query.filter_by(type='Accounts Receivable', client_id=session['client_id']).all()
    ar_balance = sum(acc.opening_balance for acc in ar_accounts)
    ar_debits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.debit_account_id.in_([acc.id for acc in ar_accounts])).scalar() or 0
    ar_credits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.credit_account_id.in_([acc.id for acc in ar_accounts])).scalar() or 0
    change_in_accounts_receivable = (ar_balance + ar_debits - ar_credits) - ar_balance

    # Change in Inventory
    inventory_accounts = Account.query.filter_by(type='Inventory', client_id=session['client_id']).all()
    inventory_balance = sum(acc.opening_balance for acc in inventory_accounts)
    inventory_debits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.debit_account_id.in_([acc.id for acc in inventory_accounts])).scalar() or 0
    inventory_credits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.credit_account_id.in_([acc.id for acc in inventory_accounts])).scalar() or 0
    change_in_inventory = (inventory_balance + inventory_debits - inventory_credits) - inventory_balance

    # Change in Accounts Payable
    ap_accounts = Account.query.filter_by(type='Accounts Payable', client_id=session['client_id']).all()
    ap_balance = sum(acc.opening_balance for acc in ap_accounts)
    ap_debits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.debit_account_id.in_([acc.id for acc in ap_accounts])).scalar() or 0
    ap_credits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.credit_account_id.in_([acc.id for acc in ap_accounts])).scalar() or 0
    change_in_accounts_payable = (ap_balance + ap_credits - ap_debits) - ap_balance

    net_cash_from_operating_activities = net_income + depreciation - change_in_accounts_receivable - change_in_inventory + change_in_accounts_payable

    # Investing Activities
    purchase_of_fixed_assets = 0 # Placeholder
    net_cash_from_investing_activities = -purchase_of_fixed_assets

    # Financing Activities
    issuance_of_long_term_debt = 0 # Placeholder
    repayment_of_long_term_debt = 0 # Placeholder
    net_cash_from_financing_activities = issuance_of_long_term_debt - repayment_of_long_term_debt

    # Summary
    net_increase_in_cash = net_cash_from_operating_activities + net_cash_from_investing_activities + net_cash_from_financing_activities
    cash_at_beginning_of_period = db.session.query(db.func.sum(Account.opening_balance)).filter(Account.type == 'Asset', Account.name.ilike('%cash%')).scalar() or 0
    cash_at_end_of_period = cash_at_beginning_of_period + net_increase_in_cash

    return render_template('statement_of_cash_flows.html', 
                           net_income=net_income,
                           depreciation=depreciation,
                           change_in_accounts_receivable=change_in_accounts_receivable,
                           change_in_inventory=change_in_inventory,
                           change_in_accounts_payable=change_in_accounts_payable,
                           net_cash_from_operating_activities=net_cash_from_operating_activities,
                           purchase_of_fixed_assets=purchase_of_fixed_assets,
                           net_cash_from_investing_activities=net_cash_from_investing_activities,
                           issuance_of_long_term_debt=issuance_of_long_term_debt,
                           repayment_of_long_term_debt=repayment_of_long_term_debt,
                           net_cash_from_financing_activities=net_cash_from_financing_activities,
                           net_increase_in_cash=net_increase_in_cash,
                           cash_at_beginning_of_period=cash_at_beginning_of_period,
                           cash_at_end_of_period=cash_at_end_of_period
                           )

@reports_bp.route('/analysis', methods=['GET', 'POST'])
def analysis():
    client_id = session.get('client_id')
    if not client_id:
        return redirect(url_for('clients.clients'))

    today = datetime.now().date()
    
    # Default date ranges for comparison
    start_date_1 = today.replace(month=1, day=1) # YTD
    end_date_1 = today
    start_date_2 = (today.replace(month=1, day=1) - timedelta(days=1)).replace(month=1, day=1) # Previous YTD
    end_date_2 = (today.replace(month=1, day=1) - timedelta(days=1))

    if request.method == 'POST':
        start_date_1 = datetime.strptime(request.form['start_date_1'], '%Y-%m-%d').date()
        end_date_1 = datetime.strptime(request.form['end_date_1'], '%Y-%m-%d').date()
        start_date_2 = datetime.strptime(request.form['start_date_2'], '%Y-%m-%d').date()
        end_date_2 = datetime.strptime(request.form['end_date_2'], '%Y-%m-%d').date()

    # --- Spending by Category (Period 1) ---
    spending_by_category_query = db.session.query(
        JournalEntries.category,
        db.func.sum(JournalEntries.amount).label('total')
    ).join(Account, JournalEntries.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntries.client_id == client_id,
        JournalEntries.date >= start_date_1,
        JournalEntries.date <= end_date_1,
        JournalEntries.category != None,
        JournalEntries.category != ''
    ).group_by(JournalEntries.category).order_by(db.func.sum(JournalEntries.amount).desc())

    spending_by_category = spending_by_category_query.all()
    category_labels = json.dumps([item.category for item in spending_by_category])
    category_data = json.dumps([item.total for item in spending_by_category])

    # --- Income by Category (Period 1) ---
    income_by_category_query = db.session.query(
        JournalEntries.category,
        db.func.sum(JournalEntries.amount).label('total')
    ).join(Account, JournalEntries.credit_account_id == Account.id).filter(
        Account.type == 'Revenue',
        JournalEntries.client_id == client_id,
        JournalEntries.date >= start_date_1,
        JournalEntries.date <= end_date_1,
        JournalEntries.category != None,
        JournalEntries.category != ''
    ).group_by(JournalEntries.category).order_by(db.func.sum(JournalEntries.amount).desc())

    income_by_category = income_by_category_query.all()
    income_category_labels = json.dumps([item.category for item in income_by_category])
    income_category_data = json.dumps([float(item.total) for item in income_by_category])

    # --- Category Comparison ---
    # For simplicity, we'll just use the top 5 categories from Period 1 for comparison
    top_categories = [item.category for item in spending_by_category[:5]]

    category_comparison_data_1 = []
    category_comparison_data_2 = []

    for category in top_categories:
        total_1 = db.session.query(db.func.sum(JournalEntries.amount)).join(Account, JournalEntries.debit_account_id == Account.id).filter(
            Account.type == 'Expense',
            JournalEntries.client_id == client_id,
            JournalEntries.date >= start_date_1,
            JournalEntries.date <= end_date_1,
            JournalEntries.category == category
        ).scalar() or 0
        category_comparison_data_1.append(total_1)

        total_2 = db.session.query(db.func.sum(JournalEntries.amount)).join(Account, JournalEntries.debit_account_id == Account.id).filter(
            Account.type == 'Expense',
            JournalEntries.client_id == client_id,
            JournalEntries.date >= start_date_2,
            JournalEntries.date <= end_date_2,
            JournalEntries.category == category
        ).scalar() or 0
        category_comparison_data_2.append(total_2)

    category_comparison_labels = json.dumps(top_categories)
    category_comparison_data_1 = json.dumps(category_comparison_data_1)
    category_comparison_data_2 = json.dumps(category_comparison_data_2)

    # --- Income vs. Expense ---
    # Monthly data for line chart (similar to dashboard)
    income_by_month_query = db.session.query(
        db.func.strftime('%Y-%m', JournalEntries.date).label('month'),
        db.func.sum(JournalEntries.amount).label('total')
    ).join(Account, JournalEntries.credit_account_id == Account.id).filter(
        Account.type.in_(['Revenue', 'Income']),
        JournalEntries.client_id == client_id,
        JournalEntries.date >= start_date_1, # Using Period 1 for this chart
        JournalEntries.date <= end_date_1
    ).group_by('month')

    expense_by_month_query = db.session.query(
        db.func.strftime('%Y-%m', JournalEntries.date).label('month'),
        db.func.sum(JournalEntries.amount).label('total')
    ).join(Account, JournalEntries.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntries.client_id == client_id,
        JournalEntries.date >= start_date_1, # Using Period 1 for this chart
        JournalEntries.date <= end_date_1
    ).group_by('month')

    income_by_month = {r.month: r.total for r in income_by_month_query.all()}
    expense_by_month = {r.month: r.total for r in expense_by_month_query.all()}

    all_months = sorted(list(set(income_by_month.keys()) | set(expense_by_month.keys())))

    income_trend_data = json.dumps([income_by_month.get(m, 0) for m in all_months])
    expense_trend_data = json.dumps([expense_by_month.get(m, 0) for m in all_months])
    all_months_json = json.dumps(all_months) # Renamed to avoid conflict with template variable

    # --- Cash Flow Statement (using Period 1 for now) ---
    # Net Income
    revenue = db.session.query(db.func.sum(JournalEntries.amount)).join(Account, JournalEntries.credit_account_id == Account.id).filter(Account.type.in_(['Revenue', 'Income']), JournalEntries.client_id == client_id, JournalEntries.date >= start_date_1, JournalEntries.date <= end_date_1).scalar() or 0
    expenses = db.session.query(db.func.sum(JournalEntries.amount)).join(Account, JournalEntries.debit_account_id == Account.id).filter(Account.type == 'Expense', JournalEntries.client_id == client_id, JournalEntries.date >= start_date_1, JournalEntries.date <= end_date_1).scalar() or 0
    net_income = revenue - expenses

    # Depreciation (Placeholder)
    depreciation = 0

    # Change in Accounts Receivable
    ar_accounts = Account.query.filter_by(type='Accounts Receivable', client_id=client_id).all()
    ar_balance_start = sum(db.session.query(db.func.sum(JournalEntries.amount)).filter(db.or_(JournalEntries.debit_account_id == acc.id, JournalEntries.credit_account_id == acc.id), JournalEntries.client_id == client_id, JournalEntries.date < start_date_1).scalar() or 0 for acc in ar_accounts)
    ar_balance_end = sum(db.session.query(db.func.sum(JournalEntries.amount)).filter(db.or_(JournalEntries.debit_account_id == acc.id, JournalEntries.credit_account_id == acc.id), JournalEntries.client_id == client_id, JournalEntries.date <= end_date_1).scalar() or 0 for acc in ar_accounts)
    change_in_accounts_receivable = ar_balance_end - ar_balance_start

    # Change in Inventory
    inventory_accounts = Account.query.filter_by(type='Inventory', client_id=client_id).all()
    inventory_balance_start = sum(db.session.query(db.func.sum(JournalEntries.amount)).filter(db.or_(JournalEntries.debit_account_id == acc.id, JournalEntries.credit_account_id == acc.id), JournalEntries.client_id == client_id, JournalEntries.date < start_date_1).scalar() or 0 for acc in inventory_accounts)
    inventory_balance_end = sum(db.session.query(db.func.sum(JournalEntries.amount)).filter(db.or_(JournalEntries.debit_account_id == acc.id, JournalEntries.credit_account_id == acc.id), JournalEntries.client_id == client_id, JournalEntries.date <= end_date_1).scalar() or 0 for acc in inventory_accounts)
    change_in_inventory = inventory_balance_end - inventory_balance_start

    # Change in Accounts Payable
    ap_accounts = Account.query.filter_by(type='Accounts Payable', client_id=client_id).all()
    ap_balance_start = sum(db.session.query(db.func.sum(JournalEntries.amount)).filter(db.or_(JournalEntries.debit_account_id == acc.id, JournalEntries.credit_account_id == acc.id), JournalEntries.client_id == client_id, JournalEntries.date < start_date_1).scalar() or 0 for acc in ap_accounts)
    ap_balance_end = sum(db.session.query(db.func.sum(JournalEntries.amount)).filter(db.or_(JournalEntries.debit_account_id == acc.id, JournalEntries.credit_account_id == acc.id), JournalEntries.client_id == client_id, JournalEntries.date <= end_date_1).scalar() or 0 for acc in ap_accounts)
    change_in_accounts_payable = ap_balance_end - ap_balance_start

    net_cash_from_operating_activities = net_income + depreciation - change_in_accounts_receivable - change_in_inventory + change_in_accounts_payable

    # Investing Activities (Placeholders)
    purchase_of_fixed_assets = 0
    net_cash_from_investing_activities = -purchase_of_fixed_assets

    # Financing Activities (Placeholders)
    issuance_of_long_term_debt = 0
    repayment_of_long_term_debt = 0
    net_cash_from_financing_activities = issuance_of_long_term_debt - repayment_of_long_term_debt

    # Summary
    net_increase_in_cash = net_cash_from_operating_activities + net_cash_from_investing_activities + net_cash_from_financing_activities
    cash_at_beginning_of_period = db.session.query(db.func.sum(Account.opening_balance)).filter(Account.type == 'Asset', Account.name.ilike('%cash%'), Account.client_id == client_id).scalar() or 0
    cash_at_end_of_period = cash_at_beginning_of_period + net_increase_in_cash

    return render_template('analysis.html',
                           start_date_1=start_date_1.strftime('%Y-%m-%d'),
                           end_date_1=end_date_1.strftime('%Y-%m-%d'),
                           start_date_2=start_date_2.strftime('%Y-%m-%d'),
                           end_date_2=end_date_2.strftime('%Y-%m-%d'),
                           spending_by_category=spending_by_category,
                           category_labels=category_labels,
                           category_data=category_data,
                           income_by_category=income_by_category,
                           income_category_labels=income_category_labels,
                           income_category_data=income_category_data,
                           category_comparison_labels=category_comparison_labels,
                           category_comparison_data_1=category_comparison_data_1,
                           category_comparison_data_2=category_comparison_data_2,
                           all_months=all_months_json,
                           income_trend_data=income_trend_data,
                           expense_trend_data=expense_trend_data,
                           net_income=net_income,
                           depreciation=depreciation,
                           change_in_accounts_receivable=change_in_accounts_receivable,
                           change_in_inventory=change_in_inventory,
                           change_in_accounts_payable=change_in_accounts_payable,
                           net_cash_from_operating_activities=net_cash_from_operating_activities,
                           purchase_of_fixed_assets=purchase_of_fixed_assets,
                           net_cash_from_investing_activities=net_cash_from_investing_activities,
                           issuance_of_long_term_debt=issuance_of_long_term_debt,
                           repayment_of_long_term_debt=repayment_of_long_term_debt,
                           net_cash_from_financing_activities=net_cash_from_financing_activities,
                           net_increase_in_cash=net_increase_in_cash,
                           cash_at_beginning_of_period=cash_at_beginning_of_period,
                           cash_at_end_of_period=cash_at_end_of_period)

@reports_bp.route('/category_transactions/<category_name>')
def category_transactions(category_name):
    transactions = JournalEntries.query.filter_by(client_id=session['client_id'], category=category_name).order_by(JournalEntries.date.desc()).all()
    return render_template('category_transactions.html', transactions=transactions, category_name=category_name)



@reports_bp.route('/budget', methods=['GET', 'POST'])
def budget():
    if request.method == 'POST':
        name = request.form.get('name')
        amount = request.form.get('amount')
        period = request.form.get('period')
        start_date_str = request.form.get('start_date')
        keywords = request.form.get('keywords')
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()

        if period == 'monthly':
            end_date = start_date + relativedelta(months=1) - timedelta(days=1)
        elif period == 'quarterly':
            end_date = start_date + relativedelta(months=3) - timedelta(days=1)
        elif period == 'yearly':
            end_date = start_date + relativedelta(years=1) - timedelta(days=1)
        else:
            end_date = start_date + relativedelta(months=1) - timedelta(days=1)

        is_miscellaneous = request.form.get('is_miscellaneous') == '1'

        if is_miscellaneous:
            existing_misc_budget = Budget.query.filter_by(client_id=session['client_id'], is_miscellaneous=True).first()
            if existing_misc_budget:
                flash('A miscellaneous budget already exists for this client.', 'danger')
                return redirect(url_for('reports.budget'))

        new_budget = Budget(
            name=name,
            amount=amount,
            period=period,
            start_date=start_date,
            end_date=end_date,
            client_id=session['client_id'],
            parent_id=request.form.get('parent_id') if request.form.get('parent_id') else None,
            keywords=keywords,
            is_miscellaneous=is_miscellaneous
        )

        category_names = request.form.getlist('categories')
        for cat_name in category_names:
            category = Category.query.filter_by(name=cat_name, client_id=session['client_id']).first()
            if not category:
                category = Category(name=cat_name, client_id=session['client_id'])
                db.session.add(category)
            new_budget.categories.append(category)

        db.session.add(new_budget)
        db.session.commit()
        return redirect(url_for('reports.budget'))

    def get_budget_level(budget, all_budgets):
        level = 0
        parent = budget.parent
        while parent:
            level += 1
            parent = parent.parent
        return level

    all_budgets = Budget.query.filter_by(client_id=session['client_id']).order_by(Budget.name).all()
    overall_budget = Budget.query.filter_by(client_id=session['client_id'], name='Overall Budget').first()
    other_budgets = Budget.query.filter(Budget.client_id == session['client_id'], Budget.name != 'Overall Budget').order_by(Budget.name).all()

    budget_ids = [b.id for b in all_budgets]
    
    today = datetime.now().date()
    start_date = today.replace(day=1)
    end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)

    actual_spendings = get_budgets_actual_spent(budget_ids, start_date, end_date)

    overall_budget_spent = actual_spendings.get(overall_budget.id, {'actual_spent': 0.0})['actual_spent'] if overall_budget else 0.0
    overall_budget_transaction_ids = actual_spendings.get(overall_budget.id, {'transaction_ids': set()})['transaction_ids'] if overall_budget else set()

    all_other_transaction_ids = set()
    for budget in other_budgets:
        all_other_transaction_ids.update(actual_spendings.get(budget.id, {'transaction_ids': set()})['transaction_ids'])

    other_budgets_spent = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.id.in_(all_other_transaction_ids)).scalar() or 0

    miscellaneous_spending = overall_budget_spent - other_budgets_spent

    budgets_data = []
    if overall_budget:
        budgets_data.append({
            'id': overall_budget.id,
            'name': overall_budget.name,
            'categories': [],
            'period': overall_budget.period,
            'start_date': overall_budget.start_date.isoformat(),
            'amount': overall_budget.amount,
            'actual_spent': overall_budget_spent,
            'remaining': overall_budget.amount - overall_budget_spent if overall_budget.amount else 0,
            'parent_id': None,
            'level': 0,
            'is_parent': True,
            'keywords': overall_budget.keywords
        })

    for budget in other_budgets:
        budget_info = actual_spendings.get(budget.id, {'actual_spent': 0.0, 'transaction_ids': set()})
        actual_spent = budget_info['actual_spent']
        
        budgets_data.append({
            'id': budget.id,
            'name': budget.name,
            'categories': [c.name for c in budget.categories],
            'period': budget.period,
            'start_date': budget.start_date.isoformat(),
            'amount': budget.amount,
            'actual_spent': actual_spent,
            'remaining': budget.amount - actual_spent,
            'parent_id': budget.parent_id,
            'level': get_budget_level(budget, all_budgets),
            'is_parent': bool(budget.children),
            'keywords': budget.keywords
        })



    # Now, let's adjust the parent budget's spending to avoid double-counting
    budgets_by_id = {b['id']: b for b in budgets_data}
    for budget_data in sorted(budgets_data, key=lambda b: b.get('level', 0), reverse=True):
        if budget_data.get('parent_id') and budget_data['parent_id'] in budgets_by_id:
            parent = budgets_by_id[budget_data['parent_id']]
            
            parent_transaction_ids = actual_spendings.get(parent['id'], {'transaction_ids': set()})['transaction_ids']
            child_transaction_ids = actual_spendings.get(budget_data['id'], {'transaction_ids': set()})['transaction_ids']
            
            overlapping_transactions = parent_transaction_ids.intersection(child_transaction_ids)
            
            if overlapping_transactions:
                overlapping_amount = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.id.in_(overlapping_transactions)).scalar() or 0
                parent['actual_spent'] -= overlapping_amount
                if 'remaining' in parent and 'amount' in parent and isinstance(parent['amount'], (int, float)):
                    parent['remaining'] = parent['amount'] - parent['actual_spent']

    all_budgets_for_form = Budget.query.filter_by(client_id=session['client_id']).order_by(Budget.name).all()
    journal_categories = db.session.query(JournalEntries.category).filter(
        JournalEntries.client_id == session['client_id'], 
        JournalEntries.category != None, 
        JournalEntries.category != ''
    ).distinct().all()
    
    existing_categories = Category.query.filter_by(client_id=session['client_id']).all()
    
    category_names = {c[0] for c in journal_categories}
    for cat in existing_categories:
        category_names.add(cat.name)
        
    all_categories = [{'name': name} for name in sorted(list(category_names))]

    return render_template('budget.html', budgets_data=json.dumps(budgets_data), all_budgets=all_budgets_for_form, all_categories=all_categories)

@reports_bp.route('/budget/<int:budget_id>/delete', methods=['POST'])
def delete_budget(budget_id):
    budget = Budget.query.get_or_404(budget_id)
    if budget.client_id != session.get('client_id'):
        flash('You do not have permission to delete this budget.', 'danger')
        return redirect(url_for('reports.budget'))
    db.session.delete(budget)
    db.session.commit()
    flash('Budget deleted successfully.', 'success')
    return redirect(url_for('reports.budget'))

@reports_bp.route('/budget/<int:budget_id>/edit', methods=['GET', 'POST'])
def edit_budget(budget_id):
    budget = Budget.query.get_or_404(budget_id)
    budget.categories_names = [c.name for c in budget.categories]
    if budget.client_id != session.get('client_id'):
        flash('You do not have permission to edit this budget.', 'danger')
        return redirect(url_for('reports.budget'))

    if request.method == 'POST':
        budget.name = request.form.get('name')
        budget.amount = request.form.get('amount')
        budget.period = request.form.get('period')
        budget.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        budget.parent_id = request.form.get('parent_id') if request.form.get('parent_id') else None
        budget.keywords = request.form.get('keywords')
        budget.is_miscellaneous = request.form.get('is_miscellaneous') == '1'

        if budget.is_miscellaneous:
            existing_misc_budget = Budget.query.filter(
                Budget.client_id == session['client_id'],
                Budget.is_miscellaneous == True,
                Budget.id != budget.id
            ).first()
            if existing_misc_budget:
                flash('A miscellaneous budget already exists for this client.', 'danger')
                return redirect(url_for('reports.edit_budget', budget_id=budget.id))
        
        budget.categories.clear()
        category_names = request.form.getlist('categories')
        for cat_name in category_names:
            category = Category.query.filter_by(name=cat_name, client_id=session['client_id']).first()
            if not category:
                category = Category(name=cat_name, client_id=session['client_id'])
                db.session.add(category)
            budget.categories.append(category)

        db.session.commit()
        flash('Budget updated successfully.', 'success')
        return redirect(url_for('reports.budget'))

    all_budgets = Budget.query.filter_by(client_id=session['client_id']).order_by(Budget.name).all()
    journal_categories = db.session.query(JournalEntries.category).filter(
        JournalEntries.client_id == session['client_id'], 
        JournalEntries.category != None, 
        JournalEntries.category != ''
    ).distinct().all()
    
    existing_categories = Category.query.filter_by(client_id=session['client_id']).all()
    
    category_names = {c[0] for c in journal_categories}
    for cat in existing_categories:
        category_names.add(cat.name)
        
    all_categories = [{'name': name} for name in sorted(list(category_names))]
    return render_template('edit_budget.html', budget=budget, all_budgets=all_budgets, all_categories=all_categories)

@reports_bp.route('/budget_analysis/<int:budget_id>', methods=['GET', 'POST'])
def budget_analysis(budget_id):
    budget = Budget.query.get_or_404(budget_id)
    if budget.client_id != session.get('client_id'):
        flash('You do not have permission to view this budget analysis.', 'danger')
        return redirect(url_for('reports.budget'))

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
            end_date = (start_date + relativedelta(months=1)) - timedelta(days=1)
        elif period == 'last_3_months':
            start_date = today - timedelta(days=90)
        elif period == 'last_6_months':
            start_date = today - timedelta(days=180)
        else: # Default to ytd
            start_date = today.replace(month=1, day=1)

    actual_spent = 0.0
    total_budgeted = 0.0
    difference = 0.0
    contributing_transactions = []
    historical_performance = []
    spending_breakdown = []

    if budget.is_miscellaneous:
        num_periods = get_num_periods(start_date, end_date, budget.period)
        total_budgeted = budget.amount * num_periods

        total_expenses = db.session.query(db.func.sum(JournalEntries.amount)).join(Account, JournalEntries.debit_account_id == Account.id).filter(
            Account.type == 'Expense',
            JournalEntries.client_id == session['client_id'],
            JournalEntries.date >= start_date,
            JournalEntries.date <= end_date
        ).scalar() or 0

        non_misc_budgets = Budget.query.filter(Budget.client_id == session['client_id'], Budget.is_miscellaneous == False).all()
        non_misc_budget_ids = [b.id for b in non_misc_budgets]
        non_misc_actual_spendings = get_budgets_actual_spent(non_misc_budget_ids, start_date, end_date)
        total_non_misc_spent = sum(s['actual_spent'] for s in non_misc_actual_spendings.values())

        actual_spent = total_expenses - total_non_misc_spent
        difference = total_budgeted - actual_spent

        all_expense_transactions = JournalEntries.query \
            .join(Account, JournalEntries.debit_account_id == Account.id) \
            .filter(Account.type == 'Expense', JournalEntries.client_id == session['client_id'], JournalEntries.date >= start_date, JournalEntries.date <= end_date) \
            .all()
        all_expense_transaction_ids = {t.id for t in all_expense_transactions}

        non_misc_transaction_ids = set()
        for b_id in non_misc_budget_ids:
            non_misc_transaction_ids.update(non_misc_actual_spendings.get(b_id, {'transaction_ids': set()})['transaction_ids'])

        misc_transaction_ids = all_expense_transaction_ids - non_misc_transaction_ids

        page = request.args.get('page', 1, type=int)
        contributing_transactions = JournalEntries.query.filter(JournalEntries.id.in_(misc_transaction_ids)).order_by(JournalEntries.date.desc()).paginate(page=page, per_page=20, error_out=False)

        historical_performance = get_miscellaneous_historical_performance(budget, start_date, end_date)
        spending_breakdown = get_miscellaneous_spending_breakdown(budget, start_date, end_date)

    else:
        all_budgets_in_tree = [budget] + budget.get_all_descendants()
        budget_ids = [b.id for b in all_budgets_in_tree]

        num_periods = get_num_periods(start_date, end_date, budget.period)
        total_budgeted = sum(b.total_budgeted * num_periods for b in all_budgets_in_tree)

        actual_spendings = get_budgets_actual_spent(budget_ids, start_date, end_date)
        
        all_transaction_ids = set()
        for b_id in budget_ids:
            all_transaction_ids.update(actual_spendings.get(b_id, {'transaction_ids': set()})['transaction_ids'])

        actual_spent = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.id.in_(all_transaction_ids)).scalar() or 0
        difference = total_budgeted - actual_spent

        all_categories = []
        all_keywords = []
        for b in all_budgets_in_tree:
            for c in b.categories:
                all_categories.append(c.name)
            if b.keywords:
                all_keywords.extend([k.strip() for k in b.keywords.split(',')])

        journal_filters = [
            JournalEntries.client_id == session['client_id'],
            JournalEntries.date >= start_date,
            JournalEntries.date <= end_date,
            Account.type == 'Expense'
        ]

        conditions = []
        if all_categories:
            conditions.append(JournalEntries.category.in_(all_categories))
        if all_keywords:
            conditions.append(db.or_(*[JournalEntries.description.ilike(f'%{kw}%') for kw in all_keywords]))
        
        if conditions:
            journal_filters.append(db.or_(*conditions))

        sort_by = request.args.get('sort_by', 'date')
        sort_dir = request.args.get('sort_dir', 'desc')
        description = request.args.get('description', '')
        notes = request.args.get('notes', '')

        if description:
            journal_filters.append(JournalEntries.description.ilike(f'%{description}%'))
        if notes:
            journal_filters.append(JournalEntries.notes.ilike(f'%{notes}%'))

        sort_column = getattr(JournalEntries, sort_by, JournalEntries.date)

        if sort_dir == 'desc':
            sort_order = sort_column.desc()
        else:
            sort_order = sort_column.asc()

        page = request.args.get('page', 1, type=int)
        contributing_transactions = JournalEntries.query.join(Account, JournalEntries.debit_account_id == Account.id).filter(*journal_filters).order_by(sort_order).paginate(page=page, per_page=20, error_out=False)

        historical_performance = budget.get_historical_performance(start_date, end_date)
        spending_breakdown = budget.get_spending_breakdown(start_date, end_date)

    return render_template('budget_analysis.html', 
                           budget=budget, 
                           actual_spent=actual_spent, 
                           total_budgeted=total_budgeted,
                           difference=difference,
                           contributing_transactions=contributing_transactions,
                           period_start=start_date,
                           period_end=end_date,
                           historical_performance=historical_performance,
                           spending_breakdown=spending_breakdown,
                           start_date=start_date.strftime('%Y-%m-%d'),
                           end_date=end_date.strftime('%Y-%m-%d'))

@reports_bp.route('/export_budget_transactions/<int:budget_id>')
def export_budget_transactions(budget_id):
    budget = Budget.query.get_or_404(budget_id)
    if budget.client_id != session.get('client_id'):
        flash('You do not have permission to export these transactions.', 'danger')
        return redirect(url_for('reports.budget_analysis', budget_id=budget_id))

    start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d').date()
    end_date = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d').date()
    description = request.args.get('description', '')
    notes = request.args.get('notes', '')

    if budget.is_miscellaneous:
        # Get all expenses for the period
        all_expenses_query = db.session.query(JournalEntries.id, JournalEntries.amount).join(Account, JournalEntries.debit_account_id == Account.id).filter(
            Account.type == 'Expense',
            JournalEntries.client_id == session['client_id'],
            JournalEntries.date >= start_date,
            JournalEntries.date <= end_date
        )
        all_expenses = {e.id: e.amount for e in all_expenses_query.all()}
        all_expense_ids = set(all_expenses.keys())

        # Get transaction IDs covered by non-miscellaneous budgets
        non_misc_budgets = Budget.query.filter(Budget.client_id == session['client_id'], Budget.is_miscellaneous == False).all()
        non_misc_budget_ids = [b.id for b in non_misc_budgets]
        non_misc_budgets_actual_spendings = get_budgets_actual_spent(non_misc_budget_ids, start_date, end_date)
        
        covered_transaction_ids = set()
        for b_id in non_misc_budget_ids:
            covered_transaction_ids.update(non_misc_budgets_actual_spendings.get(b_id, {'transaction_ids': set()})['transaction_ids'])

        # Transactions not covered by any non-miscellaneous budget
        uncovered_transaction_ids = all_expense_ids - covered_transaction_ids

        journal_filters = [JournalEntries.id.in_(uncovered_transaction_ids)]

    else:
        all_budgets_in_tree = [budget] + budget.get_all_descendants()
        all_categories = []
        all_keywords = []
        for b in all_budgets_in_tree:
            for c in b.categories:
                all_categories.append(c.name)
            if b.keywords:
                all_keywords.extend([k.strip() for k in b.keywords.split(',')])

        journal_filters = [
            JournalEntries.client_id == session['client_id'],
            JournalEntries.date >= start_date,
            JournalEntries.date <= end_date,
            Account.type == 'Expense'
        ]

        conditions = []
        if all_categories:
            conditions.append(JournalEntries.category.in_(all_categories))
        if all_keywords:
            conditions.append(db.or_(*[JournalEntries.description.ilike(f'%{kw}%') for kw in all_keywords]))
        
        if conditions:
            journal_filters.append(db.or_(*conditions))

    if description:
        journal_filters.append(JournalEntries.description.ilike(f'%{description}%'))
    if notes:
        journal_filters.append(JournalEntries.notes.ilike(f'%{notes}%'))

    transactions = JournalEntries.query.join(Account, JournalEntries.debit_account_id == Account.id).filter(*journal_filters).order_by(JournalEntries.date.desc()).all()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Date', 'Description', 'Category', 'Notes', 'Amount'])
    for t in transactions:
        cw.writerow([t.date, t.description, t.category, t.notes, t.amount])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=budget_{budget.name}_transactions.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@reports_bp.route('/audit_trail')
def audit_trail():
    logs = AuditTrail.query.join(AuditTrail.user).filter_by(client_id=session['client_id']).order_by(AuditTrail.date.desc()).all()
    return render_template('audit_trail.html', logs=logs)

@reports_bp.route('/what_if_scenarios', methods=['GET', 'POST'])
def what_if_scenarios():
    if request.method == 'POST':
        budget_id = request.form.get('budget_id')
        new_amount = float(request.form.get('new_amount'))

        original_budget = Budget.query.get(budget_id)
        
        # Create a temporary, in-memory budget object for the scenario
        scenario_budget = Budget(
            id=original_budget.id, # Keep the same ID for calculations
            name=original_budget.name + " (Scenario)",
            amount=new_amount,
            period=original_budget.period,
            start_date=original_budget.start_date,
            client_id=original_budget.client_id,
            parent_id=original_budget.parent_id,
            keywords=original_budget.keywords,
            categories=original_budget.categories
        )

        today = datetime.now().date()
        start_date = today.replace(day=1)
        end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)

        # Calculate actual spending for both original and scenario budgets
        actual_spendings = get_budgets_actual_spent([original_budget.id], start_date, end_date)
        actual_spent = actual_spendings.get(original_budget.id, 0.0)

        original_difference = original_budget.total_budgeted - actual_spent
        scenario_difference = new_amount - actual_spent

        return render_template('what_if_scenarios.html', 
                               budgets=Budget.query.filter_by(client_id=session['client_id']).all(),
                               original_budget=original_budget,
                               scenario_budget=scenario_budget,
                               actual_spent=actual_spent,
                               original_difference=original_difference,
                               scenario_difference=scenario_difference,
                               selected_budget_id=int(budget_id))

    budgets = Budget.query.filter_by(client_id=session['client_id']).all()
    return render_template('what_if_scenarios.html', budgets=budgets)

@reports_bp.route('/full_pie_chart_expenses')
def full_pie_chart_expenses():
    client_id = session.get('client_id')
    start_date_str = request.args.get('start_date', (datetime.now().date().replace(day=1)).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', datetime.now().date().strftime('%Y-%m-%d'))

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    spending_by_category_query = db.session.query(
        JournalEntries.category,
        db.func.sum(JournalEntries.amount).label('total')
    ).join(Account, JournalEntries.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntries.client_id == client_id,
        JournalEntries.date >= start_date,
        JournalEntries.date <= end_date,
        JournalEntries.category != None,
        JournalEntries.category != ''
    ).group_by(JournalEntries.category).order_by(db.func.sum(JournalEntries.amount).desc())

    spending_by_category = spending_by_category_query.all()
    labels = json.dumps([item.category for item in spending_by_category])
    data = json.dumps([float(item.total) for item in spending_by_category])

    return render_template('full_pie_chart.html', 
                           title='Expense Breakdown', 
                           labels=labels, 
                           data=data, 
                           start_date=start_date_str, 
                           end_date=end_date_str)

@reports_bp.route('/full_pie_chart_income')
def full_pie_chart_income():
    client_id = session.get('client_id')
    start_date_str = request.args.get('start_date', (datetime.now().date().replace(day=1)).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', datetime.now().date().strftime('%Y-%m-%d'))

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    income_by_category_query = db.session.query(
        JournalEntries.category,
        db.func.sum(JournalEntries.amount).label('total')
    ).join(Account, JournalEntries.credit_account_id == Account.id).filter(
        Account.type == 'Revenue',
        JournalEntries.client_id == client_id,
        JournalEntries.date >= start_date,
        JournalEntries.date <= end_date,
        JournalEntries.category != None,
        JournalEntries.category != ''
    ).group_by(JournalEntries.category).order_by(db.func.sum(JournalEntries.amount).desc())

    income_by_category = income_by_category_query.all()
    labels = json.dumps([item.category for item in income_by_category])
    data = json.dumps([float(item.total) for item in income_by_category])

    return render_template('full_pie_chart.html', 
                           title='Income Breakdown', 
                           labels=labels, 
                           data=data, 
                           start_date=start_date_str, 
                           end_date=end_date_str)

@reports_bp.route('/export/ledger')
def export_ledger():
    accounts = Account.query.filter_by(client_id=session['client_id']).order_by(Account.name).all()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Account', 'Type', 'Opening Balance', 'Debits', 'Credits', 'Net Change', 'Closing Balance'])
    for account in accounts:
        debits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.debit_account_id == account.id).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.credit_account_id == account.id).scalar() or 0
        net_change = credits - debits
        closing_balance = account.opening_balance + net_change
        cw.writerow([account.name, account.type, account.opening_balance, abs(debits), credits, net_change, closing_balance])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=ledger.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@reports_bp.route('/export/income_statement')
def export_income_statement():
    income = db.session.query(Account.name, db.func.sum(JournalEntries.amount).label('total')).join(JournalEntries, JournalEntries.credit_account_id == Account.id).filter(Account.type.in_(['Revenue', 'Income']), JournalEntries.client_id == session['client_id']).group_by(Account.name).all()
    expenses = db.session.query(Account.name, db.func.sum(JournalEntries.amount).label('total')).join(JournalEntries, JournalEntries.debit_account_id == Account.id).filter(Account.type == 'Expense', JournalEntries.client_id == session['client_id']).group_by(Account.name).all()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Category', 'Amount'])
    cw.writerow(['Income', ''])
    for i in income:
        cw.writerow([i.name, i.total])
    cw.writerow(['Expenses', ''])
    for e in expenses:
        cw.writerow([e.name, e.total])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=income_statement.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@reports_bp.route('/export/balance_sheet')
def export_balance_sheet():
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Account', 'Type', 'Balance'])

    # Assets
    cw.writerow(['Assets', '', ''])
    asset_accounts = Account.query.filter(Account.type.in_(['Asset', 'Accounts Receivable', 'Inventory', 'Fixed Asset', 'Accumulated Depreciation'])).filter_by(client_id=session['client_id']).all()
    for account in asset_accounts:
        debits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.debit_account_id == account.id, JournalEntries.client_id == session['client_id']).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.credit_account_id == account.id, JournalEntries.client_id == session['client_id']).scalar() or 0
        balance = account.opening_balance + debits - credits
        cw.writerow([account.name, account.type, balance])

    # Liabilities
    cw.writerow(['Liabilities', '', ''])
    liability_accounts = Account.query.filter(Account.type.in_(['Liability', 'Accounts Payable', 'Long-Term Debt'])).filter_by(client_id=session['client_id']).all()
    for account in liability_accounts:
        debits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.debit_account_id == account.id, JournalEntries.client_id == session['client_id']).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.credit_account_id == account.id, JournalEntries.client_id == session['client_id']).scalar() or 0
        balance = account.opening_balance + credits - debits
        cw.writerow([account.name, account.type, balance])

    # Equity
    cw.writerow(['Equity', '', ''])
    equity_accounts = Account.query.filter_by(client_id=session['client_id'], type='Equity').all()
    for account in equity_accounts:
        debits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.debit_account_id == account.id, JournalEntries.client_id == session['client_id']).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.credit_account_id == account.id, JournalEntries.client_id == session['client_id']).scalar() or 0
        balance = account.opening_balance + credits - debits
        cw.writerow([account.name, account.type, balance])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=balance_sheet.csv"
    output.headers["Content-type"] = "text/csv"
    return output
