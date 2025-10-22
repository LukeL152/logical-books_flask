from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.models import Transaction, JournalEntry, Account, CategoryRule, TransactionRule, ImportTemplate
from datetime import datetime
from app.utils import get_account_choices, log_audit

transactions_bp = Blueprint('transactions', __name__)

@transactions_bp.route('/transactions')
def transactions():
    transactions = Transaction.query.options(db.joinedload(Transaction.source_account)).filter_by(client_id=session['client_id']).order_by(Transaction.date.desc()).all()
    return render_template('transactions.html', transactions=transactions)

@transactions_bp.route('/add_transaction', methods=['GET', 'POST'])
def add_transaction():
    if request.method == 'POST':
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        description = request.form['description']
        amount = abs(float(request.form['amount']))
        new_transaction = Transaction(
            date=date, 
            description=description, 
            amount=amount,
            client_id=session['client_id']
        )
        db.session.add(new_transaction)
        db.session.commit()
        flash('Transaction added successfully.', 'success')
        return redirect(url_for('transactions.transactions'))
    return render_template('add_transaction.html')

@transactions_bp.route('/edit_transaction/<int:transaction_id>', methods=['GET', 'POST'])
def edit_transaction(transaction_id):
    transaction = Transaction.query.options(db.joinedload(Transaction.source_account)).filter_by(id=transaction_id).first_or_404()
    if transaction.client_id != session['client_id']:
        return "Unauthorized", 403
    if request.method == 'POST':
        transaction.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        transaction.description = request.form['description']
        transaction.amount = abs(float(request.form['amount']))
        db.session.commit()
        flash('Transaction updated successfully.', 'success')
        return redirect(url_for('transactions.transactions'))
    return render_template('edit_transaction.html', transaction=transaction)

@transactions_bp.route('/delete_transaction/<int:transaction_id>')
def delete_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(transaction)
    db.session.commit()
    flash('Transaction deleted successfully.', 'success')
    return redirect(url_for('transactions.transactions'))

@transactions_bp.route('/delete_transactions', methods=['POST'])
def delete_transactions():
    transaction_ids = request.form.getlist('transaction_ids')
    if not transaction_ids:
        flash('No transactions selected.', 'warning')
        return redirect(url_for('transactions.transactions'))

    Transaction.query.filter(Transaction.id.in_(transaction_ids), Transaction.client_id == session['client_id']).delete(synchronize_session=False)
    db.session.commit()
    flash(f'{len(transaction_ids)} transactions deleted successfully.', 'success')
    return redirect(url_for('transactions.transactions'))

@transactions_bp.route('/cleanup_orphaned_transactions')
def cleanup_orphaned_transactions():
    orphaned_transactions = db.session.query(Transaction).outerjoin(JournalEntry, Transaction.id == JournalEntry.transaction_id).filter(Transaction.is_approved, JournalEntry.transaction_id.is_(None)).all()
    for transaction in orphaned_transactions:
        db.session.delete(transaction)
    db.session.commit()
    flash(f'{len(orphaned_transactions)} orphaned transactions have been deleted.', 'success')
    return redirect(url_for('transactions.transactions'))

@transactions_bp.route('/unapproved')
def unapproved_transactions():
    sort_by = request.args.get('sort', 'date')
    direction = request.args.get('direction', 'desc')

    sort_column = getattr(Transaction, sort_by, Transaction.date)

    base_query = Transaction.query.options(db.joinedload(Transaction.source_account)).filter_by(client_id=session['client_id'], is_approved=False)

    if direction == 'asc':
        base_query = base_query.order_by(sort_column.asc())
    else:
        base_query = base_query.order_by(sort_column.desc())
    
    all_transactions = base_query.all()

    # Get fingerprints of all existing journal entries
    journal_entries = JournalEntry.query.filter_by(client_id=session['client_id']).all()
    journal_fingerprints = set((je.date, je.description.strip(), round(je.amount, 2)) for je in journal_entries)

    # Duplicate detection
    for t in all_transactions:
        key = (t.date, t.description.strip(), round(abs(t.amount), 2))
        if key in journal_fingerprints:
            t.is_duplicate = True
        else:
            t.is_duplicate = False

    rule_modified_transactions = [t for t in all_transactions if t.rule_modified]
    unmodified_transactions = [t for t in all_transactions if not t.rule_modified]

    account_choices = get_account_choices(session['client_id'])
    return render_template('unapproved_transactions.html', rule_modified_transactions=rule_modified_transactions, unmodified_transactions=unmodified_transactions, accounts=account_choices)

