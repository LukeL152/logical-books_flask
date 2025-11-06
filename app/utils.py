from app.models import Account, AuditTrail, JournalEntries, Reconciliation, Budget
from flask import session
from flask_login import current_user
from app import db
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def get_num_periods(start_date, end_date, period):
    if period == 'monthly':
        delta = relativedelta(end_date, start_date)
        return delta.years * 12 + delta.months + 1
    elif period == 'quarterly':
        start_quarter = (start_date.month - 1) // 3 + 1
        end_quarter = (end_date.month - 1) // 3 + 1
        return (end_date.year - start_date.year) * 4 + end_quarter - start_quarter + 1
    elif period == 'yearly':
        return end_date.year - start_date.year + 1
    return 1

def get_account_choices(client_id):
    def _get_accounts_recursive(parent_id, level):
        accounts = Account.query.filter_by(client_id=client_id, parent_id=parent_id).order_by(Account.name).all()
        choices = []
        for account in accounts:
            choices.append((account.id, account.name, int(level)))
            choices.extend(_get_accounts_recursive(account.id, level + 1))
        return choices

    return _get_accounts_recursive(None, 0)

def log_audit(action):
    if 'client_id' in session and current_user.is_authenticated:
        audit_log = AuditTrail(user_id=current_user.id, action=action)
        db.session.add(audit_log)
        db.session.commit()

def update_all_balances(client_id):
    from datetime import datetime

    def _calculate_balance(account):
        debits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.debit_account_id == account.id).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.credit_account_id == account.id).scalar() or 0
        if account.type in ['Asset', 'Expense']:
            return account.opening_balance + debits - credits
        else:
            return account.opening_balance + credits - debits

    def _update_balances_recursive(account):
        if not account.children.first():  # It's a leaf node
            if not account.plaid_account_link:
                account.current_balance = _calculate_balance(account)
                account.balance_last_updated = datetime.utcnow()
        else:  # It's a parent account
            child_balance_sum = 0
            for child in account.children:
                child_balance_sum += _update_balances_recursive(child)
            account.current_balance = child_balance_sum
            account.balance_last_updated = datetime.utcnow()
        
        db.session.add(account)
        return account.current_balance

    top_level_accounts = Account.query.filter_by(client_id=client_id, parent_id=None).all()
    for account in top_level_accounts:
        _update_balances_recursive(account)
    
    db.session.commit()

def get_account_tree(accounts, start_date=None, end_date=None):
    account_tree = []
    for account in accounts:
        children_tree = get_account_tree(account.children.all(), start_date, end_date)
        
        # Calculate this account's individual balance without children
        debits_query = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.debit_account_id == account.id)
        credits_query = db.session.query(db.func.sum(JournalEntries.amount)).filter(JournalEntries.credit_account_id == account.id)

        if start_date and end_date:
            debits_query = debits_query.filter(JournalEntries.date.between(start_date, end_date))
            credits_query = credits_query.filter(JournalEntries.date.between(start_date, end_date))

        debits = debits_query.scalar() or 0
        credits = credits_query.scalar() or 0

        if account.type in ['Asset', 'Expense']:
            own_balance = account.opening_balance + debits - credits
        else: # Liability, Equity, Income
            own_balance = account.opening_balance + credits - debits

        # Total balance is own balance plus sum of children's balances
        balance = own_balance + sum(child['balance'] for child in children_tree)

        last_reconciliation = Reconciliation.query.filter_by(account_id=account.id).order_by(Reconciliation.statement_date.desc()).first()

        account_tree.append({
            'id': account.id,
            'parent_id': account.parent_id,
            'name': account.name,
            'balance': balance,
            'children': children_tree,
            'last_reconciliation_date': last_reconciliation.statement_date if last_reconciliation else None,
            'live_balance': account.current_balance,
            'live_balance_updated_at': account.balance_last_updated
        })
    return account_tree

