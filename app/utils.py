from app.models import Account, AuditTrail, JournalEntry, Reconciliation
from flask import session
from flask_login import current_user
from app import db

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
        debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id == account.id).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id == account.id).scalar() or 0
        if account.type in ['Asset', 'Expense']:
            return account.opening_balance + debits - credits
        else:
            return account.opening_balance + credits - debits

    def _update_balances_recursive(account):
        if not account.children.first():  # It's a leaf node
            if not account.plaid_accounts:
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
        debits_query = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id == account.id)
        credits_query = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id == account.id)

        if start_date and end_date:
            debits_query = debits_query.filter(JournalEntry.date.between(start_date, end_date))
            credits_query = credits_query.filter(JournalEntry.date.between(start_date, end_date))

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
