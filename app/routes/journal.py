from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.models import JournalEntry, Account, Transaction
from datetime import datetime
from sqlalchemy import func
from app.utils import get_account_choices, log_audit

journal_bp = Blueprint('journal', __name__)

@journal_bp.route('/journal', methods=['GET', 'POST'])
def journal():
    query = db.session.query(JournalEntry).options(db.joinedload(JournalEntry.transaction).joinedload(Transaction.source_account)).join(Account, JournalEntry.debit_account_id == Account.id).filter(JournalEntry.client_id == session['client_id'])

    categories = [c[0] for c in db.session.query(JournalEntry.category).filter(JournalEntry.client_id == session['client_id']).distinct().all() if c[0]]

    # Default to no filters, but retain filter values from form
    filters = {
        'start_date': request.form.get('start_date', ''),
        'end_date': request.form.get('end_date', ''),
        'description': request.form.get('description', ''),
        'account_id': request.form.get('account_id', ''),
        'categories': request.form.getlist('categories'),
        'transaction_type': request.form.get('transaction_type', '')
    }

    if request.method == 'POST':
        if filters['start_date']:
            query = query.filter(JournalEntry.date >= filters['start_date'])
        if filters['end_date']:
            query = query.filter(JournalEntry.date <= filters['end_date'])
        if filters['description']:
            query = query.filter(JournalEntry.description.ilike(f"%{filters['description']}"))
        if filters['account_id']:
            query = query.filter(db.or_(JournalEntry.debit_account_id == filters['account_id'], JournalEntry.credit_account_id == filters['account_id']))
        if filters['categories']:
            query = query.filter(JournalEntry.category.in_(filters['categories']))
        if filters['transaction_type']:
            query = query.filter(JournalEntry.transaction_type == filters['transaction_type'])

    # Sorting logic
    sort_by = request.args.get('sort', 'date')
    direction = request.args.get('direction', 'desc')

    sort_column = getattr(JournalEntry, sort_by, JournalEntry.date)
    if sort_by == 'debit_account':
        sort_column = JournalEntry.debit_account.has(Account.name)
    elif sort_by == 'credit_account':
        sort_column = JournalEntry.credit_account.has(Account.name)

    if direction == 'asc':
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    entries = query.all()
    account_choices = get_account_choices(session['client_id'])

    # Duplicate detection
    seen = set()
    duplicates = set()
    for entry in entries:
        key = (entry.date, entry.description.strip(), round(entry.amount, 2))
        if key in seen:
            duplicates.add(key)
        seen.add(key)

    for entry in entries:
        key = (entry.date, entry.description.strip(), round(entry.amount, 2))
        if key in duplicates:
            entry.is_duplicate = True
        else:
            entry.is_duplicate = False
    
    return render_template('journal.html', entries=entries, accounts=account_choices, filters=filters, categories=categories)

@journal_bp.route('/add_entry', methods=['POST'])
def add_entry():
    date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    description = request.form['description']
    debit_account_id = request.form['debit_account_id']
    credit_account_id = request.form['credit_account_id']
    amount = abs(float(request.form['amount']))
    category = request.form['category']
    notes = request.form.get('notes')
    new_entry = JournalEntry(date=date, description=description, debit_account_id=debit_account_id, credit_account_id=credit_account_id, amount=amount, category=category, notes=notes, client_id=session['client_id'])
    db.session.add(new_entry)
    db.session.commit()
    log_audit(f'Added journal entry: {new_entry.description}')
    flash('Journal entry added successfully.', 'success')
    return redirect(url_for('journal.journal'))

