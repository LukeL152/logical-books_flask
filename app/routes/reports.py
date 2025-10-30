from flask import Blueprint, render_template, request, session, make_response, redirect, url_for, flash
from app import db
from app.models import Account, JournalEntry, Reconciliation, Budget, AuditTrail, Transaction, Category
from datetime import datetime, timedelta
import csv
import io
import json
from app.utils import get_account_tree

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
    revenue = db.session.query(db.func.sum(JournalEntry.amount)).join(Account, JournalEntry.credit_account_id == Account.id).filter(Account.type == 'Revenue', JournalEntry.client_id == session['client_id']).scalar() or 0
    expenses = db.session.query(db.func.sum(JournalEntry.amount)).join(Account, JournalEntry.debit_account_id == Account.id).filter(Account.type == 'Expense', JournalEntry.client_id == session['client_id']).scalar() or 0
    net_income = revenue - expenses

    # Depreciation
    depreciation = 0  # Placeholder

    # Change in Accounts Receivable
    ar_accounts = Account.query.filter_by(type='Accounts Receivable', client_id=session['client_id']).all()
    ar_balance = sum(acc.opening_balance for acc in ar_accounts)
    ar_debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id.in_([acc.id for acc in ar_accounts])).scalar() or 0
    ar_credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id.in_([acc.id for acc in ar_accounts])).scalar() or 0
    change_in_accounts_receivable = (ar_balance + ar_debits - ar_credits) - ar_balance

    # Change in Inventory
    inventory_accounts = Account.query.filter_by(type='Inventory', client_id=session['client_id']).all()
    inventory_balance = sum(acc.opening_balance for acc in inventory_accounts)
    inventory_debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id.in_([acc.id for acc in inventory_accounts])).scalar() or 0
    inventory_credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id.in_([acc.id for acc in inventory_accounts])).scalar() or 0
    change_in_inventory = (inventory_balance + inventory_debits - inventory_credits) - inventory_balance

    # Change in Accounts Payable
    ap_accounts = Account.query.filter_by(type='Accounts Payable', client_id=session['client_id']).all()
    ap_balance = sum(acc.opening_balance for acc in ap_accounts)
    ap_debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id.in_([acc.id for acc in ap_accounts])).scalar() or 0
    ap_credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id.in_([acc.id for acc in ap_accounts])).scalar() or 0
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
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntry.client_id == client_id,
        JournalEntry.date >= start_date_1,
        JournalEntry.date <= end_date_1,
        JournalEntry.category != None,
        JournalEntry.category != ''
    ).group_by(JournalEntry.category).order_by(db.func.sum(JournalEntry.amount).desc())

    spending_by_category = spending_by_category_query.all()
    category_labels = json.dumps([item.category for item in spending_by_category])
    category_data = json.dumps([item.total for item in spending_by_category])

    # --- Income by Category (Period 1) ---
    income_by_category_query = db.session.query(
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.credit_account_id == Account.id).filter(
        Account.type == 'Revenue',
        JournalEntry.client_id == client_id,
        JournalEntry.date >= start_date_1,
        JournalEntry.date <= end_date_1,
        JournalEntry.category != None,
        JournalEntry.category != ''
    ).group_by(JournalEntry.category).order_by(db.func.sum(JournalEntry.amount).desc())

    income_by_category = income_by_category_query.all()
    income_category_labels = json.dumps([item.category for item in income_by_category])
    income_category_data = json.dumps([float(item.total) for item in income_by_category])

    # --- Category Comparison ---
    # For simplicity, we'll just use the top 5 categories from Period 1 for comparison
    top_categories = [item.category for item in spending_by_category[:5]]

    category_comparison_data_1 = []
    category_comparison_data_2 = []

    for category in top_categories:
        total_1 = db.session.query(db.func.sum(JournalEntry.amount)).join(Account, JournalEntry.debit_account_id == Account.id).filter(
            Account.type == 'Expense',
            JournalEntry.client_id == client_id,
            JournalEntry.date >= start_date_1,
            JournalEntry.date <= end_date_1,
            JournalEntry.category == category
        ).scalar() or 0
        category_comparison_data_1.append(total_1)

        total_2 = db.session.query(db.func.sum(JournalEntry.amount)).join(Account, JournalEntry.debit_account_id == Account.id).filter(
            Account.type == 'Expense',
            JournalEntry.client_id == client_id,
            JournalEntry.date >= start_date_2,
            JournalEntry.date <= end_date_2,
            JournalEntry.category == category
        ).scalar() or 0
        category_comparison_data_2.append(total_2)

    category_comparison_labels = json.dumps(top_categories)
    category_comparison_data_1 = json.dumps(category_comparison_data_1)
    category_comparison_data_2 = json.dumps(category_comparison_data_2)

    # --- Income vs. Expense ---
    # Monthly data for line chart (similar to dashboard)
    income_by_month_query = db.session.query(
        db.func.strftime('%Y-%m', JournalEntry.date).label('month'),
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.credit_account_id == Account.id).filter(
        Account.type.in_(['Revenue', 'Income']),
        JournalEntry.client_id == client_id,
        JournalEntry.date >= start_date_1, # Using Period 1 for this chart
        JournalEntry.date <= end_date_1
    ).group_by('month')

    expense_by_month_query = db.session.query(
        db.func.strftime('%Y-%m', JournalEntry.date).label('month'),
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntry.client_id == client_id,
        JournalEntry.date >= start_date_1, # Using Period 1 for this chart
        JournalEntry.date <= end_date_1
    ).group_by('month')

    income_by_month = {r.month: r.total for r in income_by_month_query.all()}
    expense_by_month = {r.month: r.total for r in expense_by_month_query.all()}

    all_months = sorted(list(set(income_by_month.keys()) | set(expense_by_month.keys())))

    income_trend_data = json.dumps([income_by_month.get(m, 0) for m in all_months])
    expense_trend_data = json.dumps([expense_by_month.get(m, 0) for m in all_months])
    all_months_json = json.dumps(all_months) # Renamed to avoid conflict with template variable

    # --- Cash Flow Statement (using Period 1 for now) ---
    # Net Income
    revenue = db.session.query(db.func.sum(JournalEntry.amount)).join(Account, JournalEntry.credit_account_id == Account.id).filter(Account.type.in_(['Revenue', 'Income']), JournalEntry.client_id == client_id, JournalEntry.date >= start_date_1, JournalEntry.date <= end_date_1).scalar() or 0
    expenses = db.session.query(db.func.sum(JournalEntry.amount)).join(Account, JournalEntry.debit_account_id == Account.id).filter(Account.type == 'Expense', JournalEntry.client_id == client_id, JournalEntry.date >= start_date_1, JournalEntry.date <= end_date_1).scalar() or 0
    net_income = revenue - expenses

    # Depreciation (Placeholder)
    depreciation = 0

    # Change in Accounts Receivable
    ar_accounts = Account.query.filter_by(type='Accounts Receivable', client_id=client_id).all()
    ar_balance_start = sum(db.session.query(db.func.sum(JournalEntry.amount)).filter(db.or_(JournalEntry.debit_account_id == acc.id, JournalEntry.credit_account_id == acc.id), JournalEntry.client_id == client_id, JournalEntry.date < start_date_1).scalar() or 0 for acc in ar_accounts)
    ar_balance_end = sum(db.session.query(db.func.sum(JournalEntry.amount)).filter(db.or_(JournalEntry.debit_account_id == acc.id, JournalEntry.credit_account_id == acc.id), JournalEntry.client_id == client_id, JournalEntry.date <= end_date_1).scalar() or 0 for acc in ar_accounts)
    change_in_accounts_receivable = ar_balance_end - ar_balance_start

    # Change in Inventory
    inventory_accounts = Account.query.filter_by(type='Inventory', client_id=client_id).all()
    inventory_balance_start = sum(db.session.query(db.func.sum(JournalEntry.amount)).filter(db.or_(JournalEntry.debit_account_id == acc.id, JournalEntry.credit_account_id == acc.id), JournalEntry.client_id == client_id, JournalEntry.date < start_date_1).scalar() or 0 for acc in inventory_accounts)
    inventory_balance_end = sum(db.session.query(db.func.sum(JournalEntry.amount)).filter(db.or_(JournalEntry.debit_account_id == acc.id, JournalEntry.credit_account_id == acc.id), JournalEntry.client_id == client_id, JournalEntry.date <= end_date_1).scalar() or 0 for acc in inventory_accounts)
    change_in_inventory = inventory_balance_end - inventory_balance_start

    # Change in Accounts Payable
    ap_accounts = Account.query.filter_by(type='Accounts Payable', client_id=client_id).all()
    ap_balance_start = sum(db.session.query(db.func.sum(JournalEntry.amount)).filter(db.or_(JournalEntry.debit_account_id == acc.id, JournalEntry.credit_account_id == acc.id), JournalEntry.client_id == client_id, JournalEntry.date < start_date_1).scalar() or 0 for acc in ap_accounts)
    ap_balance_end = sum(db.session.query(db.func.sum(JournalEntry.amount)).filter(db.or_(JournalEntry.debit_account_id == acc.id, JournalEntry.credit_account_id == acc.id), JournalEntry.client_id == client_id, JournalEntry.date <= end_date_1).scalar() or 0 for acc in ap_accounts)
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

