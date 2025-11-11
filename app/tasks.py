from app import db, scheduler
from app.models import FixedAsset, Depreciation, JournalEntries, Account, RecurringTransaction, PendingPlaidLink, Transaction, Client, Budget, Notification, NotificationRule
from datetime import datetime, timedelta
from flask import session, current_app
import logging
from collections import defaultdict

def calculate_and_record_depreciation():
    with scheduler.app.app_context():
        today = datetime.now()
        clients = Client.query.all()
        for client in clients:
            assets = FixedAsset.query.filter_by(client_id=client.id).all()
            for asset in assets:
                # Calculate monthly depreciation
                monthly_depreciation = abs((asset.cost - asset.salvage_value) / (asset.useful_life * 12))
                
                # Check if depreciation has already been recorded for the current month
                last_depreciation = Depreciation.query.filter_by(fixed_asset_id=asset.id).order_by(Depreciation.date.desc()).first()
                if last_depreciation:
                    last_depreciation_date = last_depreciation.date
                    if last_depreciation_date.year == today.year and last_depreciation_date.month == today.month:
                        continue

                # Record depreciation for the current month
                new_depreciation = Depreciation(
                    date=today.date(),
                    amount=abs(monthly_depreciation),
                    fixed_asset_id=asset.id,
                    client_id=client.id
                )
                db.session.add(new_depreciation)

                # Create journal entry for depreciation
                depreciation_expense_account = Account.query.filter_by(type='Expense', category='Depreciation', client_id=client.id).first()
                accumulated_depreciation_account = Account.query.filter_by(type='Accumulated Depreciation', client_id=client.id).first()

                if depreciation_expense_account and accumulated_depreciation_account:
                    new_entry = JournalEntry(
                        date=today.date(),
                        description=f"Depreciation for {asset.name}",
                        debit_account_id=depreciation_expense_account.id,
                        credit_account_id=accumulated_depreciation_account.id,
                        amount=abs(monthly_depreciation),
                        client_id=client.id
                    )
                    db.session.add(new_entry)

        db.session.commit()

def reverse_accruals():
    with scheduler.app.app_context():
        today = datetime.now()
        if today.day == 1:
            clients = Client.query.all()
            for client in clients:
                accruals_to_reverse = JournalEntry.query.filter_by(client_id=client.id, is_accrual=True).all()
                for accrual in accruals_to_reverse:
                    # Create a reversing entry
                    new_entry = JournalEntry(
                        date=today.date(),
                        description=f"Reversal of: {accrual.description}",
                        debit_account_id=accrual.credit_account_id,
                        credit_account_id=accrual.debit_account_id,
                        amount=abs(accrual.amount),
                        is_accrual=False,
                        client_id=client.id
                    )
                    db.session.add(new_entry)
                    accrual.is_accrual = False
            db.session.commit()

def create_recurring_journal_entries():
    with scheduler.app.app_context():
        today = datetime.now()
        clients = Client.query.all()
        for client in clients:
            recurring_transactions = RecurringTransaction.query.filter_by(client_id=client.id).all()
            for transaction in recurring_transactions:
                # Check if the transaction is due
                start_date = transaction.start_date
                if transaction.end_date:
                    end_date = transaction.end_date
                    if today < start_date or today > end_date:
                        continue
                elif today < start_date:
                    continue

                # Check if a journal entry has already been created for the current period
                last_journal_entry = JournalEntry.query.filter_by(description=transaction.description, client_id=client.id).order_by(JournalEntry.date.desc()).first()
                if last_journal_entry:
                    last_journal_entry_date = last_journal_entry.date
                    if transaction.frequency == 'monthly' and last_journal_entry_date.year == today.year and last_journal_entry_date.month == today.month:
                        continue
                    elif transaction.frequency == 'weekly' and last_journal_entry_date.isocalendar()[1] == today.isocalendar()[1]:
                        continue
                    elif transaction.frequency == 'daily' and last_journal_entry_date.date() == today.date():
                        continue
                    elif transaction.frequency == 'yearly' and last_journal_entry_date.year == today.year:
                        continue

                # Create a new journal entry
                new_entry = JournalEntry(
                    date=today.date(),
                    description=transaction.description,
                    debit_account_id=transaction.debit_account_id,
                    credit_account_id=transaction.credit_account_id,
                    amount=abs(transaction.amount),
                    client_id=client.id
                )
                db.session.add(new_entry)
        db.session.commit()