@transactions_bp.route('/delete_duplicates')
def delete_duplicates():
    unapproved_transactions = Transaction.query.filter_by(client_id=session['client_id'], is_approved=False).all()
    journal_entries = JournalEntry.query.filter_by(client_id=session['client_id']).all()
    journal_fingerprints = set((je.date, je.description.strip(), round(je.amount, 2)) for je in journal_entries)

    duplicates_to_delete = []
    for t in unapproved_transactions:
        key = (t.date, t.description.strip(), round(abs(t.amount), 2))
        if key in journal_fingerprints:
            duplicates_to_delete.append(t.id)

    if duplicates_to_delete:
        Transaction.query.filter(Transaction.id.in_(duplicates_to_delete)).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{len(duplicates_to_delete)} duplicate transactions deleted successfully.', 'success')
    else:
        flash('No duplicate transactions found.', 'info')

    return redirect(url_for('transactions.unapproved_transactions'))

@transactions_bp.route('/approve_transactions', methods=['POST'])
def approve_transactions():
    transaction_ids = request.form.getlist('transaction_ids')
    for transaction_id in transaction_ids:
        transaction = Transaction.query.get_or_404(transaction_id)
        if transaction.client_id != session['client_id']:
            continue

        debit_account_id = request.form.get(f'debit_account_{transaction_id}')
        credit_account_id = request.form.get(f'credit_account_{transaction_id}')

        if not debit_account_id or not credit_account_id:
            flash(f'Debit and credit accounts must be selected for transaction {transaction.id}.', 'danger')
            continue

        new_entry = JournalEntry(
            date=transaction.date,
            description=transaction.description,
            debit_account_id=debit_account_id,
            credit_account_id=credit_account_id,
            amount=abs(transaction.amount),
            category=transaction.category,
            transaction_id=transaction.id,
            client_id=session['client_id']
        )
        db.session.add(new_entry)
        transaction.is_approved = True
        log_audit(f'Approved transaction and generated journal entry: {transaction.description}')

    db.session.commit()
    flash('Selected transactions approved and journal entries created.', 'success')
    return redirect(url_for('transactions.unapproved_transactions'))

@transactions_bp.route('/approve_transaction/<int:transaction_id>', methods=['POST'])
def approve_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.client_id != session['client_id']:
        return "Unauthorized", 403

    debit_account_id = request.form.get(f'debit_account_{transaction_id}')
    credit_account_id = request.form.get(f'credit_account_{transaction_id}')

    if not debit_account_id or not credit_account_id:
        flash(f'Debit and credit accounts must be selected for transaction {transaction.id}.', 'danger')
        return redirect(url_for('transactions.unapproved_transactions'))

    new_entry = JournalEntry(
        date=transaction.date,
        description=transaction.description,
        debit_account_id=debit_account_id,
        credit_account_id=credit_account_id,
        amount=abs(transaction.amount),
        category=transaction.category,
        transaction_id=transaction.id,
        client_id=session['client_id']
    )
    db.session.add(new_entry)
    transaction.is_approved = True
    log_audit(f'Approved transaction and generated journal entry: {transaction.description}')

    db.session.commit()
    flash('Transaction approved and journal entry created.', 'success')
    return redirect(url_for('transactions.unapproved_transactions'))

@transactions_bp.route('/delete_unapproved_transaction/<int:transaction_id>')
def delete_unapproved_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(transaction)
    db.session.commit()
    flash('Unapproved transaction deleted successfully.', 'success')
    return redirect(url_for('transactions.unapproved_transactions'))