def get_budgets_actual_spent(budget_ids, start_date, end_date):
    from app.models import Budget, JournalEntries, Account
    budgets = Budget.query.filter(Budget.id.in_(budget_ids)).all()
    if not budgets:
        return {}

    client_id = budgets[0].client_id
    budget_spending = {budget_id: {'actual_spent': 0.0, 'transaction_ids': set()} for budget_id in budget_ids}

    for budget in budgets:
        if budget.is_miscellaneous:
            budget_spending[budget.id]['actual_spent'] = 0.0
            budget_spending[budget.id]['transaction_ids'] = set()
            continue

        budget_categories = {c.name for c in budget.categories}
        budget_keywords = {k.strip() for k in budget.keywords.split(',')} if budget.keywords else set()

        if not budget_categories and not budget_keywords:
            budget_spending[budget.id]['actual_spent'] = 0.0
            budget_spending[budget.id]['transaction_ids'] = set()
            continue

        query_filter = [
            JournalEntries.client_id == client_id,
            JournalEntries.date >= start_date,
            JournalEntries.date <= end_date
        ]

        category_filter = None
        if budget_categories:
            category_filter = JournalEntries.category.in_(budget_categories)

        keyword_filter = None
        if budget_keywords:
            keyword_filters = []
            for keyword in budget_keywords:
                keyword_filters.append(JournalEntries.description.ilike(f'%{keyword}%'))
            keyword_filter = db.or_(*keyword_filters)

        if category_filter is not None and keyword_filter is not None:
            query_filter.append(db.or_(category_filter, keyword_filter))
        elif category_filter is not None:
            query_filter.append(category_filter)
        elif keyword_filter is not None:
            query_filter.append(keyword_filter)

        transactions = JournalEntries.query.join(Account, JournalEntries.debit_account_id == Account.id).filter(Account.type == 'Expense', *query_filter).all()
        budget_spending[budget.id]['actual_spent'] = sum(t.amount for t in transactions)
        budget_spending[budget.id]['transaction_ids'] = {t.id for t in transactions}

    return budget_spending

def get_miscellaneous_historical_performance(budget, start_date, end_date):
    from app.models import Budget, JournalEntries, Account
    history = []
    num_periods_to_display = get_num_periods(start_date, end_date, budget.period)

    current_end_of_period = end_date
    for i in range(num_periods_to_display):
        if budget.period == 'monthly':
            period_start = current_end_of_period.replace(day=1)
            period_end = current_end_of_period
            period_name = period_start.strftime("%B %Y")
            current_end_of_period = period_start - timedelta(days=1)
        elif budget.period == 'quarterly':
            current_quarter_start_month = (current_end_of_period.month - 1) // 3 * 3 + 1
            period_start = current_end_of_period.replace(month=current_quarter_start_month, day=1)
            period_end = (period_start + relativedelta(months=3)) - timedelta(days=1)
            period_name = f"Q{(current_quarter_start_month - 1) // 3 + 1} {current_end_of_period.year}"
            current_end_of_period = period_start - timedelta(days=1)
        else: # yearly
            period_start = current_end_of_period.replace(month=1, day=1)
            period_end = current_end_of_period.replace(month=12, day=31)
            period_name = str(current_end_of_period.year)
            current_end_of_period = period_start - timedelta(days=1)

        effective_period_start = max(period_start, start_date)
        effective_period_end = min(period_end, end_date)

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

        history.append({
            'period_name': period_name,
            'budgeted': budget.total_budgeted,
            'actual': hist_actual_spent,
            'difference': budget.total_budgeted - hist_actual_spent
        })
    history.reverse()
    return history

def get_miscellaneous_spending_breakdown(budget, start_date, end_date):
    from app.models import Budget, JournalEntries, Account

    client_id = budget.client_id

    # Get all expense transactions for the period
    all_expense_transactions = JournalEntries.query \
        .join(Account, JournalEntries.debit_account_id == Account.id) \
        .filter(Account.type == 'Expense', JournalEntries.client_id == client_id, JournalEntries.date >= start_date, JournalEntries.date <= end_date) \
        .all()
    all_expense_transaction_ids = {t.id for t in all_expense_transactions}

    # Get transaction IDs covered by non-miscellaneous budgets
    non_misc_budgets = Budget.query.filter(Budget.client_id == client_id, Budget.is_miscellaneous == False).all()
    non_misc_budget_ids = [b.id for b in non_misc_budgets]
    non_misc_budgets_actual_spendings = get_budgets_actual_spent(non_misc_budget_ids, start_date, end_date)
    
    covered_transaction_ids = set()
    for b_id in non_misc_budget_ids:
        covered_transaction_ids.update(non_misc_budgets_actual_spendings.get(b_id, {'transaction_ids': set()})['transaction_ids'])

    # Transactions not covered by any non-miscellaneous budget
    misc_transaction_ids = all_expense_transaction_ids - covered_transaction_ids

    # Calculate spending breakdown by category for the miscellaneous transactions
    spending_breakdown_query = db.session.query(
        JournalEntries.category,
        db.func.sum(JournalEntries.amount).label('total')
    ).filter(
        JournalEntries.id.in_(misc_transaction_ids),
        JournalEntries.category != None,
        JournalEntries.category != ''
    ).group_by(JournalEntries.category).order_by(db.func.sum(JournalEntries.amount).desc())

    spending_breakdown = spending_breakdown_query.all()

    return spending_breakdown
