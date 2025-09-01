from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_apscheduler import APScheduler
import csv
import io
from datetime import datetime, timedelta
from collections import defaultdict
import json
import markdown

import os

from markupsafe import Markup

app = Flask(__name__)

@app.template_filter('nl2br')
def nl2br(s):
    return Markup(s.replace('\n', '<br>\n')) if s else ''

app.config['SECRET_KEY'] = 'your_secret_key'  # Change this in a real application
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'bookkeeping.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contact_name = db.Column(db.String(100), nullable=False)
    business_name = db.Column(db.String(100), unique=True)
    contact_email = db.Column(db.String(120))
    contact_phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    entity_structure = db.Column(db.String(50))
    services_offered = db.Column(db.Text)
    payment_method = db.Column(db.String(50))
    billing_cycle = db.Column(db.String(50))
    client_status = db.Column(db.String(20), default='Active')
    notes = db.Column(db.Text)

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    client = db.relationship('Client', backref=db.backref('users', lazy=True))
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    role = db.relationship('Role', backref=db.backref('users', lazy=True))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False) # Asset, Liability, Equity, Revenue, Expense, Accounts Receivable, Accounts Payable, Inventory, Fixed Asset, Accumulated Depreciation, Long-Term Debt
    opening_balance = db.Column(db.Float, nullable=True, default=0.0)
    category = db.Column(db.String(100), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    children = db.relationship('Account', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')

class JournalEntry(db.Model):
    __tablename__ = 'journal_entries'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    description = db.Column(db.String(200))
    debit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    credit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100))
    notes = db.Column(db.String(500), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    locked = db.Column(db.Boolean, nullable=False, default=False)
    is_accrual = db.Column(db.Boolean, nullable=True, default=False)
    is_reversing = db.Column(db.Boolean, nullable=False, default=False)
    reversal_date = db.Column(db.String(10), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='posted') # posted, voided
    transaction_type = db.Column(db.String(20), nullable=True)
    debit_account = db.relationship('Account', foreign_keys=[debit_account_id])
    credit_account = db.relationship('Account', foreign_keys=[credit_account_id])
    documents = db.relationship('Document', backref='journal_entry', cascade="all, delete-orphan")

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

class ImportTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False, unique=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    date_col = db.Column(db.Integer, nullable=False)
    description_col = db.Column(db.Integer, nullable=False)
    amount_col = db.Column(db.Integer)
    debit_col = db.Column(db.Integer)
    credit_col = db.Column(db.Integer)
    category_col = db.Column(db.Integer)
    notes_col = db.Column(db.Integer)
    has_header = db.Column(db.Boolean, nullable=False, default=False)
    negate_amount = db.Column(db.Boolean, nullable=False, default=False)
    account = db.relationship('Account', backref=db.backref('import_template', uselist=False, cascade="all, delete-orphan"))

class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

class RuleAccountLink(db.Model):
    __tablename__ = 'rule_account_link'
    rule_id = db.Column(db.Integer, db.ForeignKey('rule.id'), primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), primary_key=True)
    is_exclusion = db.Column(db.Boolean, nullable=False, default=False)

