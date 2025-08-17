from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import csv
import io
from datetime import datetime, timedelta
from collections import defaultdict
import json

import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Change this in a real application
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'bookkeeping.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    opening_balance = db.Column(db.Float, nullable=True, default=0.0)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

class JournalEntry(db.Model):
    __tablename__ = 'journal_entries'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    description = db.Column(db.String(200))
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100))
    transaction_type = db.Column(db.String(20), nullable=False, default='uncategorized') # uncategorized, income, expense, transfer
    notes = db.Column(db.String(500), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    account = db.relationship('Account', backref=db.backref('journal_entries', lazy=True))

class ImportTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False, unique=True)
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
    is_automatic = db.Column(db.Boolean, nullable=False, default=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    accounts = db.relationship('RuleAccountLink', backref='rule', cascade="all, delete-orphan")


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

@app.route('/clients', methods=['GET', 'POST'])
def clients():
    if request.method == 'POST':
        name = request.form['name']
        if Client.query.filter_by(name=name).first():
            flash(f'Client "{name}" already exists.', 'danger')
            return redirect(url_for('clients'))
        new_client = Client(name=name)
        db.session.add(new_client)
        db.session.commit()
        flash(f'Client "{name}" created successfully.', 'success')
        return redirect(url_for('clients'))
    else:
        clients = Client.query.all()
        return render_template('clients.html', clients=clients)

@app.route('/select_client/<int:client_id>')
def select_client(client_id):
    session['client_id'] = client_id
    return redirect(url_for('index'))

@app.route('/edit_client/<int:client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)
    if request.method == 'POST':
        name = request.form['name']
        if Client.query.filter(Client.name == name, Client.id != client_id).first():
            flash(f'Client "{name}" already exists.', 'danger')
            return redirect(url_for('edit_client', client_id=client_id))
        client.name = name
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
        JournalEntry.transaction_type,
        db.func.sum(JournalEntry.amount).label('total')
    ).filter(
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date_str,
        JournalEntry.date <= end_date_str
    ).group_by('month', JournalEntry.transaction_type)

    monthly_data = monthly_data_query.all()

    bar_chart_data = defaultdict(lambda: {'income': 0, 'expense': 0})
    for month, trans_type, total in monthly_data:
        if trans_type in ['income', 'expense']:
            bar_chart_data[month][trans_type] = total
    
    sorted_months = sorted(bar_chart_data.keys())
    bar_chart_labels = json.dumps(sorted_months)
    bar_chart_income = json.dumps([bar_chart_data[m]['income'] for m in sorted_months])
    bar_chart_expense = json.dumps([bar_chart_data[m]['expense'] for m in sorted_months])

    # Expense breakdown for the selected period for the pie chart
    expense_breakdown_query = db.session.query(
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).filter(
        JournalEntry.transaction_type == 'expense',
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date_str,
        JournalEntry.date <= end_date_str
    ).group_by(JournalEntry.category)

    expense_breakdown = expense_breakdown_query.all()

    pie_chart_labels = json.dumps([item.category for item in expense_breakdown])
    pie_chart_data = json.dumps([item.total for item in expense_breakdown])

    # Income breakdown for the selected period for the pie chart
    income_breakdown_query = db.session.query(
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).filter(
        JournalEntry.transaction_type == 'income',
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date_str,
        JournalEntry.date <= end_date_str
    ).group_by(JournalEntry.category)

    income_breakdown = income_breakdown_query.all()

    income_pie_chart_labels = json.dumps([item.category for item in income_breakdown])
    income_pie_chart_data = json.dumps([item.total for item in income_breakdown])

    # KPIs for the selected period
    income_this_period = db.session.query(db.func.sum(JournalEntry.amount)).filter(
        JournalEntry.client_id == session['client_id'],
        JournalEntry.transaction_type == 'income',
        JournalEntry.date >= start_date_str,
        JournalEntry.date <= end_date_str
    ).scalar() or 0
    
    expenses_this_period = db.session.query(db.func.sum(JournalEntry.amount)).filter(
        JournalEntry.client_id == session['client_id'],
        JournalEntry.transaction_type == 'expense',
        JournalEntry.date >= start_date_str,
        JournalEntry.date <= end_date_str
    ).scalar() or 0

    m_income = income_this_period
    m_expenses = expenses_this_period
    net_profit = m_income + m_expenses

    # Account summaries (these are not date-filtered in the original, so keep as is)
    asset_accounts = Account.query.filter_by(type='Asset', client_id=session['client_id']).all()
    liability_accounts = Account.query.filter_by(type='Liability', client_id=session['client_id']).all()

    asset_balances = {account.name: sum(entry.amount for entry in account.journal_entries) for account in asset_accounts}
    liability_balances = {account.name: sum(entry.amount for entry in account.journal_entries) for account in liability_accounts}

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

@app.route('/category_transactions/<category_name>')
def category_transactions(category_name):
    entries = JournalEntry.query.filter_by(category=category_name, client_id=session['client_id']).order_by(JournalEntry.date.desc()).all()
    return render_template('category_transactions.html', entries=entries, category_name=category_name)

@app.route('/accounts')
def accounts():
    accounts = Account.query.filter_by(client_id=session['client_id']).order_by(Account.name).all()
    return render_template('accounts.html', accounts=accounts)

@app.route('/add_account', methods=['POST'])
def add_account():
    name = request.form['name']
    account_type = request.form['type']
    opening_balance = float(request.form['opening_balance'])
    if Account.query.filter_by(name=name, client_id=session['client_id']).first():
        flash(f'Account "{name}" already exists.', 'danger')
        return redirect(url_for('accounts'))
    new_account = Account(name=name, type=account_type, opening_balance=opening_balance, client_id=session['client_id'])
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
        if Account.query.filter(Account.name == name, Account.id != account_id, Account.client_id == session['client_id']).first():
            flash(f'Account "{name}" already exists.', 'danger')
            return redirect(url_for('edit_account', account_id=account_id))
        account.name = name
        account.type = request.form['type']
        account.opening_balance = float(request.form['opening_balance'])
        db.session.commit()
        flash('Account updated successfully.', 'success')
        return redirect(url_for('accounts'))
    else:
        return render_template('edit_account.html', account=account)

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
    query = JournalEntry.query.join(Account).filter(JournalEntry.client_id == session['client_id'])

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
    if sort_by == 'account':
        sort_column = Account.name

    if direction == 'asc':
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    entries = query.all()
    accounts = Account.query.filter_by(client_id=session['client_id']).order_by(Account.name).all()
    
    return render_template('journal.html', entries=entries, accounts=accounts, filters=filters)

@app.route('/add_entry', methods=['POST'])
def add_entry():
    date = request.form['date']
    description = request.form['description']
    account_id = request.form['account']
    amount = request.form['amount']
    category = request.form['category']
    transaction_type = request.form['transaction_type']
    notes = request.form.get('notes')
    new_entry = JournalEntry(date=date, description=description, account_id=account_id, amount=amount, category=category, transaction_type=transaction_type, notes=notes, client_id=session['client_id'])
    db.session.add(new_entry)
    db.session.commit()
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
        entry.account_id = request.form['account']
        entry.amount = request.form['amount']
        entry.category = request.form['category']
        entry.transaction_type = request.form['transaction_type']
        entry.notes = request.form.get('notes')
        db.session.commit()
        flash('Journal entry updated successfully.', 'success')
        return redirect(url_for('journal'))
    else:
        accounts = Account.query.filter_by(client_id=session['client_id']).order_by(Account.name).all()
        return render_template('edit_entry.html', entry=entry, accounts=accounts)

@app.route('/delete_entry/<int:entry_id>')
def delete_entry(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(entry)
    db.session.commit()
    flash('Journal entry deleted successfully.', 'success')
    return redirect(url_for('journal'))

@app.route('/bulk_actions', methods=['POST'])
def bulk_actions():
    print("--- BULK ACTIONS ROUTE REACHED ---")
    entry_ids = request.form.getlist('entry_ids')
    action = request.form['action']

    if not entry_ids:
        flash('No entries selected.', 'warning')
        return redirect(url_for('journal'))

    if action == 'delete':
        JournalEntry.query.filter(JournalEntry.id.in_(entry_ids), JournalEntry.client_id == session['client_id']).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{len(entry_ids)} journal entries deleted successfully.', 'success')
    elif action == 'update_type':
        transaction_type = request.form['transaction_type']
        if transaction_type:
            entry_ids_int = [int(id) for id in entry_ids]
            try:
                JournalEntry.query.filter(JournalEntry.id.in_(entry_ids_int), JournalEntry.client_id == session['client_id']).update({'transaction_type': transaction_type}, synchronize_session=False)
                db.session.commit()
                flash(f'{len(entry_ids)} journal entries updated to type "{transaction_type}" successfully.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating entries: {e}', 'danger')
        else:
            flash('Transaction type not provided.', 'warning')
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

                excluded_accounts = {link.account_id for link in rule.accounts if link.is_exclusion}
                if entry.account_id in excluded_accounts:
                    continue

                included_accounts = {link.account_id for link in rule.accounts if not link.is_exclusion}
                if included_accounts and entry.account_id not in included_accounts:
                    continue
                
                applicable_rules.append(rule)

            print(f"DEBUG: Rules loaded for manual application: {[(r.name, r.keyword, r.condition, r.value, r.is_automatic) for r in applicable_rules]}")
            print(f"DEBUG: Processing Entry ID: {entry.id}, Description: '{entry.description}', Amount: {entry.amount}")
            
            # Initialize category and transaction_type for this entry
            current_category = entry.category
            current_transaction_type = entry.transaction_type

            # Apply all matching rules
            for rule in applicable_rules:
                # Normalize description and keyword for robust matching
                normalized_description = ' '.join(entry.description.lower().split())
                normalized_keyword = ' '.join(rule.keyword.lower().split()) if rule.keyword else None

                print(f"DEBUG: Checking rule: {rule.name} | {rule.keyword} | {rule.condition} {rule.value} (Automatic: {rule.is_automatic})")
                print(f"DEBUG: Normalized Description: '{normalized_description}'")
                print(f"DEBUG: Normalized Keyword: '{normalized_keyword}'")

                keyword_match = False
                if normalized_keyword:
                    keyword_match = normalized_keyword in normalized_description
                print(f"DEBUG: Keyword Match: {keyword_match}")
                
                condition_match = False
                if rule.condition and rule.value is not None:
                    if rule.condition == 'less_than' and entry.amount < rule.value:
                        condition_match = True
                    elif rule.condition == 'greater_than' and entry.amount > rule.value:
                        condition_match = True
                    elif rule.condition == 'equals' and entry.amount == rule.value:
                        condition_match = True
                print(f"DEBUG: Condition Match: {condition_match}")

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
                print(f"DEBUG: Apply Rule: {apply_rule}")

                if apply_rule:
                    if rule.category:
                        current_category = rule.category
                    if rule.transaction_type:
                        current_transaction_type = rule.transaction_type
                    print(f"DEBUG: Rule Matched. Current Category: {current_category}, Current Type: {current_transaction_type}")
            
            # Update entry only if changes were made
            if entry.category != current_category or entry.transaction_type != current_transaction_type:
                entry.category = current_category
                entry.transaction_type = current_transaction_type
                updated_count += 1
                print(f"DEBUG: Entry Updated! Final Category: {entry.category}, Final Type: {entry.transaction_type}")

        db.session.commit()
        flash(f'{updated_count} journal entries updated successfully based on rules.', 'success')
    
    return redirect(url_for('journal'))

@app.route('/import', methods=['GET'])
def import_page():
    accounts = Account.query.filter_by(client_id=session['client_id']).order_by(Account.name).all()
    return render_template('import.html', accounts=accounts)

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

        for row in csv_reader:
            try:
                date = normalize_date(row[template.date_col])
                description = row[template.description_col]
                notes = row[template.notes_col] if template.notes_col is not None else None
                
                if template.amount_col is not None:
                    amount = float(row[template.amount_col])
                else:
                    debit = float(row[template.debit_col]) if row[template.debit_col] else 0
                    credit = float(row[template.credit_col]) if row[template.credit_col] else 0
                    amount = credit - debit

                if template.negate_amount:
                    amount = -amount

                # Set defaults
                category = row[template.category_col] if template.category_col is not None and row[template.category_col] else None
                transaction_type = 'uncategorized'

                # Apply rules
                for rule in applicable_rules:
                    print(f"DEBUG: Checking rule: {{rule.keyword}} | {{rule.condition}} {{rule.value}}")
                    print(f"DEBUG: Transaction Description: {{description}}")
                    print(f"DEBUG: Transaction Amount: {{amount}}")

                    keyword_match = False
                    if rule.keyword:
                        keyword_match = rule.keyword.lower() in description.lower()
                    print(f"DEBUG: Keyword Match: {{keyword_match}}")
                    
                    condition_match = False
                    if rule.condition and rule.value is not None:
                        if rule.condition == 'less_than' and amount < rule.value:
                            condition_match = True
                        elif rule.condition == 'greater_than' and amount > rule.value:
                            condition_match = True
                        elif rule.condition == 'equals' and amount == rule.value:
                            condition_match = True
                    print(f"DEBUG: Condition Match: {{condition_match}}")

                    # A rule can have a keyword, a condition, or both. 
                    # If both are present, both must be true.
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
                    print(f"DEBUG: Apply Rule: {apply_rule}")

                    if apply_rule:
                        if rule.category:
                            category = rule.category
                        if rule.transaction_type:
                            transaction_type = rule.transaction_type
                        print(f"DEBUG: Rule Applied! Category: {{category}}, Type: {{transaction_type}}")
                        break # Stop after first matching rule

                new_entry = JournalEntry(
                    date=date, description=description, account_id=account_id, 
                    amount=amount, category=category, transaction_type=transaction_type, notes=notes, client_id=session['client_id']
                )
                db.session.add(new_entry)
            except (ValueError, IndexError) as e:
                flash(f'Error processing row: {row}. Error: {e}', 'danger')
                db.session.rollback()
                return redirect(url_for('journal'))

    db.session.commit()
    flash(f'{len(files)} file(s) imported successfully.', 'success')
    return redirect(url_for('journal'))

@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    if request.method == 'POST':
        date = normalize_date(request.form['date'])
        description = request.form['description']
        from_account_id = request.form['from_account']
        to_account_id = request.form['to_account']
        amount = float(request.form['amount'])

        if from_account_id == to_account_id:
            flash('From and To accounts cannot be the same.', 'danger')
            return redirect(url_for('transfer'))

        # Create two journal entries for the transfer
        from_entry = JournalEntry(
            date=date, description=description, account_id=from_account_id, 
            amount=-amount, transaction_type='transfer', client_id=session['client_id']
        )
        to_entry = JournalEntry(
            date=date, description=description, account_id=to_account_id, 
            amount=amount, transaction_type='transfer', client_id=session['client_id']
        )
        db.session.add(from_entry)
        db.session.add(to_entry)
        db.session.commit()
        flash('Transfer recorded successfully.', 'success')
        return redirect(url_for('journal'))
    else:
        accounts = Account.query.filter_by(client_id=session['client_id']).order_by(Account.name).all()
        return render_template('transfer.html', accounts=accounts)

@app.route('/ledger')
def ledger():
    accounts = Account.query.filter_by(client_id=session['client_id']).order_by(Account.name).all()
    ledger_data = []
    total_ytd_net_change = 0

    for account in accounts:
        entries = JournalEntry.query.filter_by(account_id=account.id, client_id=session['client_id']).all()
        
        opening_balance = account.opening_balance
        debits = sum(entry.amount for entry in entries if entry.amount < 0)
        credits = sum(entry.amount for entry in entries if entry.amount > 0)
        net_change = debits + credits
        closing_balance = opening_balance + net_change

        if account.type in ['Asset', 'Expense']:
            total_ytd_net_change += net_change
        else: # Liability, Equity, Income
            total_ytd_net_change -= net_change

        ledger_data.append({
            'name': account.name,
            'type': account.type,
            'opening_balance': opening_balance,
            'debits': abs(debits),
            'credits': credits,
            'net_change': net_change,
            'closing_balance': closing_balance
        })

    return render_template('ledger.html', ledger_data=ledger_data, total_ytd_net_change=total_ytd_net_change)

@app.route('/income_statement')
def income_statement():
    income = db.session.query(Account.name, db.func.sum(JournalEntry.amount).label('total')).join(JournalEntry).filter(JournalEntry.transaction_type == 'income', JournalEntry.client_id == session['client_id']).group_by(Account.name).all()
    expenses = db.session.query(Account.name, db.func.sum(JournalEntry.amount).label('total')).join(JournalEntry).filter(JournalEntry.transaction_type == 'expense', JournalEntry.client_id == session['client_id']).group_by(Account.name).all()

    total_income = sum(i.total for i in income)
    total_expenses = sum(e.total for e in expenses)
    net_income = total_income + total_expenses

    return render_template('income_statement.html', income=income, expenses=expenses, total_income=total_income, total_expenses=total_expenses, net_income=net_income)

@app.route('/balance_sheet')
def balance_sheet():
    assets = db.session.query(Account.name, db.func.sum(JournalEntry.amount).label('balance')).join(JournalEntry).filter(Account.type == 'Asset', JournalEntry.client_id == session['client_id']).group_by(Account.name).all()
    liabilities = db.session.query(Account.name, db.func.sum(JournalEntry.amount).label('balance')).join(JournalEntry).filter(Account.type == 'Liability', JournalEntry.client_id == session['client_id']).group_by(Account.name).all()
    equity = db.session.query(Account.name, db.func.sum(JournalEntry.amount).label('balance')).join(JournalEntry).filter(Account.type == 'Equity', JournalEntry.client_id == session['client_id']).group_by(Account.name).all()

    total_assets = sum(a.balance for a in assets)
    total_liabilities = sum(l.balance for l in liabilities)
    total_equity = sum(e.balance for e in equity)

    return render_template('balance_sheet.html', assets=assets, liabilities=liabilities, equity=equity, total_assets=total_assets, total_liabilities=total_liabilities, total_equity=total_equity)

@app.route('/budget', methods=['GET', 'POST'])
def budget():
    if request.method == 'POST':
        category = request.form['category']
        amount = float(request.form['amount'])
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
        entries = JournalEntry.query.filter_by(account_id=account.id, client_id=session['client_id']).all()
        opening_balance = 0
        debits = sum(entry.amount for entry in entries if entry.amount < 0)
        credits = sum(entry.amount for entry in entries if entry.amount > 0)
        net_change = debits + credits
        closing_balance = opening_balance + net_change
        cw.writerow([account.name, account.type, opening_balance, abs(debits), credits, net_change, closing_balance])
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
    for l in liabilities:
        cw.writerow([l.name, l.balance])
    cw.writerow(['Equity', ''])
    for e in equity:
        cw.writerow([e.name, e.balance])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=balance_sheet.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/rules', methods=['GET', 'POST'])
def rules():
    if request.method == 'POST':
        keyword = request.form['keyword']
        category = request.form['category']
        transaction_type = request.form['transaction']
        new_rule = Rule(keyword=keyword, category=category, transaction_type=transaction_type, client_id=session['client_id'])
        db.session.add(new_rule)
        db.session.commit()
        flash('Rule created successfully.', 'success')
        return redirect(url_for('rules'))
    else:
        rules = Rule.query.filter_by(client_id=session['client_id']).all()
        accounts = Account.query.filter_by(client_id=session['client_id']).order_by(Account.name).all()
        return render_template('rules.html', rules=rules, accounts=accounts)

@app.route('/add_rule', methods=['POST'])
def add_rule():
    name = request.form['name']
    keyword = request.form.get('keyword')
    condition = request.form.get('condition')
    value_str = request.form.get('value')
    category = request.form.get('category')
    transaction_type = request.form.get('transaction_type')
    is_automatic = request.form.get('is_automatic') == 'true'
    include_accounts = request.form.getlist('include_accounts')
    exclude_accounts = request.form.getlist('exclude_accounts')

    # Basic validation
    if not keyword and not (condition and value_str):
        flash('A rule must have at least a keyword or a value condition.', 'danger')
        return redirect(url_for('rules'))
    
    if not category and not transaction_type:
        flash('A rule must specify at least a category or a transaction type to set.', 'danger')
        return redirect(url_for('rules'))

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
    flash('Rule created successfully.', 'success')
    return redirect(url_for('rules'))

@app.route('/delete_rule/<int:rule_id>')
def delete_rule(rule_id):
    rule = Rule.query.get_or_404(rule_id)
    if rule.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(rule)
    db.session.commit()
    flash('Rule deleted successfully.', 'success')
    return redirect(url_for('rules'))

@app.route('/edit_rule/<int:rule_id>', methods=['GET', 'POST'])
def edit_rule(rule_id):
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
        rule.is_automatic = request.form.get('is_automatic') == 'true'
        include_accounts = request.form.getlist('include_accounts')
        exclude_accounts = request.form.getlist('exclude_accounts')

        # Basic validation
        if not rule.keyword and not (rule.condition and value_str):
            flash('A rule must have at least a keyword or a value condition.', 'danger')
            return redirect(url_for('edit_rule', rule_id=rule_id))
        
        if not rule.category and not rule.transaction_type:
            flash('A rule must specify at least a category or a transaction type to set.', 'danger')
            return redirect(url_for('edit_rule', rule_id=rule_id))

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
        rule.accounts.clear()

        for account_id in include_set:
            link = RuleAccountLink(account_id=account_id, is_exclusion=False)
            rule.accounts.append(link)

        for account_id in exclude_set:
            link = RuleAccountLink(account_id=account_id, is_exclusion=True)
            rule.accounts.append(link)

        db.session.commit()
        flash('Rule updated successfully.', 'success')
        return redirect(url_for('rules'))
    else:
        accounts = Account.query.filter_by(client_id=session['client_id']).order_by(Account.name).all()
        return render_template('edit_rule.html', rule=rule, accounts=accounts)