@reports_bp.route('/populate_categories')
def populate_categories():
    client_id = session.get('client_id')
    if not client_id:
        flash('Please select a client first.', 'warning')
        return redirect(url_for('clients.clients'))

    # Get categories from JournalEntry
    journal_categories = db.session.query(JournalEntry.category).filter(
        JournalEntry.client_id == client_id,
        JournalEntry.category != None,
        JournalEntry.category != ''
    ).distinct().all()

    # Get categories from Transaction
    transaction_categories = db.session.query(Transaction.category).filter(
        Transaction.client_id == client_id,
        Transaction.category != None,
        Transaction.category != ''
    ).distinct().all()

    all_categories = set([c[0] for c in journal_categories] + [c[0] for c in transaction_categories])

    existing_categories = [c.name for c in Category.query.all()]

    for cat_name in all_categories:
        if cat_name not in existing_categories:
            new_category = Category(name=cat_name)
            db.session.add(new_category)
    
    db.session.commit()
    flash('Categories populated successfully!', 'success')
    return redirect(url_for('reports.budget'))

@reports_bp.route('/budget', methods=['GET', 'POST'])
def budget():
    if request.method == 'POST':
        name = request.form.get('name')
        categories = request.form.getlist('categories')
        amount = request.form.get('amount')
        period = request.form.get('period')
        start_date_str = request.form.get('start_date')
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()

        new_budget = Budget(
            name=name,
            amount=amount,
            period=period,
            start_date=start_date,
            client_id=session['client_id'],
            parent_id=request.form.get('parent_id') if request.form.get('parent_id') else None,
            keywords=request.form.get('keywords')
        )

        for category_id in categories:
            category = Category.query.get(category_id)
            if category:
                new_budget.categories.append(category)
        db.session.add(new_budget)
        db.session.commit()
        return redirect(url_for('reports.budget'))

    def build_budget_tree(parent_budget=None):
        if parent_budget:
            budgets = Budget.query.filter_by(client_id=session['client_id'], parent_id=parent_budget.id).order_by(Budget.name).all()
        else:
            budgets = Budget.query.filter_by(client_id=session['client_id'], parent_id=None).order_by(Budget.name).all()

        tree = []
        for budget in budgets:
            # Calculate actual_spent and remaining for each budget
            today = datetime.now().date()
            if budget.period == 'monthly':
                start_date = today.replace(day=1)
                end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)
            elif budget.period == 'quarterly':
                current_quarter = (today.month - 1) // 3 + 1
                start_date = datetime(today.year, 3 * current_quarter - 2, 1).date()
                period_end_month = 3 * current_quarter
                period_end_year = today.year
                if period_end_month > 12:
                    period_end_month -= 12
                    period_end_year += 1
                end_date = (datetime(period_end_year, period_end_month, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            elif budget.period == 'yearly':
                start_date = today.replace(month=1, day=1)
                end_date = today.replace(month=12, day=31)
            else:
                start_date = budget.start_date
                end_date = today # Default to up to today if period is weird

            budget_categories = [c.name for c in budget.categories]
            budget_keywords = [k.strip() for k in budget.keywords.split(',')] if budget.keywords else []

            journal_filters = [
                Account.type == 'Expense',
                JournalEntry.client_id == session['client_id'],
                JournalEntry.date >= start_date,
                JournalEntry.date <= end_date
            ]
            if budget_categories:
                journal_filters.append(JournalEntry.category.in_(budget_categories))
            if budget_keywords:
                journal_filters.append(db.or_(*[JournalEntry.description.ilike(f'%{kw}%') for kw in budget_keywords]))

            actual_spent_journal = db.session.query(
                db.func.sum(JournalEntry.amount)
            ).join(Account, JournalEntry.debit_account_id == Account.id).filter(
                *journal_filters
            ).scalar() or 0.0

            transaction_filters = [
                Transaction.client_id == session['client_id'],
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                Transaction.is_approved == False
            ]
            if budget_categories:
                transaction_filters.append(Transaction.category.in_(budget_categories))
            if budget_keywords:
                transaction_filters.append(db.or_(*[Transaction.description.ilike(f'%{kw}%') for kw in budget_keywords]))

            actual_spent_transaction = db.session.query(
                db.func.sum(Transaction.amount)
            ).filter(
                *transaction_filters
            ).scalar() or 0.0

            budget.actual_spent = actual_spent_journal + actual_spent_transaction
            budget.remaining = budget.amount - budget.actual_spent

            tree.append({
                'budget': budget,
                'children': build_budget_tree(budget)
            })
        return tree

    budget_tree = build_budget_tree()
    categories = Category.query.order_by(Category.name).all()
    all_budgets = Budget.query.filter_by(client_id=session['client_id']).order_by(Budget.name).all()

    return render_template('budget.html', budget_tree=budget_tree, categories=categories, all_budgets=all_budgets)

@reports_bp.route('/budget/<int:budget_id>/delete', methods=['GET']) # Should be POST
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

        budget.categories.clear()
        category_ids = request.form.getlist('categories')
        for cat_id in category_ids:
            category = Category.query.get(cat_id)
            if category:
                budget.categories.append(category)

        db.session.commit()
        flash('Budget updated successfully.', 'success')
        return redirect(url_for('reports.budget'))

    categories = Category.query.order_by(Category.name).all()
    return render_template('edit_budget.html', budget=budget, categories=categories)

@reports_bp.route('/audit_trail')
def audit_trail():
    logs = AuditTrail.query.join(AuditTrail.user).filter_by(client_id=session['client_id']).order_by(AuditTrail.date.desc()).all()
    return render_template('audit_trail.html', logs=logs)

@reports_bp.route('/full_pie_chart_expenses')
def full_pie_chart_expenses():
    client_id = session.get('client_id')
    start_date_str = request.args.get('start_date', (datetime.now().date().replace(day=1)).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', datetime.now().date().strftime('%Y-%m-%d'))

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    spending_by_category_query = db.session.query(
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntry.client_id == client_id,
        JournalEntry.date >= start_date,
        JournalEntry.date <= end_date,
        JournalEntry.category != None,
        JournalEntry.category != ''
    ).group_by(JournalEntry.category).order_by(db.func.sum(JournalEntry.amount).desc())

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
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.credit_account_id == Account.id).filter(
        Account.type == 'Revenue',
        JournalEntry.client_id == client_id,
        JournalEntry.date >= start_date,
        JournalEntry.date <= end_date,
        JournalEntry.category != None,
        JournalEntry.category != ''
    ).group_by(JournalEntry.category).order_by(db.func.sum(JournalEntry.amount).desc())

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
        debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id == account.id).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id == account.id).scalar() or 0
        net_change = credits - debits
        closing_balance = account.opening_balance + net_change
        cw.writerow([account.name, account.type, account.opening_balance, abs(debits), credits, net_change, closing_balance])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=ledger.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@reports_bp.route('/export/income_statement')