class Rule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    keyword = db.Column(db.String(100), nullable=True)
    condition = db.Column(db.String(20), nullable=True)
    value = db.Column(db.Float, nullable=True)
    category = db.Column(db.String(100), nullable=True)
    transaction_type = db.Column(db.String(20), nullable=True)
    debit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    credit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    is_automatic = db.Column(db.Boolean, nullable=False, default=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    accounts = db.relationship('RuleAccountLink', backref='rule', cascade="all, delete-orphan")
    debit_account = db.relationship('Account', foreign_keys=[debit_account_id])
    credit_account = db.relationship('Account', foreign_keys=[credit_account_id])

class FinancialPeriod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.String(10), nullable=False)
    end_date = db.Column(db.String(10), nullable=False)
    is_closed = db.Column(db.Boolean, nullable=False, default=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

class CategoryRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    keyword = db.Column(db.String(100), nullable=True)
    condition = db.Column(db.String(20), nullable=True)
    value = db.Column(db.Float, nullable=True)
    category = db.Column(db.String(100), nullable=False)
    debit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    credit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    debit_account = db.relationship('Account', foreign_keys=[debit_account_id])
    credit_account = db.relationship('Account', foreign_keys=[credit_account_id])


class FixedAsset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    purchase_date = db.Column(db.String(10), nullable=False)
    cost = db.Column(db.Float, nullable=False)
    useful_life = db.Column(db.Integer, nullable=False) # in years
    salvage_value = db.Column(db.Float, nullable=False, default=0.0)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

class Depreciation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    fixed_asset_id = db.Column(db.Integer, db.ForeignKey('fixed_asset.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    cost = db.Column(db.Float, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    product = db.relationship('Product', backref='inventory_item', uselist=False)

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    product = db.relationship('Product', backref='sales')

class RecurringTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    amount = db.Column(db.Float, nullable=False)
    frequency = db.Column(db.String(20), nullable=False) # daily, weekly, monthly, yearly
    start_date = db.Column(db.String(10), nullable=False)
    end_date = db.Column(db.String(10))
    debit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    credit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    description = db.Column(db.String(200))
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    is_approved = db.Column(db.Boolean, nullable=False, default=False)
    debit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    credit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    rule_modified = db.Column(db.Boolean, nullable=False, default=False)

class AuditTrail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    action = db.Column(db.String(200), nullable=False)
    user = db.relationship('Client', backref='audit_trails')

# Schedule the depreciation calculation job
@scheduler.task('cron', id='calculate_depreciation', day=1, hour=0)
def scheduled_depreciation():
    calculate_and_record_depreciation()

@scheduler.task('cron', id='reverse_accruals', day=1, hour=0)
def scheduled_reversal():
    reverse_accruals()

@scheduler.task('cron', id='create_recurring_journal_entries', day=1, hour=0)
def create_recurring_journal_entries():
    with app.app_context():
        today = datetime.now()
        recurring_transactions = RecurringTransaction.query.filter_by(client_id=session['client_id']).all()
        for transaction in recurring_transactions:
            # Check if the transaction is due
            start_date = datetime.strptime(transaction.start_date, '%Y-%m-%d')
            if transaction.end_date:
                end_date = datetime.strptime(transaction.end_date, '%Y-%m-%d')
                if today < start_date or today > end_date:
                    continue
            elif today < start_date:
                continue

            # Check if a journal entry has already been created for the current period
            last_journal_entry = JournalEntry.query.filter_by(description=transaction.description).order_by(JournalEntry.date.desc()).first()
            if last_journal_entry:
                last_journal_entry_date = datetime.strptime(last_journal_entry.date, '%Y-%m-%d')
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
                date=today.strftime('%Y-%m-%d'),
                description=transaction.description,
                debit_account_id=transaction.debit_account_id,
                credit_account_id=transaction.credit_account_id,
                amount=abs(transaction.amount),
                client_id=session['client_id']
            )
            db.session.add(new_entry)
        db.session.commit()



























@app.route('/transactions')
def transactions():
    transactions = Transaction.query.filter_by(client_id=session['client_id']).order_by(Transaction.date.desc()).all()
    return render_template('transactions.html', transactions=transactions)

@app.route('/add_transaction', methods=['GET', 'POST'])
def add_transaction():
    if request.method == 'POST':
        date = request.form['date']
        description = request.form['description']
        amount = abs(float(request.form['amount']))
        new_transaction = Transaction(date=date, description=description, amount=amount, client_id=session['client_id'])
        db.session.add(new_transaction)
        db.session.commit()
        flash('Transaction added successfully.', 'success')
        return redirect(url_for('transactions'))
    return render_template('add_transaction.html')

@app.route('/edit_transaction/<int:transaction_id>', methods=['GET', 'POST'])
def edit_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.client_id != session['client_id']:
        return "Unauthorized", 403
    if request.method == 'POST':
        transaction.date = request.form['date']
        transaction.description = request.form['description']
        transaction.amount = abs(float(request.form['amount']))
        db.session.commit()
        flash('Transaction updated successfully.', 'success')
        return redirect(url_for('transactions'))
    return render_template('edit_transaction.html', transaction=transaction)

@app.route('/delete_transaction/<int:transaction_id>')
def delete_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(transaction)
    db.session.commit()
    flash('Transaction deleted successfully.', 'success')
    return redirect(url_for('transactions'))

@app.route('/unapproved')
def unapproved_transactions():
    rule_modified_transactions = Transaction.query.filter_by(client_id=session['client_id'], is_approved=False, rule_modified=True).order_by(Transaction.date.desc()).all()
    unmodified_transactions = Transaction.query.filter_by(client_id=session['client_id'], is_approved=False, rule_modified=False).order_by(Transaction.date.desc()).all()
    account_choices = get_account_choices(session['client_id'])
    return render_template('unapproved_transactions.html', rule_modified_transactions=rule_modified_transactions, unmodified_transactions=unmodified_transactions, accounts=account_choices)



@app.route('/approve_transactions', methods=['POST'])
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
            client_id=session['client_id']
        )
        db.session.add(new_entry)
        transaction.is_approved = True
        log_audit(f'Approved transaction and generated journal entry: {transaction.description}')

    db.session.commit()
    flash('Selected transactions approved and journal entries created.', 'success')
    return redirect(url_for('unapproved_transactions'))

@app.route('/delete_unapproved_transaction/<int:transaction_id>')
def delete_unapproved_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(transaction)
    db.session.commit()
    flash('Unapproved transaction deleted successfully.', 'success')
    return redirect(url_for('unapproved_transactions'))

@app.route('/delete_unapproved_transactions', methods=['POST'])
def delete_unapproved_transactions():
    transaction_ids = request.form.getlist('transaction_ids')
    if not transaction_ids:
        flash('No transactions selected.', 'warning')
        return redirect(url_for('unapproved_transactions'))

    Transaction.query.filter(Transaction.id.in_(transaction_ids), Transaction.client_id == session['client_id']).delete(synchronize_session=False)
    db.session.commit()
    flash(f'{len(transaction_ids)} unapproved transactions deleted successfully.', 'success')
    return redirect(url_for('unapproved_transactions'))


def run_category_rules(transactions):
    all_rules = CategoryRule.query.filter_by(client_id=session['client_id']).order_by(CategoryRule.id).all()
    for transaction in transactions:
        for rule in all_rules:
            normalized_description = ' '.join(transaction.description.lower().split())
            normalized_keyword = ' '.join(rule.keyword.lower().split()) if rule.keyword else None

            keyword_match = False
            if normalized_keyword:
                keyword_match = normalized_keyword in normalized_description
            
            condition_match = False
            if rule.condition and rule.value is not None:
                if rule.condition == 'less_than' and transaction.amount < rule.value:
                    condition_match = True
                elif rule.condition == 'greater_than' and transaction.amount > rule.value:
                    condition_match = True
                elif rule.condition == 'equals' and transaction.amount == rule.value:
                    condition_match = True

            apply_rule = False
            if rule.keyword and (rule.condition and rule.value is not None):
                if keyword_match and condition_match:
                    apply_rule = True
            elif rule.keyword:
                if keyword_match:
                    apply_rule = True
            elif rule.condition and rule.value is not None:
                if condition_match:
                    apply_rule = True

            if apply_rule:
                if rule.debit_account_id:
                    transaction.debit_account_id = rule.debit_account_id
                if rule.credit_account_id:
                    transaction.credit_account_id = rule.credit_account_id
                transaction.rule_modified = True

@app.route('/run_unapproved_rules', methods=['POST'])
def run_unapproved_rules():
    transactions_to_update = Transaction.query.filter_by(is_approved=False, client_id=session['client_id']).all()
    all_rules = Rule.query.filter_by(client_id=session['client_id']).order_by(Rule.id).all()
    updated_count = 0
    for transaction in transactions_to_update:
        applicable_rules = []
        for rule in all_rules:
            if not rule.accounts:
                applicable_rules.append(rule)
                continue
            applicable_rules.append(rule)

        for rule in applicable_rules:
            normalized_description = ' '.join(transaction.description.lower().split())
            normalized_keyword = ' '.join(rule.keyword.lower().split()) if rule.keyword else None

            keyword_match = False
            if normalized_keyword:
                keyword_match = normalized_keyword in normalized_description
            
            condition_match = False
            if rule.condition and rule.value is not None:
                if rule.condition == 'less_than' and transaction.amount < rule.value:
                    condition_match = True
                elif rule.condition == 'greater_than' and transaction.amount > rule.value:
                    condition_match = True
                elif rule.condition == 'equals' and transaction.amount == rule.value:
                    condition_match = True

            apply_rule = False
            if rule.keyword and (rule.condition and rule.value is not None):
                if keyword_match and condition_match:
                    apply_rule = True
            elif rule.keyword:
                if keyword_match:
                    apply_rule = True
            elif rule.condition and rule.value is not None:
                if condition_match:
                    apply_rule = True

            if apply_rule:
                if rule.debit_account_id:
                    transaction.debit_account_id = rule.debit_account_id
                if rule.credit_account_id:
                    transaction.credit_account_id = rule.credit_account_id
                transaction.rule_modified = True
                updated_count += 1
    run_category_rules(transactions_to_update)
    db.session.commit()
    flash(f'{updated_count} transactions updated successfully based on rules.', 'success')
    return redirect(url_for('unapproved_transactions'))


@app.route('/audit_trail')
def audit_trail():
    logs = AuditTrail.query.filter_by(user_id=session['client_id']).order_by(AuditTrail.date.desc()).all()
    return render_template('audit_trail.html', logs=logs)

def log_audit(action):
    if 'client_id' in session:
        audit_log = AuditTrail(user_id=session['client_id'], action=action)
        db.session.add(audit_log)


def col_to_index(col_name):
    """Converts a column name (e.g., 'A', 'B', 'AA') to a zero-based index."""
    if not col_name:
        return None
    index = 0
    for char in col_name.upper():
        index = index * 26 + (ord(char) - ord('A') + 1)
    return index - 1

def index_to_col(index):
    """Converts a zero-based index to a column name (e.g., 0 -> 'A', 1 -> 'B')."""
    if index is None:
        return ''
    col = ''
    while index >= 0:
        col = chr(ord('A') + index % 26) + col
        index = index // 26 - 1
    return col

def normalize_date(date_str):
    """Parses a date string from common formats and returns YYYY-MM-DD."""
    if not date_str:
        return None
    formats_to_try = [
        '%Y-%m-%d',  # YYYY-MM-DD
        '%m/%d/%Y',  # MM/DD/YYYY
        '%d-%b-%Y',  # DD-Mon-YYYY (e.g., 25-Jul-2023)
        '%d-%B-%Y',  # DD-Month-YYYY (e.g., 25-July-2023)
        '%m/%d/%y',  # MM/DD/YY
    ]
    for fmt in formats_to_try:
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    # If no format matches, raise an error or return original string
    # depending on desired strictness.
    raise ValueError(f"Date format for '{date_str}' not recognized.")

@app.before_request
def before_request():
    if 'client_id' not in session and request.endpoint not in ['clients', 'add_client', 'select_client', 'edit_client', 'delete_client']:
        return redirect(url_for('clients'))

@app.route('/clients')
def clients():
    clients = Client.query.all()
    return render_template('clients.html', clients=clients)

@app.route('/client/<int:client_id>')
def client_detail(client_id):
    client = Client.query.get_or_404(client_id)
    return render_template('client_detail.html', client=client)

@app.route('/add_client', methods=['GET', 'POST'])
def add_client():
    if request.method == 'POST':
        if Client.query.filter_by(business_name=request.form['business_name']).first():
            flash(f'Client "{request.form["business_name"]}" already exists.', 'danger')
            return redirect(url_for('clients'))
        new_client = Client(
            contact_name=request.form['contact_name'],
            business_name=request.form['business_name'],
            contact_email=request.form['contact_email'],
            contact_phone=request.form['contact_phone'],
            address=request.form['address'],
            entity_structure=request.form['entity_structure'],
            services_offered=request.form['services_offered'],
            payment_method=request.form['payment_method'],
            billing_cycle=request.form['billing_cycle'],
            client_status=request.form['client_status'],
            notes=request.form['notes']
        )
        db.session.add(new_client)
        db.session.commit()
        flash(f'Client "{new_client.business_name}" created successfully.', 'success')
        return redirect(url_for('clients'))
    return render_template('add_client.html')

@app.route('/select_client/<int:client_id>')
def select_client(client_id):
    session['client_id'] = client_id
    return redirect(url_for('index'))

@app.route('/edit_client/<int:client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)
    if request.method == 'POST':
        if Client.query.filter(Client.business_name == request.form['business_name'], Client.id != client_id).first():
            flash(f'Client with business name "{request.form["business_name"]}" already exists.', 'danger')
            return redirect(url_for('edit_client', client_id=client_id))
        
        client.contact_name = request.form['contact_name']
        client.business_name = request.form['business_name']
        client.contact_email = request.form['contact_email']
        client.contact_phone = request.form['contact_phone']
        client.address = request.form['address']
        client.entity_structure = request.form['entity_structure']
        client.services_offered = request.form['services_offered']
        client.payment_method = request.form['payment_method']
        client.billing_cycle = request.form['billing_cycle']
        client.client_status = request.form['client_status']
        client.notes = request.form['notes']
        
        db.session.commit()
        flash('Client updated successfully.', 'success')
        return redirect(url_for('clients'))
    else:
        return render_template('edit_client.html', client=client)

@app.route('/delete_client/<int:client_id>')
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    # Delete all data associated with the client first
    JournalEntry.query.filter_by(client_id=client_id).delete()
    ImportTemplate.query.filter_by(client_id=client_id).delete()
    Account.query.filter_by(client_id=client_id).delete()
    Budget.query.filter_by(client_id=client_id).delete()
    Rule.query.filter_by(client_id=client_id).delete()
    db.session.delete(client)
    db.session.commit()
    flash('Client deleted successfully.', 'success')
    # Clear the session if the deleted client was the active one
    if session.get('client_id') == client_id:
        session.pop('client_id', None)
    return redirect(url_for('clients'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    today = datetime.now()
    start_date = None
    end_date = today

    if request.method == 'POST':
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
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
    
    # Ensure start_date is a datetime object
    if not isinstance(start_date, datetime):
        start_date = datetime.strptime(start_date.strftime('%Y-%m-%d'), '%Y-%m-%d')

    # Convert to string for database query
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')

    # Monthly data for bar chart
    monthly_data_query = db.session.query(
        db.func.strftime('%Y-%m', JournalEntry.date).label('month'),
        Account.type,
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.debit_account_id == Account.id).filter(
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date_str,
        JournalEntry.date <= end_date_str
    ).group_by('month', Account.type)

    monthly_data = monthly_data_query.all()

    bar_chart_data = defaultdict(lambda: {'income': 0, 'expense': 0})
    for month, acc_type, total in monthly_data:
        if acc_type in ['Revenue', 'Income']:
            bar_chart_data[month]['income'] += total
        elif acc_type == 'Expense':
            bar_chart_data[month]['expense'] += total
    
    sorted_months = sorted(bar_chart_data.keys())
    bar_chart_labels = json.dumps(sorted_months)
    bar_chart_income = json.dumps([bar_chart_data[m]['income'] for m in sorted_months])
    bar_chart_expense = json.dumps([bar_chart_data[m]['expense'] for m in sorted_months])

    # Expense breakdown for the selected period for the pie chart
    expense_breakdown_query = db.session.query(
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date_str,
        JournalEntry.date <= end_date_str,
        JournalEntry.category is not None,
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
        JournalEntry.date >= start_date_str,
        JournalEntry.date <= end_date_str,
        JournalEntry.category is not None,
        JournalEntry.category != ''
    ).group_by(JournalEntry.category)

    income_breakdown = income_breakdown_query.all()

    income_pie_chart_labels = json.dumps([item.category for item in income_breakdown])
    income_pie_chart_data = json.dumps([item.total for item in income_breakdown])

    # KPIs for the selected period
    income_this_period = db.session.query(db.func.sum(JournalEntry.amount)).join(Account, JournalEntry.credit_account_id == Account.id).filter(
        JournalEntry.client_id == session['client_id'],
        Account.type.in_(['Revenue', 'Income']),
        JournalEntry.date >= start_date_str,
        JournalEntry.date <= end_date_str
    ).scalar() or 0
    
    expenses_this_period = db.session.query(db.func.sum(JournalEntry.amount)).join(Account, JournalEntry.debit_account_id == Account.id).filter(
        JournalEntry.client_id == session['client_id'],
        Account.type == 'Expense',
        JournalEntry.date >= start_date_str,
        JournalEntry.date <= end_date_str
    ).scalar() or 0

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
        asset_balances[account.name] = account.opening_balance + credits - debits

    liability_balances = {}
    for account in liability_accounts:
        debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id == account.id).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id == account.id).scalar() or 0
        liability_balances[account.name] = account.opening_balance - credits + debits

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
                           end_date=end_date.strftime('%Y-%m-%d'))

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/bookkeeping_guide')
def bookkeeping_guide():
    try:
        with open('BOOKKEEPING_GUIDE.md', 'r') as f:
            content = f.read()
        guide_content = markdown.markdown(content, extensions=['tables'])
    except FileNotFoundError:
        guide_content = "<p>Error: BOOKKEEPING_GUIDE.md not found.</p>"
    return render_template('bookkeeping_guide.html', guide_content=guide_content)

@app.route('/category_transactions/<category_name>')
def category_transactions(category_name):
    entries = JournalEntry.query.filter_by(category=category_name, client_id=session['client_id']).order_by(JournalEntry.date.desc()).all()
    return render_template('category_transactions.html', entries=entries, category_name=category_name)

@app.route('/full_pie_chart_expenses')
def full_pie_chart_expenses():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    expense_breakdown_query = db.session.query(
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).filter(
        JournalEntry.transaction_type == 'expense',
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date,
        JournalEntry.date <= end_date,
        JournalEntry.category is not None,
        JournalEntry.category != ''
    ).group_by(JournalEntry.category)

    expense_breakdown = expense_breakdown_query.all()

    pie_chart_labels = json.dumps([item.category for item in expense_breakdown])
    pie_chart_data = json.dumps([item.total for item in expense_breakdown])

    return render_template('full_pie_chart.html', title='Expense Breakdown', labels=pie_chart_labels, data=pie_chart_data)

@app.route('/full_pie_chart_income')
def full_pie_chart_income():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    income_breakdown_query = db.session.query(
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).filter(
        JournalEntry.transaction_type == 'income',
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date,
        JournalEntry.date <= end_date,
        JournalEntry.category is not None,
        JournalEntry.category != ''
    ).group_by(JournalEntry.category)

    income_breakdown = income_breakdown_query.all()

    pie_chart_labels = json.dumps([item.category for item in income_breakdown])
    pie_chart_data = json.dumps([item.total for item in income_breakdown])

    return render_template('full_pie_chart.html', title='Income Breakdown', labels=pie_chart_labels, data=pie_chart_data)

@app.route('/accounts')
def accounts():
    accounts = Account.query.filter_by(client_id=session['client_id'], parent_id=None).order_by(Account.name).all()
    account_choices = get_account_choices(session['client_id'])
    return render_template('accounts.html', accounts=accounts, account_choices=account_choices)

@app.route('/add_account', methods=['POST'])
def add_account():
    name = request.form['name']
    account_type = request.form['type']
    category = request.form.get('category')
    opening_balance = float(request.form['opening_balance'])
    parent_id = request.form.get('parent_id')
    if parent_id == 'None':
        parent_id = None
    else:
        parent_id = int(parent_id)

    if Account.query.filter_by(name=name, client_id=session['client_id']).first():
        flash(f'Account "{name}" already exists.', 'danger')
        return redirect(url_for('accounts'))
    new_account = Account(name=name, type=account_type, category=category, opening_balance=opening_balance, parent_id=parent_id, client_id=session['client_id'])
    db.session.add(new_account)
    db.session.commit()
    flash(f'Account "{name}" created successfully.', 'success')
    return redirect(url_for('accounts'))

@app.route('/edit_account/<int:account_id>', methods=['GET', 'POST'])
def edit_account(account_id):
    account = Account.query.get_or_404(account_id)
    if account.client_id != session['client_id']:
        return "Unauthorized", 403

    if request.method == 'POST':
        name = request.form['name']
        parent_id = request.form.get('parent_id')

        if parent_id == 'None' or parent_id == "''":
            parent_id = None
        else:
            parent_id = int(parent_id)

        # Prevent setting an account as its own parent
        if parent_id == account.id:
            flash('An account cannot be its own parent.', 'danger')
            return redirect(url_for('edit_account', account_id=account_id))

        # A more complex check would be needed to prevent circular dependencies
        # (e.g., setting parent to one of its own children), but this covers the direct case.

        if Account.query.filter(Account.name == name, Account.id != account_id, Account.client_id == session['client_id']).first():
            flash(f'Account "{name}" already exists.', 'danger')
            return redirect(url_for('edit_account', account_id=account_id))
        
        account.name = name
        account.type = request.form['type']
        account.category = request.form.get('category')
        account.opening_balance = float(request.form['opening_balance'])
        account.parent_id = parent_id
        db.session.commit()
        flash('Account updated successfully.', 'success')
        return redirect(url_for('accounts'))
    else:
        account_choices = get_account_choices(session['client_id'])
        return render_template('edit_account.html', account=account, account_choices=account_choices)

@app.route('/delete_account/<int:account_id>')
def delete_account(account_id):
    account = Account.query.get_or_404(account_id)
    if account.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(account)
    db.session.commit()
    flash('Account deleted successfully.', 'success')
    return redirect(url_for('accounts'))

@app.route('/journal', methods=['GET', 'POST'])
def journal():
    query = db.session.query(JournalEntry).join(Account, JournalEntry.debit_account_id == Account.id).filter(JournalEntry.client_id == session['client_id'])

    # Default to no filters, but retain filter values from form
    filters = {
        'start_date': request.form.get('start_date', ''),
        'end_date': request.form.get('end_date', ''),
        'description': request.form.get('description', ''),
        'account_id': request.form.get('account_id', ''),
        'category': request.form.get('category', ''),
        'transaction_type': request.form.get('transaction_type', '')
    }

    if request.method == 'POST':
        if filters['start_date']:
            query = query.filter(JournalEntry.date >= filters['start_date'])
        if filters['end_date']:
            query = query.filter(JournalEntry.date <= filters['end_date'])
        if filters['description']:
            query = query.filter(JournalEntry.description.ilike(f"%{filters['description']}%"))
        if filters['account_id']:
            query = query.filter(JournalEntry.account_id == filters['account_id'])
        if filters['category']:
            query = query.filter(JournalEntry.category.ilike(f"%{filters['category']}%"))
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
    
    return render_template('journal.html', entries=entries, accounts=account_choices, filters=filters)

@app.route('/add_entry', methods=['POST'])
def add_entry():
    date = request.form['date']
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
    return redirect(url_for('journal'))

@app.route('/edit_entry/<int:entry_id>', methods=['GET', 'POST'])
def edit_entry(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.client_id != session['client_id']:
        return "Unauthorized", 403
    if request.method == 'POST':
        entry.date = request.form['date']
        entry.description = request.form['description']
        entry.debit_account_id = request.form['debit_account_id']
        entry.credit_account_id = request.form['credit_account_id']
        entry.amount = abs(float(request.form['amount']))
        entry.category = request.form['category']
        entry.notes = request.form.get('notes')
        db.session.commit()
        log_audit(f'Edited journal entry: {entry.description}')
        flash('Journal entry updated successfully.', 'success')
        return redirect(url_for('journal'))
    else:
        account_choices = get_account_choices(session['client_id'])
        return render_template('edit_entry.html', entry=entry, accounts=account_choices)

@app.route('/delete_entry/<int:entry_id>')
def delete_entry(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.client_id != session['client_id']:
        return "Unauthorized", 403
    log_audit(f'Deleted journal entry: {entry.description}')
    db.session.delete(entry)
    db.session.commit()
    flash('Journal entry deleted successfully.', 'success')
    return redirect(url_for('journal'))

@app.route('/toggle_lock/<int:entry_id>')
def toggle_lock(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.client_id != session['client_id']:
        return "Unauthorized", 403
    entry.locked = not entry.locked
    db.session.commit()
    return redirect(url_for('journal'))

@app.route('/bulk_actions', methods=['POST'])
def bulk_actions():
    entry_ids = request.form.getlist('entry_ids')
    action = request.form['action']

    if not entry_ids:
        flash('No entries selected.', 'warning')
        return redirect(url_for('journal'))

    if action == 'delete':
        JournalEntry.query.filter(JournalEntry.id.in_(entry_ids), JournalEntry.client_id == session['client_id']).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{len(entry_ids)} entries deleted successfully.', 'success')
    elif action == 'update_type':
        transaction_type = request.form.get('transaction_type')
        if not transaction_type:
            flash('No transaction type selected.', 'warning')
            return redirect(url_for('journal'))
        
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
    elif action == 'apply_rules':
        entries_to_update = JournalEntry.query.filter(JournalEntry.id.in_(entry_ids), JournalEntry.client_id == session['client_id']).all()
        all_rules = Rule.query.filter_by(client_id=session['client_id']).order_by(Rule.id).all()
        updated_count = 0
        for entry in entries_to_update:
            applicable_rules = []
            for rule in all_rules:
                if not rule.accounts:
                    applicable_rules.append(rule)
                    continue
                applicable_rules.append(rule)

            for rule in applicable_rules:
                normalized_description = ' '.join(entry.description.lower().split())
                normalized_keyword = ' '.join(rule.keyword.lower().split()) if rule.keyword else None

                keyword_match = False
                if normalized_keyword:
                    keyword_match = normalized_keyword in normalized_description
                
                condition_match = False
                if rule.condition and rule.value is not None:
                    if rule.condition == 'less_than' and entry.amount < rule.value:
                        condition_match = True
                    elif rule.condition == 'greater_than' and entry.amount > rule.value:
                        condition_match = True
                    elif rule.condition == 'equals' and entry.amount == rule.value:
                        condition_match = True

                apply_rule = False
                if rule.keyword and (rule.condition and rule.value is not None):
                    if keyword_match and condition_match:
                        apply_rule = True
                elif rule.keyword:
                    if keyword_match:
                        apply_rule = True
                elif rule.condition and rule.value is not None:
                    if condition_match:
                        apply_rule = True

                if apply_rule:
                    if rule.category:
                        entry.category = rule.category
                    if rule.transaction_type:
                        entry.transaction_type = rule.transaction_type
                    if rule.debit_account_id:
                        entry.debit_account_id = rule.debit_account_id
                    if rule.credit_account_id:
                        entry.credit_account_id = rule.credit_account_id
                    updated_count += 1
        db.session.commit()
        flash(f'{updated_count} entries updated successfully based on rules.', 'success')
    
    return redirect(url_for('journal'))

@app.route('/import', methods=['GET'])
def import_page():
    account_choices = get_account_choices(session['client_id'])
    accounts = Account.query.filter_by(client_id=session['client_id']).all()
    account_map = {account.id: account for account in accounts}
    return render_template('import.html', accounts=account_choices, account_map=account_map)

@app.route('/add_template_for_account/<int:account_id>')
def add_template_for_account(account_id):
    account = Account.query.get_or_404(account_id)
    if account.client_id != session['client_id']:
        return "Unauthorized", 403
    
    # Redirect to edit if template already exists
    if account.import_template:
        return redirect(url_for('edit_template', template_id=account.import_template.id))

    # Otherwise, create a new blank template and redirect to edit
    new_template = ImportTemplate(
        account_id=account_id,
        client_id=session['client_id'],
        date_col=0,
        description_col=1,
    )
    db.session.add(new_template)
    db.session.commit()
    return redirect(url_for('edit_template', template_id=new_template.id))

@app.route('/edit_template/<int:template_id>', methods=['GET', 'POST'])
def edit_template(template_id):
    template = ImportTemplate.query.get_or_404(template_id)
    account = Account.query.get_or_404(template.account_id)
    if account.client_id != session['client_id']:
        return "Unauthorized", 403
    if request.method == 'POST':
        template.date_col = col_to_index(request.form['date_col'])
        template.description_col = col_to_index(request.form['description_col'])
        template.amount_col = col_to_index(request.form.get('amount_col'))
        template.debit_col = col_to_index(request.form.get('debit_col'))
        template.credit_col = col_to_index(request.form.get('credit_col'))
        template.category_col = col_to_index(request.form.get('category_col'))
        template.notes_col = col_to_index(request.form.get('notes_col'))
        template.has_header = 'has_header' in request.form
        template.negate_amount = 'negate_amount' in request.form
        db.session.commit()
        flash('Template updated successfully.', 'success')
        return redirect(url_for('import_page'))
    else:
        template_for_view = {
            'id': template.id,
            'account_name': account.name,
            'date_col': index_to_col(template.date_col),
            'description_col': index_to_col(template.description_col),
            'amount_col': index_to_col(template.amount_col),
            'debit_col': index_to_col(template.debit_col),
            'credit_col': index_to_col(template.credit_col),
            'category_col': index_to_col(template.category_col),
            'notes_col': index_to_col(template.notes_col),
            'has_header': template.has_header,
            'negate_amount': template.negate_amount
        }
        return render_template('edit_template.html', template=template_for_view)

@app.route('/delete_template/<int:template_id>')
def delete_template(template_id):
    template = ImportTemplate.query.get_or_404(template_id)
    if template.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(template)
    db.session.commit()
    flash('Template deleted successfully.', 'success')
    return redirect(url_for('import_page'))

@app.route('/import_csv', methods=['POST'])
def import_csv():
    files = request.files.getlist('csv_files')
    account_id = request.form['account']

    template = ImportTemplate.query.filter_by(account_id=account_id).first()
    if not template:
        flash('No import template found for the selected account.', 'danger')
        return redirect(url_for('import_page'))

    all_rules = Rule.query.filter_by(client_id=session['client_id'], is_automatic=True).order_by(Rule.id).all()
    
    # Pre-filter rules that could possibly apply
    applicable_rules = []
    for rule in all_rules:
        if not rule.accounts:
            applicable_rules.append(rule)
            continue

        excluded_accounts = {link.account_id for link in rule.accounts if link.is_exclusion}
        if account_id in excluded_accounts:
            continue

        included_accounts = {link.account_id for link in rule.accounts if not link.is_exclusion}
        if included_accounts and account_id not in included_accounts:
            continue
            
        applicable_rules.append(rule)

    for file in files:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.reader(stream)

        if template.has_header:
            next(csv_reader)
        
        transactions = []
        for row in csv_reader:
            try:
                date = normalize_date(row[template.date_col])
                description = row[template.description_col]
                row[template.notes_col] if template.notes_col is not None else None
                
                if template.amount_col is not None:
                    amount = float(row[template.amount_col])
                else:
                    debit = float(row[template.debit_col]) if row[template.debit_col] else 0
                    credit = float(row[template.credit_col]) if row[template.credit_col] else 0
                    amount = credit - debit

                if template.negate_amount:
                    amount = -amount

                category = row[template.category_col] if template.category_col is not None else None

                new_transaction = Transaction(
                    date=date, description=description, amount=amount, category=category, client_id=session['client_id']
                )
                db.session.add(new_transaction)
                transactions.append(new_transaction)
            except (ValueError, IndexError) as e:
                flash(f'Error processing row: {row}. Error: {e}', 'danger')
                db.session.rollback()
                return redirect(url_for('journal'))
        run_category_rules(transactions)

    db.session.commit()
    flash(f'{len(files)} file(s) imported successfully.', 'success')
    return redirect(url_for('journal'))



def get_account_choices(client_id):
    def _get_accounts_recursive(parent_id, level):
        accounts = Account.query.filter_by(client_id=client_id, parent_id=parent_id).order_by(Account.name).all()
        choices = []
        for account in accounts:
            choices.append((account.id, account.name, int(level)))
            choices.extend(_get_accounts_recursive(account.id, level + 1))
        return choices

    return _get_accounts_recursive(None, 0)

def get_account_and_children_ids(account):
    account_ids = [account.id]
    for child in account.children:
        account_ids.extend(get_account_and_children_ids(child))
    return account_ids

@app.route('/ledger')
def ledger():
    accounts = Account.query.filter_by(client_id=session['client_id'], parent_id=None).order_by(Account.name).all()
    ledger_data = get_account_tree(accounts)
    return render_template('ledger.html', ledger_data=ledger_data)

def get_account_tree(accounts):
    account_tree = []
    for account in accounts:
        account_ids = get_account_and_children_ids(account)
        debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id.in_(account_ids)).scalar() or 0
        credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id.in_(account_ids)).scalar() or 0
        
        if account.type in ['Asset', 'Expense']:
            balance = account.opening_balance + debits - credits
        else: # Liability, Equity, Income
            balance = account.opening_balance + credits - debits

        children_tree = get_account_tree(account.children.all())
        
        account_tree.append({
            'id': account.id,
            'parent_id': account.parent_id,
            'name': account.name,
            'balance': balance,
            'children': children_tree
        })
    return account_tree

@app.route('/income_statement')
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

@app.route('/balance_sheet')
def balance_sheet():
    asset_accounts = Account.query.filter_by(client_id=session['client_id'], type='Asset', parent_id=None).all()
    liability_accounts = Account.query.filter_by(client_id=session['client_id'], type='Liability', parent_id=None).all()
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

@app.route('/statement_of_cash_flows')
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

@app.route('/budget', methods=['GET', 'POST'])
def budget():
    if request.method == 'POST':
        category = request.form['category']
        amount = abs(float(request.form['amount']))
        if Budget.query.filter_by(category=category, client_id=session['client_id']).first():
            flash(f'Budget for category "{category}" already exists.', 'danger')
            return redirect(url_for('budget'))
        new_budget = Budget(category=category, amount=amount, client_id=session['client_id'])
        db.session.add(new_budget)
        db.session.commit()
        flash(f'Budget for category "{category}" created successfully.', 'success')
        return redirect(url_for('budget'))
    else:
        budgets = Budget.query.filter_by(client_id=session['client_id']).all()
        spending = db.session.query(Budget.category, db.func.sum(JournalEntry.amount).label('spent')).join(JournalEntry, Budget.category == JournalEntry.category).filter(JournalEntry.client_id == session['client_id'], JournalEntry.transaction_type == 'expense').group_by(Budget.category).all()
        spending_dict = {s.category: s.spent for s in spending}
        return render_template('budget.html', budgets=budgets, spending=spending_dict)

@app.route('/export/ledger')
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

@app.route('/export/income_statement')
def export_income_statement():
    income = db.session.query(Account.name, db.func.sum(JournalEntry.amount).label('total')).join(JournalEntry).filter(JournalEntry.transaction_type == 'income', JournalEntry.client_id == session['client_id']).group_by(Account.name).all()
    expenses = db.session.query(Account.name, db.func.sum(JournalEntry.amount).label('total')).join(JournalEntry).filter(JournalEntry.transaction_type == 'expense', JournalEntry.client_id == session['client_id']).group_by(Account.name).all()
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

@app.route('/export/balance_sheet')
def export_balance_sheet():
    assets = db.session.query(Account.name, db.func.sum(JournalEntry.amount).label('balance')).join(JournalEntry).filter(Account.type == 'Asset', JournalEntry.client_id == session['client_id']).group_by(Account.name).all()
    liabilities = db.session.query(Account.name, db.func.sum(JournalEntry.amount).label('balance')).join(JournalEntry).filter(Account.type == 'Liability', JournalEntry.client_id == session['client_id']).group_by(Account.name).all()
    equity = db.session.query(Account.name, db.func.sum(JournalEntry.amount).label('balance')).join(JournalEntry).filter(Account.type == 'Equity', JournalEntry.client_id == session['client_id']).group_by(Account.name).all()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Category', 'Amount'])
    cw.writerow(['Assets', ''])
    for a in assets:
        cw.writerow([a.name, a.balance])
    cw.writerow(['Liabilities', ''])
    for liability in liabilities:
        cw.writerow([liability.name, liability.balance])
    cw.writerow(['Equity', ''])
    for e in equity:
        cw.writerow([e.name, e.balance])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=balance_sheet.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/rules')
def rules():
    return redirect(url_for('transaction_rules'))

@app.route('/transaction_rules', methods=['GET', 'POST'])
def transaction_rules():
    if request.method == 'POST':
        keyword = request.form['keyword']
        category = request.form['category']
        transaction_type = request.form['transaction']
        new_rule = Rule(keyword=keyword, category=category, transaction_type=transaction_type, client_id=session['client_id'])
        db.session.add(new_rule)
        db.session.commit()
        flash('Rule created successfully.', 'success')
        return redirect(url_for('transaction_rules'))
    else:
        rules = Rule.query.filter_by(client_id=session['client_id']).all()
        account_choices = get_account_choices(session['client_id'])
        return render_template('transaction_rules.html', rules=rules, accounts=account_choices)

@app.route('/category_rules', methods=['GET', 'POST'])
def category_rules():
    if request.method == 'POST':
        keyword = request.form['keyword']
        category = request.form['category']
        new_rule = CategoryRule(keyword=keyword, category=category, client_id=session['client_id'])
        db.session.add(new_rule)
        db.session.commit()
        flash('Category rule created successfully.', 'success')
        return redirect(url_for('category_rules'))
    else:
        rules = CategoryRule.query.filter_by(client_id=session['client_id']).all()
        account_choices = get_account_choices(session['client_id'])
        return render_template('category_rules.html', rules=rules, accounts=account_choices)

@app.route('/add_transaction_rule', methods=['POST'])
def add_transaction_rule():
    name = request.form['name']
    keyword = request.form.get('keyword')
    condition = request.form.get('condition')
    value_str = request.form.get('value')
    category = request.form.get('category')
    transaction_type = request.form.get('transaction_type')
    debit_account_id = request.form.get('debit_account_id')
    credit_account_id = request.form.get('credit_account_id')
    is_automatic = request.form.get('is_automatic') == 'true'
    include_accounts = request.form.getlist('include_accounts')
    exclude_accounts = request.form.getlist('exclude_accounts')

    # Basic validation
    if not keyword and not (condition and value_str):
        flash('A rule must have at least a keyword or a value condition.', 'danger')
        return redirect(url_for('transaction_rules'))
    
    if not category and not transaction_type and not debit_account_id and not credit_account_id:
        flash('A rule must specify at least a category, a transaction type, or debit/credit accounts to set.', 'danger')
        return redirect(url_for('transaction_rules'))

    value = float(value_str) if value_str else None

    # Use sets for efficient handling of overlaps
    include_set = set(include_accounts)
    exclude_set = set(exclude_accounts)

    # Excluded accounts take precedence. An account cannot be in both.
    conflicting_accounts = include_set.intersection(exclude_set)
    if conflicting_accounts:
        conflicting_names = [acc.name for acc in Account.query.filter(Account.id.in_(conflicting_accounts)).all()]
        flash(f"Accounts cannot be in both include and exclude lists: {', '.join(conflicting_names)}. They have been excluded by default.", 'warning')
        include_set -= exclude_set

    new_rule = Rule(
        name=name,
        keyword=keyword,
        condition=condition,
        value=value,
        category=category, 
        transaction_type=transaction_type,
        debit_account_id=debit_account_id,
        credit_account_id=credit_account_id,
        is_automatic=is_automatic,
        client_id=session['client_id']
    )

    for account_id in include_set:
        link = RuleAccountLink(account_id=account_id, is_exclusion=False)
        new_rule.accounts.append(link)

    for account_id in exclude_set:
        link = RuleAccountLink(account_id=account_id, is_exclusion=True)
        new_rule.accounts.append(link)

    db.session.add(new_rule)
    db.session.commit()
    flash('Transaction rule created successfully.', 'success')
    return redirect(url_for('transaction_rules'))

@app.route('/add_category_rule', methods=['POST'])
def add_category_rule():
    name = request.form['name']
    keyword = request.form.get('keyword')
    condition = request.form.get('condition')
    value_str = request.form.get('value')
    category = request.form.get('category')
    debit_account_id = request.form.get('debit_account_id')
    credit_account_id = request.form.get('credit_account_id')

    # Basic validation
    if not keyword and not (condition and value_str):
        flash('A rule must have at least a keyword or a value condition.', 'danger')
        return redirect(url_for('category_rules'))
    
    if not category:
        flash('A category rule must specify a category to set.', 'danger')
        return redirect(url_for('category_rules'))

    value = float(value_str) if value_str else None

    new_rule = CategoryRule(
        name=name,
        keyword=keyword,
        condition=condition,
        value=value,
        category=category,
        debit_account_id=debit_account_id if debit_account_id else None,
        credit_account_id=credit_account_id if credit_account_id else None,
        client_id=session['client_id']
    )
    db.session.add(new_rule)
    db.session.commit()
    flash('Category rule created successfully.', 'success')
    return redirect(url_for('category_rules'))

@app.route('/delete_transaction_rule/<int:rule_id>')
def delete_transaction_rule(rule_id):
    rule = Rule.query.get_or_404(rule_id)
    if rule.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(rule)
    db.session.commit()
    flash('Transaction rule deleted successfully.', 'success')
    return redirect(url_for('transaction_rules'))

@app.route('/delete_category_rule/<int:rule_id>')
def delete_category_rule(rule_id):
    rule = CategoryRule.query.get_or_404(rule_id)
    if rule.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(rule)
    db.session.commit()
    flash('Category rule deleted successfully.', 'success')
    return redirect(url_for('category_rules'))

@app.route('/edit_transaction_rule/<int:rule_id>', methods=['GET', 'POST'])
def edit_transaction_rule(rule_id):
    rule = Rule.query.get_or_404(rule_id)
    if rule.client_id != session['client_id']:
        return "Unauthorized", 403
    if request.method == 'POST':
        rule.name = request.form['name']
        rule.keyword = request.form.get('keyword')
        rule.condition = request.form.get('condition')
        value_str = request.form.get('value')
        rule.category = request.form.get('category')
        rule.transaction_type = request.form.get('transaction_type')
        rule.debit_account_id = request.form.get('debit_account_id')
        rule.credit_account_id = request.form.get('credit_account_id')
        rule.is_automatic = request.form.get('is_automatic') == 'true'
        include_accounts = request.form.getlist('include_accounts')
        exclude_accounts = request.form.getlist('exclude_accounts')

        # Basic validation
        if not rule.keyword and not (rule.condition and value_str):
            flash('A rule must have at least a keyword or a value condition.', 'danger')
            return redirect(url_for('edit_transaction_rule', rule_id=rule_id))
        
        if not rule.category and not rule.transaction_type and not rule.debit_account_id and not rule.credit_account_id:
            flash('A rule must specify at least a category, a transaction type, or debit/credit accounts to set.', 'danger')
            return redirect(url_for('edit_transaction_rule', rule_id=rule_id))

        rule.value = float(value_str) if value_str else None

        # Use sets for efficient handling of overlaps
        include_set = set(include_accounts)
        exclude_set = set(exclude_accounts)

        # Excluded accounts take precedence. An account cannot be in both.
        conflicting_accounts = include_set.intersection(exclude_set)
        if conflicting_accounts:
            conflicting_names = [acc.name for acc in Account.query.filter(Account.id.in_(conflicting_accounts)).all()]
            flash(f"Accounts cannot be in both include and exclude lists: {', '.join(conflicting_names)}. They have been excluded by default.", 'warning')
            include_set -= exclude_set

        # Clear existing account links
        RuleAccountLink.query.filter_by(rule_id=rule_id).delete()

        for account_id in include_set:
            link = RuleAccountLink(rule_id=rule.id, account_id=account_id, is_exclusion=False)
            db.session.add(link)

        for account_id in exclude_set:
            link = RuleAccountLink(rule_id=rule.id, account_id=account_id, is_exclusion=True)
            db.session.add(link)

        db.session.commit()
        flash('Transaction rule updated successfully.', 'success')
        return redirect(url_for('transaction_rules'))
    else:
        account_choices = get_account_choices(session['client_id'])
        return render_template('edit_rule.html', rule=rule, accounts=account_choices)

@app.route('/edit_category_rule/<int:rule_id>', methods=['GET', 'POST'])
def edit_category_rule(rule_id):
    rule = CategoryRule.query.get_or_404(rule_id)
    if rule.client_id != session['client_id']:
        return "Unauthorized", 403
    if request.method == 'POST':
        rule.name = request.form['name']
        rule.keyword = request.form.get('keyword')
        rule.condition = request.form.get('condition')
        value_str = request.form.get('value')
        rule.category = request.form.get('category')
        rule.debit_account_id = request.form.get('debit_account_id')
        rule.credit_account_id = request.form.get('credit_account_id')

        # Basic validation
        if not rule.keyword and not (rule.condition and value_str):
            flash('A category rule must have at least a keyword or a value condition.', 'danger')
            return redirect(url_for('edit_category_rule', rule_id=rule_id))
        
        if not rule.category:
            flash('A category rule must specify a category to set.', 'danger')
            return redirect(url_for('edit_category_rule', rule_id=rule_id))

        rule.value = float(value_str) if value_str else None

        db.session.commit()
        flash('Category rule updated successfully.', 'success')
        return redirect(url_for('category_rules'))
    else:
        account_choices = get_account_choices(session['client_id'])
        return render_template('edit_category_rule.html', rule=rule, accounts=account_choices)


@app.route('/products')
def products():
    products = Product.query.filter_by(client_id=session['client_id']).order_by(Product.name).all()
    return render_template('products.html', products=products)

@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        cost = abs(float(request.form['cost']))

        new_product = Product(
            name=name, 
            description=description, 
            cost=cost, 
            client_id=session['client_id']
        )
        db.session.add(new_product)
        db.session.commit()

        # Add product to inventory with initial quantity of 0
        new_inventory_item = Inventory(
            quantity=0,
            product_id=new_product.id,
            client_id=session['client_id']
        )
        db.session.add(new_inventory_item)
        db.session.commit()

        flash('Product added successfully.', 'success')
        return redirect(url_for('products'))
    return render_template('add_product.html')

@app.route('/inventory')
def inventory():
    inventory = Inventory.query.filter_by(client_id=session['client_id']).all()
    return render_template('inventory.html', inventory=inventory)

@app.route('/sales')
def sales():
    sales = Sale.query.filter_by(client_id=session['client_id']).order_by(Sale.date.desc()).all()
    return render_template('sales.html', sales=sales)

@app.route('/add_sale', methods=['GET', 'POST'])
def add_sale():
    products = Product.query.filter_by(client_id=session['client_id']).order_by(Product.name).all()
    if request.method == 'POST':
        date = request.form['date']
        product_id = request.form['product_id']
        quantity = int(request.form['quantity'])
        price = float(request.form['price'])

        # Check if there is enough inventory
        inventory_item = Inventory.query.filter_by(product_id=product_id, client_id=session['client_id']).first()
        if not inventory_item or inventory_item.quantity < quantity:
            flash('Not enough inventory for this sale.', 'danger')
            return render_template('add_sale.html', products=products)

        # Create the sale
        new_sale = Sale(
            date=date,
            product_id=product_id,
            quantity=quantity,
            price=price,
            client_id=session['client_id']
        )
        db.session.add(new_sale)

        # Update inventory
        inventory_item.quantity -= quantity

        # Create journal entries for the sale
        cogs_account = Account.query.filter_by(category='COGS', client_id=session['client_id']).first()
        sales_revenue_account = Account.query.filter_by(type='Revenue', client_id=session['client_id']).first()
        inventory_account = Account.query.filter_by(type='Inventory', client_id=session['client_id']).first()
        cash_account = Account.query.filter_by(type='Asset', name='Cash', client_id=session['client_id']).first()

        if cogs_account and sales_revenue_account and inventory_account and cash_account:
            # 1. Record the sale
            db.session.add(JournalEntry(
                date=date,
                description=f"Sale of {quantity} {new_sale.product.name}",
                debit_account_id=cash_account.id,
                credit_account_id=sales_revenue_account.id,
                amount=abs(price * quantity),
                client_id=session['client_id']
            ))

            # 2. Record the cost of goods sold
            db.session.add(JournalEntry(
                date=date,
                description=f"COGS for sale of {quantity} {new_sale.product.name}",
                debit_account_id=cogs_account.id,
                credit_account_id=inventory_account.id,
                amount=abs(new_sale.product.cost * quantity),
                client_id=session['client_id']
            ))

        db.session.commit()
        flash('Sale recorded successfully.', 'success')
        return redirect(url_for('sales'))

    return render_template('add_sale.html', products=products)

@app.route('/accruals')
def accruals():
    accruals = JournalEntry.query.filter_by(client_id=session['client_id'], is_accrual=True).order_by(JournalEntry.date.desc()).all()
    return render_template('accruals.html', accruals=accruals)

@app.route('/add_accrual', methods=['GET', 'POST'])
def add_accrual():
    account_choices = get_account_choices(session['client_id'])
    if request.method == 'POST':
        date = request.form['date']
        description = request.form['description']
        amount = abs(float(request.form['amount']))
        debit_account_id = request.form['debit_account_id']
        credit_account_id = request.form['credit_account_id']

        new_entry = JournalEntry(
            date=date,
            description=description,
            debit_account_id=debit_account_id,
            credit_account_id=credit_account_id,
            amount=amount,
            is_accrual=True,
            client_id=session['client_id']
        )
        db.session.add(new_entry)
        db.session.commit()

        flash('Accrual added successfully.', 'success')
        return redirect(url_for('accruals'))
    return render_template('add_accrual.html', accounts=account_choices)

@app.route('/recurring_transactions')
def recurring_transactions():
    recurring_transactions = detect_recurring_transactions()
    account_choices = get_account_choices(session['client_id'])
    return render_template('recurring_transactions.html', recurring_transactions=recurring_transactions, accounts=account_choices)

@app.route('/approve_recurring_transaction', methods=['POST'])
def approve_recurring_transaction():
    name = request.form['name']
    description = request.form['description']
    amount = abs(float(request.form['amount']))
    frequency = request.form['frequency']
    start_date = request.form['start_date']
    end_date = request.form['end_date']
    debit_account_id = request.form['debit_account_id']
    credit_account_id = request.form['credit_account_id']

    new_recurring_transaction = RecurringTransaction(
        name=name,
        description=description,
        amount=amount,
        frequency=frequency,
        start_date=start_date,
        end_date=end_date,
        debit_account_id=debit_account_id,
        credit_account_id=credit_account_id,
        client_id=session['client_id']
    )
    db.session.add(new_recurring_transaction)
    db.session.commit()

    flash('Recurring transaction approved successfully.', 'success')
    return redirect(url_for('recurring_transactions'))

def reverse_accruals():
    with app.app_context():
        today = datetime.now()
        if today.day == 1:
            accruals_to_reverse = JournalEntry.query.filter_by(client_id=session['client_id'], is_accrual=True).all()
            for accrual in accruals_to_reverse:
                # Create a reversing entry
                new_entry = JournalEntry(
                    date=today.strftime('%Y-%m-%d'),
                    description=f"Reversal of: {accrual.description}",
                    debit_account_id=accrual.credit_account_id,
                    credit_account_id=accrual.debit_account_id,
                    amount=abs(accrual.amount),
                    is_accrual=False,
                    client_id=session['client_id']
                )
                db.session.add(new_entry)
                accrual.is_accrual = False
            db.session.commit()

def detect_recurring_transactions():
    with app.app_context():
        # Get all transactions for the current client
        transactions = Transaction.query.filter_by(client_id=session['client_id']).order_by(Transaction.date.desc()).all()

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
                    date1 = datetime.strptime(transaction_group[i].date, '%Y-%m-%d')
                    date2 = datetime.strptime(transaction_group[i+1].date, '%Y-%m-%d')
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

@app.route('/fixed_assets')
def fixed_assets():
    assets = FixedAsset.query.filter_by(client_id=session['client_id']).order_by(FixedAsset.purchase_date.desc()).all()
    return render_template('fixed_assets.html', assets=assets)

@app.route('/add_fixed_asset', methods=['GET', 'POST'])
def add_fixed_asset():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        purchase_date = request.form['purchase_date']
        cost = abs(float(request.form['cost']))
        useful_life = int(request.form['useful_life'])
        salvage_value = float(request.form['salvage_value'])

        new_asset = FixedAsset(
            name=name, 
            description=description, 
            purchase_date=purchase_date, 
            cost=cost, 
            useful_life=useful_life, 
            salvage_value=salvage_value, 
            client_id=session['client_id']
        )
        db.session.add(new_asset)
        db.session.commit()

        # Create a journal entry for the purchase of the fixed asset
        fixed_asset_account = Account.query.filter_by(type='Fixed Asset', client_id=session['client_id']).first()
        cash_account = Account.query.filter_by(type='Asset', name='Cash', client_id=session['client_id']).first()
        if fixed_asset_account and cash_account:
            new_entry = JournalEntry(
                date=purchase_date,
                description=f"Purchase of {name}",
                debit_account_id=fixed_asset_account.id,
                credit_account_id=cash_account.id,
                amount=cost,
                client_id=session['client_id']
            )
            db.session.add(new_entry)
            db.session.commit()

        flash('Fixed asset added successfully.', 'success')
        return redirect(url_for('fixed_assets'))
    return render_template('add_fixed_asset.html')

@app.route('/depreciation_schedule/<int:asset_id>')
def depreciation_schedule(asset_id):
    asset = FixedAsset.query.get_or_404(asset_id)
    if asset.client_id != session['client_id']:
        return "Unauthorized", 403

    depreciation_entries = Depreciation.query.filter_by(fixed_asset_id=asset.id).order_by(Depreciation.date).all()
    schedule = []
    accumulated_depreciation = 0
    book_value = asset.cost

    for entry in depreciation_entries:
        accumulated_depreciation += entry.amount
        book_value -= entry.amount
        schedule.append({
            'date': entry.date,
            'amount': entry.amount,
            'accumulated_depreciation': accumulated_depreciation,
            'book_value': book_value
        })

    return render_template('depreciation_schedule.html', asset=asset, schedule=schedule)

def calculate_and_record_depreciation():
    with app.app_context():
        today = datetime.now()
        assets = FixedAsset.query.filter_by(client_id=session['client_id']).all()
        for asset in assets:
            # Calculate monthly depreciation
            monthly_depreciation = abs((asset.cost - asset.salvage_value) / (asset.useful_life * 12))
            
            # Check if depreciation has already been recorded for the current month
            last_depreciation = Depreciation.query.filter_by(fixed_asset_id=asset.id).order_by(Depreciation.date.desc()).first()
            if last_depreciation:
                last_depreciation_date = datetime.strptime(last_depreciation.date, '%Y-%m-%d')
                if last_depreciation_date.year == today.year and last_depreciation_date.month == today.month:
                    continue

            # Record depreciation for the current month
            new_depreciation = Depreciation(
                date=today.strftime('%Y-%m-%d'),
                amount=abs(monthly_depreciation),
                fixed_asset_id=asset.id,
                client_id=session['client_id']
            )
            db.session.add(new_depreciation)

            # Create journal entry for depreciation
            depreciation_expense_account = Account.query.filter_by(type='Expense', category='Depreciation', client_id=session['client_id']).first()
            accumulated_depreciation_account = Account.query.filter_by(type='Accumulated Depreciation', client_id=session['client_id']).first()

            if depreciation_expense_account and accumulated_depreciation_account:
                new_entry = JournalEntry(
                    date=today.strftime('%Y-%m-%d'),
                    description=f"Depreciation for {asset.name}",
                    debit_account_id=depreciation_expense_account.id,
                    credit_account_id=accumulated_depreciation_account.id,
                    amount=abs(monthly_depreciation),
                    client_id=session['client_id']
                )
                db.session.add(new_entry)

        db.session.commit()