def cleanup_pending_plaid_links():
    with scheduler.app.app_context():
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        expired_links = PendingPlaidLink.query.filter(PendingPlaidLink.created_at < seven_days_ago).all()
        if expired_links:
            for link in expired_links:
                db.session.delete(link)
            db.session.commit()
            logging.info(f"Cleaned up {len(expired_links)} expired pending Plaid links.")

def detect_recurring_transactions(client_id):
    with current_app.app_context():
        # Get all transactions for the current client
        transactions = Transaction.query.filter_by(client_id=client_id).order_by(Transaction.date.desc()).all()

        # Group transactions by description and amount
        grouped_transactions = defaultdict(list)
        for transaction in transactions:
            grouped_transactions[(transaction.description, transaction.amount)].append(transaction)

        # Find transactions that occur at regular intervals
        recurring_transactions = []
        for (description, amount), transaction_group in grouped_transactions.items():
            if len(transaction_group) > 1:
                # Sort transactions by date
                transaction_group.sort(key=lambda x: x.date)

                # Calculate the time difference between transactions
                time_diffs = []
                for i in range(len(transaction_group) - 1):
                    date1 = transaction_group[i].date
                    date2 = transaction_group[i+1].date
                    time_diffs.append((date2 - date1).days)

                # If the time differences are consistent, it's a recurring transaction
                if len(set(time_diffs)) == 1:
                    frequency_days = time_diffs[0]
                    if 28 <= frequency_days <= 31:
                        frequency = 'monthly'
                    elif 7 == frequency_days:
                        frequency = 'weekly'
                    elif 365 == frequency_days:
                        frequency = 'yearly'
                    elif 1 == frequency_days:
                        frequency = 'daily'
                    else:
                        continue

                    recurring_transactions.append({
                        'name': description,
                        'description': description,
                        'amount': amount,
                        'frequency': frequency,
                        'start_date': transaction_group[0].date,
                        'end_date': transaction_group[-1].date,
                        'debit_account_id': None, # User will select this
                        'credit_account_id': None # User will select this
                    })

        return recurring_transactions

def check_budgets():
    with scheduler.app.app_context():
        from app.utils import get_budgets_actual_spent
        today = datetime.now().date()
        clients = Client.query.all()
        for client in clients:
            budgets = Budget.query.filter_by(client_id=client.id).all()
            if not budgets:
                continue

            budget_ids = [b.id for b in budgets]
            start_date = today.replace(day=1)
            end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)
            actual_spendings = get_budgets_actual_spent(budget_ids, start_date, end_date)

            for budget in budgets:
                actual_spent = actual_spendings.get(budget.id, {'actual_spent': 0.0})['actual_spent']
                if actual_spent >= budget.total_budgeted * 0.8:
                    user = client.users[0] # Assuming one user per client for now
                    message = f"You have spent {actual_spent:.2f} of your {budget.total_budgeted:.2f} budget for {budget.name}."
                    notification = Notification(user_id=user.id, message=message)
                    db.session.add(notification)
        db.session.commit()

def check_notification_rules():
    with scheduler.app.app_context():
        today = datetime.now().date()
        clients = Client.query.all()
        for client in clients:
            rules = NotificationRule.query.filter_by(client_id=client.id).all()
            for rule in rules:
                if rule.criteria_type == 'daily_spending':
                    total_spent_today = db.session.query(db.func.sum(JournalEntries.amount)) \
                        .join(Account, JournalEntries.debit_account_id == Account.id) \
                        .filter(Account.type == 'Expense', JournalEntries.client_id == client.id, JournalEntries.date == today) \
                        .scalar() or 0

                    if total_spent_today > rule.criteria_value:
                        message = f"You have spent {total_spent_today:.2f} today, which exceeds your daily spending limit of {rule.criteria_value:.2f}."
                        if rule.notification_method == 'in_app':
                            notification = Notification(message=message)
                            db.session.add(notification)
                        elif rule.notification_method == 'email':
                            # Placeholder for sending email
                            pass
                        elif rule.notification_method == 'sms':
                            # Placeholder for sending SMS
                            pass
        db.session.commit()