@journal_bp.route('/edit_entry/<int:entry_id>', methods=['GET', 'POST'])
def edit_entry(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.client_id != session['client_id']:
        return "Unauthorized", 403
    if request.method == 'POST':
        entry.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        entry.description = request.form['description']
        entry.debit_account_id = request.form['debit_account_id']
        entry.credit_account_id = request.form['credit_account_id']
        entry.amount = abs(float(request.form['amount']))
        entry.category = request.form['category']
        entry.notes = request.form.get('notes')
        db.session.commit()
        log_audit(f'Edited journal entry: {entry.description}')
        flash('Journal entry updated successfully.', 'success')
        return redirect(url_for('journal.journal'))
    else:
        account_choices = get_account_choices(session['client_id'])
        return render_template('edit_entry.html', entry=entry, accounts=account_choices)

@journal_bp.route('/delete_entry/<int:entry_id>')
def delete_entry(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.client_id != session['client_id']:
        return "Unauthorized", 403
    log_audit(f'Deleted journal entry: {entry.description}')
    if entry.transaction_id:
        transaction = Transaction.query.get(entry.transaction_id)
        if transaction:
            db.session.delete(transaction)
    else:
        # Try to find the transaction by matching fields for old entries
        transaction = Transaction.query.filter(
            Transaction.client_id == session['client_id'],
            Transaction.date == entry.date,
            Transaction.description == entry.description,
            func.abs(Transaction.amount) == entry.amount
        ).first()
        if transaction:
            db.session.delete(transaction)

    db.session.delete(entry)
    db.session.commit()
    flash('Journal entry deleted successfully.', 'success')
    return redirect(url_for('journal.journal'))

@journal_bp.route('/unapprove_transaction/<int:entry_id>')
def unapprove_transaction(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.client_id != session['client_id']:
        return "Unauthorized", 403

    if entry.transaction_id:
        transaction = Transaction.query.get(entry.transaction_id)
        if transaction:
            transaction.is_approved = False
    
    db.session.delete(entry)
    db.session.commit()

    flash('Transaction unapproved and sent back to the unapproved list.', 'success')
    return redirect(url_for('journal.journal'))

@journal_bp.route('/toggle_lock/<int:entry_id>')
def toggle_lock(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.client_id != session['client_id']:
        return "Unauthorized", 403
    entry.locked = not entry.locked
    db.session.commit()
    return redirect(url_for('journal.journal'))

@journal_bp.route('/bulk_actions', methods=['POST'])
def bulk_actions():
    entry_ids = request.form.getlist('entry_ids')
    action = request.form['action']

    if not entry_ids:
        flash('No entries selected.', 'warning')
        return redirect(url_for('journal.journal'))

    if action == 'delete':
        entries = JournalEntry.query.filter(JournalEntry.id.in_(entry_ids), JournalEntry.client_id == session['client_id']).all()
        transaction_ids_to_delete = [entry.transaction_id for entry in entries if entry.transaction_id]
        
        for entry in entries:
            db.session.delete(entry)
            
        if transaction_ids_to_delete:
            Transaction.query.filter(Transaction.id.in_(transaction_ids_to_delete)).delete(synchronize_session=False)
            
        db.session.commit()
        flash(f'{len(entries)} entries deleted successfully.', 'success')
    elif action == 'update_type':
        transaction_type = request.form.get('transaction_type')
        if not transaction_type:
            flash('No transaction type selected.', 'warning')
            return redirect(url_for('journal.journal'))
        
        JournalEntry.query.filter(JournalEntry.id.in_(entry_ids), JournalEntry.client_id == session['client_id']).update({'transaction_type': transaction_type}, synchronize_session=False)
        db.session.commit()
        flash(f'{len(entry_ids)} entries updated successfully.', 'success')
    elif action == 'lock':
        JournalEntry.query.filter(JournalEntry.id.in_(entry_ids), JournalEntry.client_id == session['client_id']).update({'locked': True}, synchronize_session=False)
        db.session.commit()
        flash(f'{len(entry_ids)} entries locked successfully.', 'success')
    elif action == 'unlock':
        JournalEntry.query.filter(JournalEntry.id.in_(entry_ids), JournalEntry.client_id == session['client_id']).update({'locked': False}, synchronize_session=False)
        db.session.commit()
        flash(f'{len(entry_ids)} entries unlocked successfully.', 'success')
    elif action == 'unapprove':
        entries = JournalEntry.query.filter(JournalEntry.id.in_(entry_ids), JournalEntry.client_id == session['client_id']).all()
        for entry in entries:
            if entry.transaction_id:
                transaction = Transaction.query.get(entry.transaction_id)
                if transaction:
                    transaction.is_approved = False
            db.session.delete(entry)
        db.session.commit()
        flash(f'{len(entries)} entries unapproved and sent back to the unapproved list.', 'success')
    
    return redirect(url_for('journal.journal'))

@journal_bp.route('/delete_duplicate_journal_entries')
def delete_duplicate_journal_entries():
    all_entries = JournalEntry.query.filter_by(client_id=session['client_id']).all()

    seen = {}
    duplicates_to_delete = []
    for entry in all_entries:
        key = (entry.date, entry.description.strip(), round(entry.amount, 2))
        if key in seen:
            duplicates_to_delete.append(entry.id)
        else:
            seen[key] = entry.id

    if duplicates_to_delete:
        JournalEntry.query.filter(JournalEntry.id.in_(duplicates_to_delete)).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{len(duplicates_to_delete)} duplicate journal entries deleted successfully.', 'success')
    else:
        flash('No duplicate journal entries found.', 'info')

    return redirect(url_for('journal.journal'))