def export_income_statement():
    income = db.session.query(Account.name, db.func.sum(JournalEntry.amount).label('total')).join(JournalEntry, JournalEntry.credit_account_id == Account.id).filter(Account.type.in_(['Revenue', 'Income']), JournalEntry.client_id == session['client_id']).group_by(Account.name).all()
    expenses = db.session.query(Account.name, db.func.sum(JournalEntry.amount).label('total')).join(JournalEntry, JournalEntry.debit_account_id == Account.id).filter(Account.type == 'Expense', JournalEntry.client_id == session['client_id']).group_by(Account.name).all()
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
        debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id == account.id, JournalEntry.client_id == session['client_id']).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id == account.id, JournalEntry.client_id == session['client_id']).scalar() or 0
        balance = account.opening_balance + debits - credits
        cw.writerow([account.name, account.type, balance])

    # Liabilities
    cw.writerow(['Liabilities', '', ''])
    liability_accounts = Account.query.filter(Account.type.in_(['Liability', 'Accounts Payable', 'Long-Term Debt'])).filter_by(client_id=session['client_id']).all()
    for account in liability_accounts:
        debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id == account.id, JournalEntry.client_id == session['client_id']).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id == account.id, JournalEntry.client_id == session['client_id']).scalar() or 0
        balance = account.opening_balance + credits - debits
        cw.writerow([account.name, account.type, balance])

    # Equity
    cw.writerow(['Equity', '', ''])
    equity_accounts = Account.query.filter_by(client_id=session['client_id'], type='Equity').all()
    for account in equity_accounts:
        debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id == account.id, JournalEntry.client_id == session['client_id']).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id == account.id, JournalEntry.client_id == session['client_id']).scalar() or 0
        balance = account.opening_balance + credits - debits
        cw.writerow([account.name, account.type, balance])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=balance_sheet.csv"
    output.headers["Content-type"] = "text/csv"
    return output