@transactions_bp.route('/delete_unapproved_transactions', methods=['POST'])
def delete_unapproved_transactions():
    transaction_ids = request.form.getlist('transaction_ids')
    if not transaction_ids:
        flash('No transactions selected.', 'warning')
        return redirect(url_for('transactions.unapproved_transactions'))

    Transaction.query.filter(Transaction.id.in_(transaction_ids), Transaction.client_id == session['client_id']).delete(synchronize_session=False)
    db.session.commit()
    flash(f'{len(transaction_ids)} unapproved transactions deleted successfully.', 'success')
    return redirect(url_for('transactions.unapproved_transactions'))

@transactions_bp.route('/bulk_assign_accounts', methods=['POST'])
def bulk_assign_accounts():
    transaction_ids = request.form.getlist('transaction_ids')
    debit_account_id = request.form.get('bulk_debit_account_id')
    credit_account_id = request.form.get('bulk_credit_account_id')

    if not transaction_ids:
        flash('No transactions selected.', 'warning')
        return redirect(url_for('transactions.unapproved_transactions'))

    if not debit_account_id or not credit_account_id:
        flash('Please select both a debit and a credit account.', 'danger')
        return redirect(url_for('transactions.unapproved_transactions'))

    update_data = {
        'debit_account_id': debit_account_id,
        'credit_account_id': credit_account_id,
        'rule_modified': True
    }

    Transaction.query.filter(Transaction.id.in_(transaction_ids), Transaction.client_id == session['client_id']).update(update_data, synchronize_session=False)

    db.session.commit()
    flash(f'{len(transaction_ids)} transactions updated successfully.', 'success')
    return redirect(url_for('transactions.unapproved_transactions'))

@transactions_bp.route('/assign_accounts/<int:transaction_id>', methods=['POST'])
def assign_accounts(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.client_id != session['client_id']:
        return "Unauthorized", 403

    debit_account_id = request.form.get(f'debit_account_{transaction_id}')
    credit_account_id = request.form.get(f'credit_account_{transaction_id}')

    if not debit_account_id or not credit_account_id:
        flash('Debit and credit accounts must be selected.', 'danger')
        return redirect(url_for('transactions.unapproved_transactions'))

    transaction.debit_account_id = debit_account_id
    transaction.credit_account_id = credit_account_id
    transaction.rule_modified = True
    db.session.commit()

    flash('Accounts assigned successfully.', 'success')
    return redirect(url_for('transactions.unapproved_transactions'))

@transactions_bp.route('/run_unapproved_rules', methods=['POST'])
def run_unapproved_rules():
    unapproved_transactions = Transaction.query.filter_by(client_id=session['client_id'], is_approved=False).all()
    rules = TransactionRule.query.filter_by(client_id=session['client_id']).all()

    for transaction in unapproved_transactions:
        for rule in rules:
            # Check if the rule applies to the transaction
            if rule.keyword and rule.keyword.lower() not in transaction.description.lower():
                continue
            if rule.category_condition and rule.category_condition != transaction.category:
                continue
            if rule.transaction_type:
                if rule.transaction_type == 'debit' and transaction.amount < 0:
                    continue
                if rule.transaction_type == 'credit' and transaction.amount > 0:
                    continue
            if rule.min_amount and abs(transaction.amount) < rule.min_amount:
                continue
            if rule.max_amount and abs(transaction.amount) > rule.max_amount:
                continue
            if rule.source_account_id and rule.source_account_id != transaction.source_account_id:
                continue

            # Apply the rule
            if rule.new_category:
                transaction.category = rule.new_category
            if rule.new_description:
                transaction.description = rule.new_description
            if rule.new_debit_account_id:
                transaction.debit_account_id = rule.new_debit_account_id
            if rule.new_credit_account_id:
                transaction.credit_account_id = rule.new_credit_account_id
            if rule.delete_transaction:
                db.session.delete(transaction)
                continue
            
            transaction.rule_modified = True
            break  # Stop after the first matching rule

    db.session.commit()
    flash('Transaction rules re-applied to unapproved transactions.', 'success')
    return redirect(url_for('transactions.unapproved_transactions'))

from app.utils import get_account_choices, log_audit

@transactions_bp.route('/import', methods=['GET', 'POST'])
def import_page():
    accounts = get_account_choices(session['client_id'])
    account_map = {acc.id: acc for acc in Account.query.filter_by(client_id=session['client_id']).all()}
    return render_template('import.html', accounts=accounts, account_map=account_map)

@transactions_bp.route('/edit_template/<int:template_id>', methods=['GET', 'POST'])
def edit_template(template_id):
    template = ImportTemplate.query.get_or_404(template_id)
    if template.client_id != session.get('client_id'):
        flash('You do not have permission to edit this template.', 'danger')
        return redirect(url_for('transactions.import_page'))
    
    if request.method == 'POST':
        template.date_col = int(request.form['date_col'])
        template.description_col = int(request.form['description_col'])
        template.amount_col = int(request.form.get('amount_col')) if request.form.get('amount_col') else None
        template.debit_col = int(request.form.get('debit_col')) if request.form.get('debit_col') else None
        template.credit_col = int(request.form.get('credit_col')) if request.form.get('credit_col') else None
        template.category_col = int(request.form.get('category_col')) if request.form.get('category_col') else None
        template.notes_col = int(request.form.get('notes_col')) if request.form.get('notes_col') else None
        template.has_header = 'has_header' in request.form
        template.negate_amount = 'negate_amount' in request.form
        db.session.commit()
        flash('Import template updated successfully.', 'success')
        return redirect(url_for('transactions.import_page'))

    account = Account.query.get_or_404(template.account_id)
    return render_template('template_form.html', template=template, account=account)

@transactions_bp.route('/delete_template/<int:template_id>')
def delete_template(template_id):
    template = ImportTemplate.query.get_or_404(template_id)
    if template.client_id != session.get('client_id'):
        flash('You do not have permission to delete this template.', 'danger')
        return redirect(url_for('transactions.import_page'))
    db.session.delete(template)
    db.session.commit()
    flash('Import template deleted successfully.', 'success')
    return redirect(url_for('transactions.import_page'))

@transactions_bp.route('/add_template_for_account/<int:account_id>', methods=['GET', 'POST'])
def add_template_for_account(account_id):
    account = Account.query.get_or_404(account_id)
    if request.method == 'POST':
        new_template = ImportTemplate(
            account_id=account_id,
            client_id=session['client_id'],
            date_col=int(request.form['date_col']),
            description_col=int(request.form['description_col']),
            amount_col=int(request.form.get('amount_col')) if request.form.get('amount_col') else None,
            debit_col=int(request.form.get('debit_col')) if request.form.get('debit_col') else None,
            credit_col=int(request.form.get('credit_col')) if request.form.get('credit_col') else None,
            category_col=int(request.form.get('category_col')) if request.form.get('category_col') else None,
            notes_col=int(request.form.get('notes_col')) if request.form.get('notes_col') else None,
            has_header='has_header' in request.form,
            negate_amount='negate_amount' in request.form
        )
        db.session.add(new_template)
        db.session.commit()
        flash('Import template created successfully.', 'success')
        return redirect(url_for('transactions.import_page'))
    return render_template('template_form.html', account=account, template=None)

import csv
import io

@transactions_bp.route('/import_csv', methods=['POST'])
def import_csv():
    account_id = int(request.form['account'])
    files = request.files.getlist('csv_files')
    template = ImportTemplate.query.filter_by(account_id=account_id).first()

    if not template:
        flash('No import template found for the selected account.', 'danger')
        return redirect(url_for('transactions.import_page'))

    for file in files:
        if file and file.filename.endswith('.csv'):
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.reader(stream)
            
            if template.has_header:
                next(csv_reader, None)

            for row in csv_reader:
                try:
                    date = datetime.strptime(row[template.date_col], '%Y-%m-%d').date()
                    description = row[template.description_col]
                    
                    amount = 0
                    if template.amount_col is not None:
                        amount = float(row[template.amount_col])
                        if template.negate_amount:
                            amount = -amount
                    elif template.debit_col is not None and template.credit_col is not None:
                        debit = float(row[template.debit_col]) if row[template.debit_col] else 0
                        credit = float(row[template.credit_col]) if row[template.credit_col] else 0
                        amount = debit - credit

                    category = row[template.category_col] if template.category_col is not None else None

                    new_transaction = Transaction(
                        date=date,
                        description=description,
                        amount=amount,
                        category=category,
                        client_id=session['client_id'],
                        source_account_id=account_id
                    )
                    db.session.add(new_transaction)
                except (ValueError, IndexError) as e:
                    flash(f'Error processing row: {row}. Error: {e}', 'danger')
                    continue
    
    db.session.commit()
    flash('CSV files imported successfully.', 'success')
    return redirect(url_for('transactions.unapproved_transactions'))

@transactions_bp.route('/transaction_analysis')
def transaction_analysis_page():
    # Placeholder for transaction analysis logic
    return render_template('transaction_analysis.html')

@transactions_bp.route('/category_rules')
def category_rules():
    rules = CategoryRule.query.filter_by(client_id=session['client_id']).order_by(CategoryRule.name).all()
    accounts = get_account_choices(session['client_id'])
    return render_template('category_rules.html', rules=rules, accounts=accounts)

@transactions_bp.route('/add_category_rule', methods=['POST'])
def add_category_rule():
    name = request.form.get('name')
    keyword = request.form.get('keyword')
    condition = request.form.get('condition')
    value = request.form.get('value')
    category = request.form.get('category')
    debit_account_id = request.form.get('debit_account_id')
    credit_account_id = request.form.get('credit_account_id')

    new_rule = CategoryRule(
        name=name,
        keyword=keyword,
        condition=condition if condition else None,
        value=float(value) if value else None,
        category=category,
        debit_account_id=int(debit_account_id) if debit_account_id else None,
        credit_account_id=int(credit_account_id) if credit_account_id else None,
        client_id=session['client_id']
    )
    db.session.add(new_rule)
    db.session.commit()
    flash('Category rule added successfully.', 'success')
    return redirect(url_for('transactions.category_rules'))

@transactions_bp.route('/edit_category_rule/<int:rule_id>', methods=['GET', 'POST'])
def edit_category_rule(rule_id):
    rule = CategoryRule.query.get_or_404(rule_id)
    if rule.client_id != session.get('client_id'):
        flash('You do not have permission to edit this rule.', 'danger')
        return redirect(url_for('transactions.category_rules'))

    if request.method == 'POST':
        rule.name = request.form.get('name')
        rule.keyword = request.form.get('keyword')
        rule.condition = request.form.get('condition') if request.form.get('condition') else None
        rule.value = float(request.form.get('value')) if request.form.get('value') else None
        rule.category = request.form.get('category')
        rule.debit_account_id = int(request.form.get('debit_account_id')) if request.form.get('debit_account_id') else None
        rule.credit_account_id = int(request.form.get('credit_account_id')) if request.form.get('credit_account_id') else None
        db.session.commit()
        flash('Category rule updated successfully.', 'success')
        return redirect(url_for('transactions.category_rules'))

    accounts = get_account_choices(session['client_id'])
    return render_template('edit_category_rule.html', rule=rule, accounts=accounts)

@transactions_bp.route('/delete_category_rule/<int:rule_id>')
def delete_category_rule(rule_id):
    rule = CategoryRule.query.get_or_404(rule_id)
    if rule.client_id != session.get('client_id'):
        flash('You do not have permission to delete this rule.', 'danger')
        return redirect(url_for('transactions.category_rules'))
    db.session.delete(rule)
    db.session.commit()
    flash('Category rule deleted successfully.', 'success')
    return redirect(url_for('transactions.category_rules'))

@transactions_bp.route('/recurring_transactions')
def recurring_transactions():
    # Placeholder for recurring transactions logic
    return render_template('recurring_transactions.html')

@transactions_bp.route('/add_transaction_rule', methods=['GET', 'POST'])
def add_transaction_rule():
    if request.method == 'POST':
        new_rule = TransactionRule(
            keyword=request.form.get('keyword'),
            category_condition=request.form.get('category_condition'),
            transaction_type=request.form.get('transaction_type') if request.form.get('transaction_type') else None,
            min_amount=float(request.form.get('min_amount')) if request.form.get('min_amount') else None,
            max_amount=float(request.form.get('max_amount')) if request.form.get('max_amount') else None,
            new_category=request.form.get('new_category'),
            new_description=request.form.get('new_description'),
            new_debit_account_id=int(request.form.get('new_debit_account_id')) if request.form.get('new_debit_account_id') else None,
            new_credit_account_id=int(request.form.get('new_credit_account_id')) if request.form.get('new_credit_account_id') else None,
            is_automatic='is_automatic' in request.form,
            delete_transaction='delete_transaction' in request.form,
            client_id=session['client_id'],
            source_account_id=int(request.form.get('source_account_id')) if request.form.get('source_account_id') else None
        )
        db.session.add(new_rule)
        db.session.commit()
        flash('Transaction rule added successfully.', 'success')
        return redirect(url_for('transactions.transaction_rules'))

    accounts = get_account_choices(session['client_id'])
    return render_template('add_transaction_rule.html', accounts=accounts)

@transactions_bp.route('/edit_transaction_rule/<int:rule_id>', methods=['GET', 'POST'])
def edit_transaction_rule(rule_id):
    rule = TransactionRule.query.get_or_404(rule_id)
    if rule.client_id != session.get('client_id'):
        flash('You do not have permission to edit this rule.', 'danger')
        return redirect(url_for('transactions.transaction_rules'))

    if request.method == 'POST':
        rule.keyword = request.form.get('keyword')
        rule.category_condition = request.form.get('category_condition')
        rule.transaction_type = request.form.get('transaction_type') if request.form.get('transaction_type') else None
        rule.min_amount = float(request.form.get('min_amount')) if request.form.get('min_amount') else None
        rule.max_amount = float(request.form.get('max_amount')) if request.form.get('max_amount') else None
        rule.new_category = request.form.get('new_category')
        rule.new_description = request.form.get('new_description')
        rule.new_debit_account_id = int(request.form.get('new_debit_account_id')) if request.form.get('new_debit_account_id') else None
        rule.new_credit_account_id = int(request.form.get('new_credit_account_id')) if request.form.get('new_credit_account_id') else None
        rule.is_automatic = 'is_automatic' in request.form
        rule.delete_transaction = 'delete_transaction' in request.form
        rule.source_account_id = int(request.form.get('source_account_id')) if request.form.get('source_account_id') else None
        db.session.commit()
        flash('Transaction rule updated successfully.', 'success')
        return redirect(url_for('transactions.transaction_rules'))

    accounts = get_account_choices(session['client_id'])
    return render_template('edit_transaction_rule.html', rule=rule, accounts=accounts)

@transactions_bp.route('/delete_transaction_rule/<int:rule_id>')
def delete_transaction_rule(rule_id):
    rule = TransactionRule.query.get_or_404(rule_id)
    if rule.client_id != session.get('client_id'):
        flash('You do not have permission to delete this rule.', 'danger')
        return redirect(url_for('transactions.transaction_rules'))
    db.session.delete(rule)
    db.session.commit()
    flash('Transaction rule deleted successfully.', 'success')
    return redirect(url_for('transactions.transaction_rules'))

@transactions_bp.route('/transaction_rules')
def transaction_rules():
    rules = TransactionRule.query.filter_by(client_id=session['client_id']).all()
    rules_by_source = {}
    for rule in rules:
        source_account_name = rule.source_account.name if rule.source_account else 'All Accounts'
        if source_account_name not in rules_by_source:
            rules_by_source[source_account_name] = []
        rules_by_source[source_account_name].append(rule)
    return render_template('transaction_rules.html', rules_by_source=rules_by_source)
