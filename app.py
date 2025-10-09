from dotenv import load_dotenv
import os
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path, override=True)

from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_apscheduler import APScheduler
from sqlalchemy import func
import csv
import io
from datetime import datetime, timedelta
from collections import defaultdict, OrderedDict
import json
import markdown
import jwt, hashlib
import plaid
from plaid.api import plaid_api
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.link_token_get_request import LinkTokenGetRequest
from plaid.model.link_token_create_request_update import LinkTokenCreateRequestUpdate
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest

import os

from markupsafe import Markup
import click
from flask.cli import with_appcontext

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, timedelta):
            return str(obj)
        return JSONEncoder.default(self, obj)

from flask_talisman import Talisman

app = Flask(__name__)

csp = {
    "default-src": "'self'",
    "base-uri": "'self'",
    "object-src": "'none'",

    # Plaid + your libs. Keep 'unsafe-eval' only if you actually need it.
    "script-src": [
        "'self'", "'unsafe-inline'", "'unsafe-eval'",
        "https://cdn.plaid.com", "https://plaid.com", "https://*.plaid.com",
        "https://seondnsresolve.com", "https://*.seondnsresolve.com",
        "https://seon.io", "https://*.seon.io",
        "https://code.jquery.com", "https://cdn.datatables.net",
        "https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com",
        "blob:"  # (not used to allow workers; included for completeness if any inline blob scripts)
    ],

    "style-src": [
        "'self'", "'unsafe-inline'",
        "https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com", "https://cdn.datatables.net",
        # remove localhost:8001 in prod
        "http://localhost:8001"
    ],

    # Plaid renders in iframes you open – allow their frames
    "frame-src": [
        "https://cdn.plaid.com", "https://plaid.com", "https://*.plaid.com"
    ],

    # XHR/fetch destinations – be explicit about cdn.plaid.com too
    "connect-src": [
        "'self'",
        "https://cdn.plaid.com", "https://plaid.com", "https://*.plaid.com",
        "https://analytics.plaid.com",
        "https://seondnsresolve.com", "https://*.seondnsresolve.com",
        "https://seon.io", "https://*.seon.io",
        "https://cdn.jsdelivr.net",
        # dev-only:
        "http://127.0.0.1:8001", "https://logical-books.lotr.lan"
    ],

    # Fonts + images
    "font-src": ["'self'", "https://cdnjs.cloudflare.com", "https://cdn.jsdelivr.net", "data:"],
    "img-src":  ["'self'", "data:", "https://cdn.plaid.com", "https://plaid.com", "https://*.plaid.com"],

    # Critical: allow workers from blob: and Plaid CDN
    "worker-src": [
        "'self'", "blob:", "https://cdn.plaid.com", "https://plaid.com", "https://*.plaid.com",
        "https://seondnsresolve.com", "https://*.seondnsresolve.com",
        "https://seon.io", "https://*.seon.io"
    ],

    # Backstop for older browsers that ignore worker-src
    #"child-src": ["'self'", "blob:"],
}

# Talisman(app,
#     content_security_policy=csp,
#     permissions_policy={
#         # tighten if you don't need these features
#         "encrypted-media": "()",
#         "accelerometer": "()",
#         "camera": "()",
#         "geolocation": "()",
#         "gyroscope": "()",
#         "magnetometer": "()",
#         "microphone": "()",
#         "payment": "()",
#         "usb": "()",
#     }
# )

import logging
logging.basicConfig(level=logging.INFO)
app.json_encoder = CustomJSONEncoder

@app.template_filter('tojson')
def tojson_filter(obj):
    return json.dumps(obj)


@app.template_filter('nl2br')
def nl2br(s):
    return Markup(s.replace('\n', '<br>\n')) if s else ''

app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True
)

app.config['SECRET_KEY'] = 'your_secret_key'  # Change this in a real application
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'bookkeeping.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Plaid client setup
PLAID_CLIENT_ID = os.environ.get('PLAID_CLIENT_ID')
PLAID_SECRET = os.environ.get('PLAID_SECRET')
PLAID_ENV = os.environ.get('PLAID_ENV', 'sandbox')
PLAID_PRODUCTS = os.environ.get('PLAID_PRODUCTS', 'transactions').split(',')
PLAID_COUNTRY_CODES = os.environ.get('PLAID_COUNTRY_CODES', 'US').split(',')
PLAID_WEBHOOK_URL = os.environ.get('PLAID_WEBHOOK_URL')

if PLAID_ENV == 'sandbox':
    host = plaid.Environment.Sandbox
elif PLAID_ENV == 'development':
    host = plaid.Environment.Development
elif PLAID_ENV == 'production':
    host = plaid.Environment.Production
else:
    raise ValueError("Invalid PLAID_ENV")

configuration = plaid.Configuration(
    host=host,
    api_key={
        'clientId': PLAID_CLIENT_ID,
        'secret': PLAID_SECRET,
    }
)

api_client = plaid.ApiClient(configuration)
plaid_client = plaid_api.PlaidApi(api_client)



def verify_plaid_webhook(req):
    try:
        # Don’t assume JSON is present
        data = req.get_json(force=False, silent=True)
        if data is None:
            app.logger.warning('Plaid webhook with no/invalid JSON body; headers=%s', dict(req.headers))
            return True, None  # If you can’t verify, don’t 500—just accept and log

        # If you do signature verification, do it here against headers
        # (Plaid sends verification headers; if not configured, skip)
        return True, None
    except Exception as e:
        app.logger.error(f"Error during webhook verification: {e}")
        return False, ('invalid_webhook', 400)





db = SQLAlchemy(app)
migrate = Migrate(app, db)
scheduler = APScheduler()

if __name__ == '__main__':
    app.run(debug=True, port=8001)

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

class PlaidAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plaid_item_id = db.Column(db.Integer, db.ForeignKey('plaid_item.id'), nullable=False)
    account_id = db.Column(db.String(100), nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    mask = db.Column(db.String(10), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    subtype = db.Column(db.String(50), nullable=False)
    plaid_item = db.relationship('PlaidItem', backref=db.backref('plaid_accounts', lazy=True, cascade="all, delete-orphan"))
    local_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    local_account = db.relationship('Account', backref=db.backref('plaid_accounts', lazy=True))

class PlaidItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    item_id = db.Column(db.String(100), nullable=False, unique=True)
    access_token = db.Column(db.String(100), nullable=False)
    institution_name = db.Column(db.String(100), nullable=True)
    institution_id = db.Column(db.String(100), nullable=True) # Making it nullable to avoid breaking existing data
    last_synced = db.Column(db.DateTime, nullable=True)
    cursor = db.Column(db.String(256), nullable=True)
    client = db.relationship('Client', backref=db.backref('plaid_items', lazy=True))

class PendingPlaidLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    link_token = db.Column(db.String(256), nullable=False, unique=True, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    purpose = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    contact_name = db.Column(db.String(100))
    contact_email = db.Column(db.String(120))
    contact_phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    notes = db.Column(db.Text)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

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
    current_balance = db.Column(db.Float, nullable=True)
    balance_last_updated = db.Column(db.DateTime, nullable=True)

class JournalEntry(db.Model):
    __tablename__ = 'journal_entries'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
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
    reversal_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='posted') # posted, voided
    transaction_type = db.Column(db.String(20), nullable=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id'))
    transaction = db.relationship('Transaction', foreign_keys=[transaction_id])
    debit_account = db.relationship('Account', foreign_keys=[debit_account_id])
    credit_account = db.relationship('Account', foreign_keys=[credit_account_id])
    documents = db.relationship('Document', backref='journal_entry', cascade="all, delete-orphan")
    reconciliation_id = db.Column(db.Integer, db.ForeignKey('reconciliation.id'), nullable=True)

class Reconciliation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    statement_date = db.Column(db.Date, nullable=False)
    statement_balance = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    account = db.relationship('Account', backref='reconciliations')
    journal_entries = db.relationship('JournalEntry', backref='reconciliation')

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
    period = db.Column(db.String(20), nullable=False, default='monthly') # monthly, quarterly, yearly
    start_date = db.Column(db.Date, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

class TransactionRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(100))
    category_condition = db.Column(db.Text, nullable=True)
    transaction_type = db.Column(db.String(10))  # 'debit' or 'credit'
    min_amount = db.Column(db.Float)
    max_amount = db.Column(db.Float)
    new_category = db.Column(db.String(100))
    new_description = db.Column(db.String(200))
    new_debit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    new_credit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    is_automatic = db.Column(db.Boolean, default=True)
    delete_transaction = db.Column(db.Boolean, default=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    source_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)

    new_debit_account = db.relationship('Account', foreign_keys=[new_debit_account_id])
    new_credit_account = db.relationship('Account', foreign_keys=[new_credit_account_id])
    source_account = db.relationship('Account', foreign_keys=[source_account_id])

class FinancialPeriod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
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
    purchase_date = db.Column(db.Date, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    useful_life = db.Column(db.Integer, nullable=False) # in years
    salvage_value = db.Column(db.Float, nullable=False, default=0.0)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

class Depreciation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
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
    date = db.Column(db.Date, nullable=False)
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
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    debit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    credit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(200))
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    is_approved = db.Column(db.Boolean, nullable=False, default=False)
    debit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    credit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    rule_modified = db.Column(db.Boolean, nullable=False, default=False)
    source_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    source_account = db.relationship('Account', foreign_keys=[source_account_id])
    plaid_transaction_id = db.Column(db.String(100), nullable=True, unique=True)

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
            start_date = transaction.start_date
            if transaction.end_date:
                end_date = transaction.end_date
                if today < start_date or today > end_date:
                    continue
            elif today < start_date:
                continue

            # Check if a journal entry has already been created for the current period
            last_journal_entry = JournalEntry.query.filter_by(description=transaction.description).order_by(JournalEntry.date.desc()).first()
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
                client_id=session['client_id']
            )
            db.session.add(new_entry)
        db.session.commit()

@scheduler.task('cron', id='cleanup_pending_plaid_links', day='*', hour=2) # Run daily at 2am
def cleanup_pending_plaid_links():
    with app.app_context():
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        expired_links = PendingPlaidLink.query.filter(PendingPlaidLink.created_at < seven_days_ago).all()
        if expired_links:
            for link in expired_links:
                db.session.delete(link)
            db.session.commit()
            logging.info(f"Cleaned up {len(expired_links)} expired pending Plaid links.")





@app.route('/transactions')
def transactions():
    transactions = Transaction.query.options(db.joinedload(Transaction.source_account)).filter_by(client_id=session['client_id']).order_by(Transaction.date.desc()).all()
    return render_template('transactions.html', transactions=transactions)

@app.route('/add_transaction', methods=['GET', 'POST'])
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
        return redirect(url_for('transactions'))
    return render_template('add_transaction.html')

@app.route('/edit_transaction/<int:transaction_id>', methods=['GET', 'POST'])
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

@app.route('/delete_transactions', methods=['POST'])
def delete_transactions():
    transaction_ids = request.form.getlist('transaction_ids')
    if not transaction_ids:
        flash('No transactions selected.', 'warning')
        return redirect(url_for('transactions'))

    Transaction.query.filter(Transaction.id.in_(transaction_ids), Transaction.client_id == session['client_id']).delete(synchronize_session=False)
    db.session.commit()
    flash(f'{len(transaction_ids)} transactions deleted successfully.', 'success')
    return redirect(url_for('transactions'))

@app.route('/cleanup_orphaned_transactions')
def cleanup_orphaned_transactions():
    orphaned_transactions = db.session.query(Transaction).outerjoin(JournalEntry, Transaction.id == JournalEntry.transaction_id).filter(Transaction.is_approved, JournalEntry.id is None).all()
    for transaction in orphaned_transactions:
        db.session.delete(transaction)
    db.session.commit()
    flash(f'{len(orphaned_transactions)} orphaned transactions have been deleted.', 'success')
    return redirect(url_for('transactions'))

@app.route('/unapproved')
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

@app.route('/delete_duplicates')
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

    return redirect(url_for('unapproved_transactions'))



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
            category=transaction.category,
            transaction_id=transaction.id,
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
    apply_transaction_rules(transactions_to_update, automatic_only=False)
    run_category_rules(transactions_to_update)
    db.session.commit()
    flash(f'{len(transactions_to_update)} transactions updated successfully based on rules.', 'success')
    return redirect(url_for('unapproved_transactions'))

@app.route('/bulk_assign_accounts', methods=['POST'])
def bulk_assign_accounts():
    transaction_ids = request.form.getlist('transaction_ids')
    debit_account_id = request.form.get('bulk_debit_account_id')
    credit_account_id = request.form.get('bulk_credit_account_id')

    if not transaction_ids:
        flash('No transactions selected.', 'warning')
        return redirect(url_for('unapproved_transactions'))

    if not debit_account_id or not credit_account_id:
        flash('Please select both a debit and a credit account.', 'danger')
        return redirect(url_for('unapproved_transactions'))

    update_data = {
        'debit_account_id': debit_account_id,
        'credit_account_id': credit_account_id,
        'rule_modified': True
    }

    Transaction.query.filter(Transaction.id.in_(transaction_ids), Transaction.client_id == session['client_id']).update(update_data, synchronize_session=False)

    db.session.commit()
    flash(f'{len(transaction_ids)} transactions updated successfully.', 'success')
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
    if 'client_id' not in session and request.endpoint not in ['clients', 'add_client', 'select_client', 'edit_client', 'delete_client', 'plaid_webhook', 'debug_link_token', 'plaid_oauth_return']:
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
    TransactionRule.query.filter_by(client_id=client_id).delete()
    db.session.delete(client)
    db.session.commit()
    flash('Client deleted successfully.', 'success')
    # Clear the session if the deleted client was the active one
    if session.get('client_id') == client_id:
        session.pop('client_id', None)
    return redirect(url_for('clients'))

@app.route('/vendors')
def vendors():
    vendors = Vendor.query.filter_by(client_id=session['client_id']).order_by(Vendor.name).all()
    return render_template('vendors.html', vendors=vendors)

@app.route('/add_vendor', methods=['GET', 'POST'])
def add_vendor():
    if request.method == 'POST':
        if Vendor.query.filter_by(name=request.form['name'], client_id=session['client_id']).first():
            flash(f'Vendor "{request.form["name"]}" already exists.', 'danger')
            return redirect(url_for('vendors'))
        new_vendor = Vendor(
            name=request.form['name'],
            contact_name=request.form['contact_name'],
            contact_email=request.form['contact_email'],
            contact_phone=request.form['contact_phone'],
            address=request.form['address'],
            notes=request.form['notes'],
            client_id=session['client_id']
        )
        db.session.add(new_vendor)
        db.session.commit()
        flash(f'Vendor "{new_vendor.name}" created successfully.', 'success')
        return redirect(url_for('vendors'))
    return render_template('add_vendor.html')

@app.route('/edit_vendor/<int:vendor_id>', methods=['GET', 'POST'])
def edit_vendor(vendor_id):
    vendor = Vendor.query.get_or_404(vendor_id)
    if vendor.client_id != session['client_id']:
        return "Unauthorized", 403
    if request.method == 'POST':
        if Vendor.query.filter(Vendor.name == request.form['name'], Vendor.id != vendor_id, Vendor.client_id == session['client_id']).first():
            flash(f'Vendor with name "{request.form["name"]}" already exists.', 'danger')
            return redirect(url_for('edit_vendor', vendor_id=vendor_id))
        
        vendor.name = request.form['name']
        vendor.contact_name = request.form['contact_name']
        vendor.contact_email = request.form['contact_email']
        vendor.contact_phone = request.form['contact_phone']
        vendor.address = request.form['address']
        vendor.notes = request.form['notes']
        
        db.session.commit()
        flash('Vendor updated successfully.', 'success')
        return redirect(url_for('vendors'))
    else:
        return render_template('edit_vendor.html', vendor=vendor)

@app.route('/delete_vendor/<int:vendor_id>')
def delete_vendor(vendor_id):
    vendor = Vendor.query.get_or_404(vendor_id)
    if vendor.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(vendor)
    db.session.commit()
    flash('Vendor deleted successfully.', 'success')
    return redirect(url_for('vendors'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    client_id = session.get('client_id')
    if not client_id:
        return redirect(url_for('clients'))

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
        JournalEntry.date >= start_date,
        JournalEntry.date <= end_date,
        JournalEntry.category is not None,
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
    budgets = Budget.query.filter_by(client_id=session['client_id']).all()
    performance_data = []
    for budget in budgets:
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

            actual_spent = db.session.query(db.func.sum(JournalEntry.amount)) \
                .filter(JournalEntry.category == budget.category) \
                .filter(JournalEntry.date >= period_start) \
                .filter(JournalEntry.date <= period_end) \
                .scalar() or 0

            history.append({
                'period_name': period_name,
                'budgeted': budget.amount,
                'actual': actual_spent,
                'difference': budget.amount - actual_spent
            })

        performance_data.append({
            'category_name': budget.category,
            'period': budget.period,
            'amount': budget.amount,
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

def get_spending_by_category(start_date, end_date):
    spending_query = db.session.query(
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntry.client_id == session['client_id'],
        JournalEntry.category is not None,
        JournalEntry.category != '',
        JournalEntry.date.between(start_date, end_date)
    ).group_by(JournalEntry.category)
    
    return {item.category: item.total for item in spending_query.all()}

@app.route('/analysis', methods=['GET', 'POST'])
def analysis():
    if request.method == 'POST':
        start_date_1 = datetime.strptime(request.form['start_date_1'], '%Y-%m-%d').date()
        end_date_1 = datetime.strptime(request.form['end_date_1'], '%Y-%m-%d').date()
        start_date_2 = datetime.strptime(request.form['start_date_2'], '%Y-%m-%d').date()
        end_date_2 = datetime.strptime(request.form['end_date_2'], '%Y-%m-%d').date()
    else:
        # Default to this month vs. last month
        today = datetime.now().date()
        start_date_1 = today.replace(day=1)
        end_date_1 = today
        
        last_month_end = start_date_1 - timedelta(days=1)
        start_date_2 = last_month_end.replace(day=1)
        end_date_2 = last_month_end

    # Spending by Category for period 1 (for the pie chart)
    spending_by_category_1_dict = get_spending_by_category(start_date_1, end_date_1)
    spending_by_category_1 = sorted(spending_by_category_1_dict.items(), key=lambda item: item[1], reverse=True)

    category_labels = json.dumps([item[0] for item in spending_by_category_1])
    category_data = json.dumps([item[1] for item in spending_by_category_1])

    # Data for category comparison bar chart
    spending_by_category_2_dict = get_spending_by_category(start_date_2, end_date_2)
    all_categories = sorted(list(set(spending_by_category_1_dict.keys()) | set(spending_by_category_2_dict.keys())))
    
    category_comparison_labels = json.dumps(all_categories)
    category_comparison_data_1 = json.dumps([spending_by_category_1_dict.get(c, 0) for c in all_categories])
    category_comparison_data_2 = json.dumps([spending_by_category_2_dict.get(c, 0) for c in all_categories])


    # Income vs. Expense Trend
    income_by_month_query = db.session.query(
        db.func.strftime('%Y-%m', JournalEntry.date).label('month'),
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.credit_account_id == Account.id).filter(
        Account.type.in_(['Revenue', 'Income']),
        JournalEntry.client_id == session['client_id']
    ).group_by('month')

    expense_by_month_query = db.session.query(
        db.func.strftime('%Y-%m', JournalEntry.date).label('month'),
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntry.client_id == session['client_id']
    ).group_by('month')

    income_by_month = {r.month: r.total for r in income_by_month_query.all()}
    expense_by_month = {r.month: r.total for r in expense_by_month_query.all()}

    all_months = sorted(list(set(income_by_month.keys()) | set(expense_by_month.keys())))

    income_trend_data = json.dumps([income_by_month.get(m, 0) for m in all_months])
    expense_trend_data = json.dumps([expense_by_month.get(m, 0) for m in all_months])

    # Cash Flow
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

    return render_template('analysis.html', 
                           spending_by_category=spending_by_category_1,
                           category_labels=category_labels,
                           category_data=category_data,
                           all_months=all_months,
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
                           cash_at_end_of_period=cash_at_end_of_period,
                           start_date_1=start_date_1.strftime('%Y-%m-%d'),
                           end_date_1=end_date_1.strftime('%Y-%m-%d'),
                           start_date_2=start_date_2.strftime('%Y-%m-%d'),
                           end_date_2=end_date_2.strftime('%Y-%m-%d'),
                           category_comparison_labels=category_comparison_labels,
                           category_comparison_data_1=category_comparison_data_1,
                           category_comparison_data_2=category_comparison_data_2
                           )


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
    start_date_str = request.args.get('start_date', datetime.now().replace(day=1).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    expense_breakdown_query = db.session.query(
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.debit_account_id == Account.id).filter(
        Account.type == 'Expense',
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date,
        JournalEntry.date <= end_date,
        JournalEntry.category is not None,
        JournalEntry.category != ''
    ).group_by(JournalEntry.category)

    expense_breakdown = expense_breakdown_query.all()

    pie_chart_labels = json.dumps([item.category for item in expense_breakdown])
    pie_chart_data = json.dumps([item.total for item in expense_breakdown])

    return render_template('full_pie_chart.html', title='Expense Breakdown', labels=pie_chart_labels, data=pie_chart_data, start_date=start_date.strftime('%Y-%m-%d'), end_date=end_date.strftime('%Y-%m-%d'))

@app.route('/full_pie_chart_income')
def full_pie_chart_income():
    start_date_str = request.args.get('start_date', datetime.now().replace(day=1).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    income_breakdown_query = db.session.query(
        JournalEntry.category,
        db.func.sum(JournalEntry.amount).label('total')
    ).join(Account, JournalEntry.credit_account_id == Account.id).filter(
        Account.type.in_(['Revenue', 'Income']),
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date,
        JournalEntry.date <= end_date,
        JournalEntry.category is not None,
        JournalEntry.category != ''
    ).group_by(JournalEntry.category)

    income_breakdown = income_breakdown_query.all()

    pie_chart_labels = json.dumps([item.category for item in income_breakdown])
    pie_chart_data = json.dumps([item.total for item in income_breakdown])

    return render_template('full_pie_chart.html', title='Income Breakdown', labels=pie_chart_labels, data=pie_chart_data, start_date=start_date.strftime('%Y-%m-%d'), end_date=end_date.strftime('%Y-%m-%d'))

@app.route('/accounts')
def accounts():
    account_choices = get_account_choices(session['client_id'])
    
    # Use a recursive function to build the list in order
    def get_accounts_recursive(parent_id, level):
        accounts = Account.query.filter_by(client_id=session['client_id'], parent_id=parent_id).order_by(Account.name).all()
        acc_list = []
        for account in accounts:
            is_parent = account.children.first() is not None
            acc_list.append({
                'id': account.id,
                'name': account.name,
                'type': account.type,
                'category': account.category,
                'parent_id': account.parent_id,
                'level': level,
                'is_parent': is_parent
            })
            acc_list.extend(get_accounts_recursive(account.id, level + 1))
        return acc_list

    accounts_data = get_accounts_recursive(None, 0)

    return render_template('accounts.html', 
                           account_choices=account_choices, 
                           accounts_data=accounts_data)

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
            query = query.filter(JournalEntry.description.ilike(f"%{filters['description']}%"))
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

@app.route('/add_entry', methods=['POST'])
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
    return redirect(url_for('journal'))

@app.route('/edit_entry/<int:entry_id>', methods=['GET', 'POST'])
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
    return redirect(url_for('journal'))

@app.route('/unapprove_transaction/<int:entry_id>')
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
        # This is a bit of a hack, as apply_transaction_rules expects Transaction objects, not JournalEntry objects.
        # However, they share the same relevant fields (description, amount, category, debit_account_id, credit_account_id).
        # A better solution would be to refactor the rule application logic to be more generic.
        apply_transaction_rules(entries_to_update)
        db.session.commit()
        flash(f'{len(entries_to_update)} entries updated successfully based on rules.', 'success')
    
    return redirect(url_for('journal'))

@app.route('/delete_duplicate_journal_entries')
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

def apply_transaction_rules(transactions, automatic_only=True):
    query = TransactionRule.query.filter_by(client_id=session['client_id'])
    if automatic_only:
        query = query.filter_by(is_automatic=True)
    rules = query.all()
    for transaction in transactions:
        for rule in rules:
            # Keyword
            if rule.keyword and rule.keyword.lower() not in transaction.description.lower():
                continue

            # Category
            if rule.category_condition and transaction.category not in rule.category_condition.split(','):
                continue

            # Amount
            if rule.min_amount is not None and transaction.amount < rule.min_amount:
                continue
            if rule.max_amount is not None and transaction.amount > rule.max_amount:
                continue

            # Type
            if rule.transaction_type:
                if rule.transaction_type == 'debit' and transaction.amount >= 0:
                    continue
                if rule.transaction_type == 'credit' and transaction.amount < 0:
                    continue

            # Source Account
            if rule.source_account_id and rule.source_account_id != transaction.source_account_id:
                continue
            
            # If all conditions are met, apply actions
            if rule.delete_transaction:
                if isinstance(transaction, Transaction):
                    db.session.delete(transaction)
                break # Move to the next transaction

            if rule.new_category:
                transaction.category = rule.new_category
            if rule.new_description:
                transaction.description = rule.new_description
            if rule.new_debit_account_id:
                transaction.debit_account_id = rule.new_debit_account_id
            if rule.new_credit_account_id:
                transaction.credit_account_id = rule.new_credit_account_id
            transaction.rule_modified = True

@app.route('/import_csv', methods=['POST'])
def import_csv():
    files = request.files.getlist('csv_files')
    account_id = request.form['account']

    template = ImportTemplate.query.filter_by(account_id=account_id).first()
    if not template:
        flash('No import template found for the selected account.', 'danger')
        return redirect(url_for('import_page'))

    for file in files:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.reader(stream)

        if template.has_header:
            next(csv_reader)
        
        transactions = []
        for row in csv_reader:
            try:
                date_str = normalize_date(row[template.date_col])
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
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
                    date=date, description=description, amount=amount, category=category, client_id=session['client_id'], source_account_id=account_id
                )
                db.session.add(new_transaction)
                transactions.append(new_transaction)
            except (ValueError, IndexError) as e:
                flash(f'Error processing row: {row}. Error: {e}', 'danger')
                db.session.rollback()
                return redirect(url_for('journal'))
        run_category_rules(transactions)
        apply_transaction_rules(transactions)

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

    # Debugging info
    asset_ids = [acc.id for acc in Account.query.filter_by(client_id=session['client_id'], type='Asset').all()]
    total_asset_debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id.in_(asset_ids)).scalar() or 0
    total_asset_credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id.in_(asset_ids)).scalar() or 0

    liability_ids = [acc.id for acc in Account.query.filter_by(client_id=session['client_id'], type='Liability').all()]
    total_liability_debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id.in_(liability_ids)).scalar() or 0
    total_liability_credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id.in_(liability_ids)).scalar() or 0

    equity_ids = [acc.id for acc in Account.query.filter_by(client_id=session['client_id'], type='Equity').all()]
    total_equity_debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id.in_(equity_ids)).scalar() or 0
    total_equity_credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id.in_(equity_ids)).scalar() or 0

    revenue_ids = [acc.id for acc in Account.query.filter_by(client_id=session['client_id'], type='Revenue').all()]
    total_revenue_debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id.in_(revenue_ids)).scalar() or 0
    total_revenue_credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id.in_(revenue_ids)).scalar() or 0

    expense_ids = [acc.id for acc in Account.query.filter_by(client_id=session['client_id'], type='Expense').all()]
    total_expense_debits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.debit_account_id.in_(expense_ids)).scalar() or 0
    total_expense_credits = db.session.query(db.func.sum(JournalEntry.amount)).filter(JournalEntry.credit_account_id.in_(expense_ids)).scalar() or 0


    return render_template('balance_sheet.html', 
                           asset_data=asset_data, 
                           liability_data=liability_data, 
                           equity_data=equity_data, 
                           total_assets=total_assets, 
                           total_liabilities=total_liabilities, 
                           total_equity=total_equity,
                           is_balanced=is_balanced,
                           debug_info={
                               'total_asset_debits': total_asset_debits,
                               'total_asset_credits': total_asset_credits,
                               'total_liability_debits': total_liability_debits,
                               'total_liability_credits': total_liability_credits,
                               'total_equity_debits': total_equity_debits,
                               'total_equity_credits': total_equity_credits,
                               'total_revenue_debits': total_revenue_debits,
                               'total_revenue_credits': total_revenue_credits,
                               'total_expense_debits': total_expense_debits,
                               'total_expense_credits': total_expense_credits,
                           })

@app.route('/reconcile/<int:account_id>', methods=['GET', 'POST'])
def reconcile_account(account_id):
    account = Account.query.get_or_404(account_id)
    if account.client_id != session['client_id']:
        return "Unauthorized", 403

    if request.method == 'POST':
        statement_date = datetime.strptime(request.form['statement_date'], '%Y-%m-%d').date()
        statement_balance = float(request.form['statement_balance'])
        journal_entry_ids = request.form.getlist('journal_entry_ids')

        new_reconciliation = Reconciliation(
            account_id=account_id,
            statement_date=statement_date,
            statement_balance=statement_balance,
            client_id=session['client_id']
        )
        db.session.add(new_reconciliation)
        db.session.commit()

        JournalEntry.query.filter(JournalEntry.id.in_(journal_entry_ids)).update(
            {'reconciliation_id': new_reconciliation.id},
            synchronize_session=False
        )
        db.session.commit()

        flash('Reconciliation saved successfully.', 'success')
        return redirect(url_for('balance_sheet'))

    entries = JournalEntry.query.filter(
        db.or_(JournalEntry.debit_account_id == account_id, JournalEntry.credit_account_id == account_id),
        JournalEntry.reconciliation_id == None,
        JournalEntry.client_id == session['client_id']
    ).order_by(JournalEntry.date).all()

    return render_template('reconciliation.html', account=account, entries=entries)

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
        period = request.form['period']
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()

        # Check if a budget for this category and period already exists
        if Budget.query.filter_by(category=category, period=period, start_date=start_date, client_id=session['client_id']).first():
            flash(f'A budget for this category and period already exists.', 'danger')
            return redirect(url_for('budget'))

        new_budget = Budget(category=category,
            amount=amount,
            period=period,
            start_date=start_date,
            client_id=session['client_id']
        )
        db.session.add(new_budget)
        db.session.commit()
        flash('Budget created successfully.', 'success')
        return redirect(url_for('budget'))
    else:
        budgets = Budget.query.filter_by(client_id=session['client_id']).all()
        budget_data = []
        for b in budgets:
            # Calculate actual spending for the budget period
            start = b.start_date
            if b.period == 'monthly':
                end = start.replace(day=28) + timedelta(days=4) # last day of month
                end = end - timedelta(days=end.day)
            elif b.period == 'quarterly':
                end = start + timedelta(days=90)
            else: # yearly
                end = start.replace(year=start.year + 1) - timedelta(days=1)

            actual_spent = db.session.query(db.func.sum(JournalEntry.amount)) \
                .filter(JournalEntry.category == b.category) \
                .filter(JournalEntry.date >= b.start_date) \
                .filter(JournalEntry.date <= end) \
                .scalar() or 0

            budget_data.append({
                'id': b.id,
                'category_name': b.category,
                'amount': b.amount,
                'period': b.period,
                'start_date': b.start_date,
                'actual_spent': actual_spent,
                'remaining': b.amount - actual_spent
            })

        categories = [c[0] for c in db.session.query(JournalEntry.category).filter(JournalEntry.client_id == session['client_id']).distinct().all() if c[0]]
        return render_template('budget.html', budgets=budget_data, categories=categories)



@app.route('/delete_budget/<int:budget_id>')
def delete_budget(budget_id):
    budget = Budget.query.get_or_404(budget_id)
    if budget.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(budget)
    db.session.commit()
    flash('Budget deleted successfully.', 'success')
    return redirect(url_for('budget'))

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

@app.route('/transaction_rules')
def transaction_rules():
    rules = TransactionRule.query.options(db.joinedload(TransactionRule.source_account)).filter_by(client_id=session['client_id']).all()
    
    rules_by_source = {}
    for rule in rules:
        if rule.source_account:
            if rule.source_account.name not in rules_by_source:
                rules_by_source[rule.source_account.name] = []
            rules_by_source[rule.source_account.name].append(rule)
        else:
            if 'Unassigned' not in rules_by_source:
                rules_by_source['Unassigned'] = []
            rules_by_source['Unassigned'].append(rule)

    sorted_rules_by_source = OrderedDict(sorted(rules_by_source.items()))
            
    return render_template('transaction_rules.html', rules_by_source=sorted_rules_by_source)

@app.route('/get_categories_for_account/<int:account_id>')
def get_categories_for_account(account_id):
    categories = db.session.query(Transaction.category).filter_by(source_account_id=account_id, client_id=session['client_id']).distinct().all()
    return json.dumps([c[0] for c in categories if c[0]])

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

@app.route('/add_transaction_rule', methods=['GET', 'POST'])
def add_transaction_rule():
    categories = db.session.query(Transaction.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]
    accounts_choices = get_account_choices(session['client_id'])
    accounts = []
    for account_id, account_name, level in accounts_choices:
        indent = '&nbsp;' * level * 4
        accounts.append((account_id, Markup(f"{indent}{account_name}")))

    if request.method == 'POST':
        keyword = request.form.get('keyword')
        category_condition = ",".join(request.form.getlist('category_condition'))
        transaction_type = request.form.get('transaction_type')
        min_amount_str = request.form.get('min_amount')
        max_amount_str = request.form.get('max_amount')
        min_amount = float(min_amount_str) if min_amount_str else None
        max_amount = float(max_amount_str) if max_amount_str else None
        new_category = request.form.get('new_category')
        new_description = request.form.get('new_description')
        new_debit_account_id = request.form.get('new_debit_account_id')
        new_credit_account_id = request.form.get('new_credit_account_id')
        source_account_id = request.form.get('source_account_id')
        is_automatic = request.form.get('is_automatic') == 'true'
        delete_transaction = request.form.get('delete_transaction') == 'true'
        client_id = session['client_id']

        if not keyword and min_amount is None and max_amount is None and not category_condition:
            flash('A rule must have at least a keyword, a category, or a value condition.', 'danger')
            return render_template('add_transaction_rule.html', clients=Client.query.all(), categories=categories, accounts=accounts)

        new_rule = TransactionRule(
            keyword=keyword,
            category_condition=category_condition,
            transaction_type=transaction_type,
            min_amount=min_amount,
            max_amount=max_amount,
            new_category=new_category,
            new_description=new_description,
            new_debit_account_id=int(new_debit_account_id) if new_debit_account_id else None,
            new_credit_account_id=int(new_credit_account_id) if new_credit_account_id else None,
            source_account_id=int(source_account_id) if source_account_id else None,
            is_automatic=is_automatic,
            delete_transaction=delete_transaction,
            client_id=client_id
        )
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
    rule = TransactionRule.query.get_or_404(rule_id)
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
    rule = TransactionRule.query.get_or_404(rule_id)
    if rule.client_id != session['client_id']:
        return "Unauthorized", 403
    categories = db.session.query(Transaction.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]
    accounts_choices = get_account_choices(session['client_id'])
    accounts = []
    for account_id, account_name, level in accounts_choices:
        indent = '&nbsp;' * level * 4
        accounts.append((account_id, Markup(f"{indent}{account_name}")))

    if request.method == 'POST':
        rule.keyword = request.form.get('keyword')
        rule.category_condition = ",".join(request.form.getlist('category_condition'))
        rule.transaction_type = request.form.get('transaction_type')
        min_amount_str = request.form.get('min_amount')
        max_amount_str = request.form.get('max_amount')
        rule.min_amount = float(min_amount_str) if min_amount_str else None
        rule.max_amount = float(max_amount_str) if max_amount_str else None
        rule.new_category = request.form.get('new_category')
        rule.new_description = request.form.get('new_description')
        rule.new_debit_account_id = int(request.form.get('new_debit_account_id')) if request.form.get('new_debit_account_id') else None
        rule.new_credit_account_id = int(request.form.get('new_credit_account_id')) if request.form.get('new_credit_account_id') else None
        rule.source_account_id = int(request.form.get('source_account_id')) if request.form.get('source_account_id') else None
        rule.is_automatic = request.form.get('is_automatic') == 'true'
        rule.delete_transaction = request.form.get('delete_transaction') == 'true'

        if not rule.keyword and rule.min_amount is None and rule.max_amount is None and not rule.category_condition:
            flash('A rule must have at least a keyword, a category, or a value condition.', 'danger')
            return render_template('edit_transaction_rule.html', rule=rule, categories=categories, accounts=accounts)

        db.session.commit()
        flash('Transaction rule updated successfully.', 'success')
        return redirect(url_for('transaction_rules'))
    else:
        return render_template('edit_transaction_rule.html', rule=rule, categories=categories, accounts=accounts)

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
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
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
    start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
    end_date_str = request.form['end_date']
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
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
                    date=today.date(),
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

@app.route('/fixed_assets')
def fixed_assets():
    assets = FixedAsset.query.filter_by(client_id=session['client_id']).order_by(FixedAsset.purchase_date.desc()).all()
    return render_template('fixed_assets.html', assets=assets)

@app.route('/add_fixed_asset', methods=['GET', 'POST'])
def add_fixed_asset():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        purchase_date = datetime.strptime(request.form['purchase_date'], '%Y-%m-%d').date()
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
            'date': entry.date.strftime('%Y-%m-%d'),
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
                last_depreciation_date = last_depreciation.date
                if last_depreciation_date.year == today.year and last_depreciation_date.month == today.month:
                    continue

            # Record depreciation for the current month
            new_depreciation = Depreciation(
                date=today.date(),
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
                    date=today.date(),
                    description=f"Depreciation for {asset.name}",
                    debit_account_id=depreciation_expense_account.id,
                    credit_account_id=accumulated_depreciation_account.id,
                    amount=abs(monthly_depreciation),
                    client_id=session['client_id']
                )
                db.session.add(new_entry)

        db.session.commit()

@app.route('/api/transaction_analysis')
def transaction_analysis():
    start_date_str = request.args.get('start_date', datetime.now().replace(day=1).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    query = db.session.query(JournalEntry).filter(
        JournalEntry.client_id == session['client_id'],
        JournalEntry.date >= start_date,
        JournalEntry.date <= end_date
    )

    results = query.all()

    data = [
        {
            'date': r.date.strftime('%Y-%m-%d'),
            'description': r.description,
            'amount': r.amount,
            'category': r.category,
            'debit_account': r.debit_account.name if r.debit_account else '',
            'credit_account': r.credit_account.name if r.credit_account else '',
        } for r in results
    ]

    return json.dumps(data)

@app.route('/transaction_analysis')
def transaction_analysis_page():
    accounts = get_account_choices(session['client_id'])
    vendors = Vendor.query.filter_by(client_id=session['client_id']).order_by(Vendor.name).all()
    return render_template('transaction_analysis.html', accounts=accounts, vendors=vendors)

@app.route('/plaid')
def plaid_page():
    if 'client_id' not in session:
        return redirect(url_for('clients'))
    
    client_id = session.get('client_id')
    if not client_id:
        return redirect(url_for('clients'))

    client = Client.query.get(client_id)
    plaid_items = PlaidItem.query.filter_by(client_id=client_id).all()
    accounts = Account.query.filter_by(client_id=client_id).order_by(Account.name).all()
    
    return render_template('plaid.html', 
                           plaid_items=plaid_items, 
                           accounts=accounts, 
                           client=client)

@app.route('/api/current_link_token')
def current_link_token():
    t = session.get('link_token')
    if not t:
        return jsonify({'error': 'no token in session'}), 404
    return jsonify({'link_token': t})

@app.route("/oauth-return")
def plaid_oauth_return():
    app.logger.info(f"plaid_oauth_return: Incoming request URL: {request.url}")
    link_token = session.get('link_token') or request.args.get('lt')
    app.logger.info(f"plaid_oauth_return: Using link_token: {link_token[:10]}...")
    return render_template("oauth-return.html", link_token=link_token)



@app.route('/api/create_link_token', methods=['POST'])
def create_link_token():
    try:
        app.logger.info(f"create_link_token: client_id={session['client_id']}, redirect_uri={os.environ.get('PLAID_REDIRECT_URI')}")
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(
                client_user_id=str(session['client_id'])
            ),
            client_name="My App",
            products=[Products(p) for p in PLAID_PRODUCTS],
            country_codes=[CountryCode(c) for c in PLAID_COUNTRY_CODES],
            language='en',
<<<<<<< HEAD
=======
            redirect_uri=os.environ.get('PLAID_REDIRECT_URI'),
>>>>>>> feature/plaid-integration-chase
        )
        response = plaid_client.link_token_create(request)
        link_token = response['link_token']
        session['link_token'] = link_token # Store link_token in session
        app.logger.info(f"create_link_token: Generated link_token={link_token}")
        db.session.add(PendingPlaidLink(link_token=link_token, client_id=session['client_id'], purpose='standard'))
        db.session.commit()
        return jsonify(response.to_dict())
    except plaid.exceptions.ApiException as e:
        return jsonify(json.loads(e.body)), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in create_link_token: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/generate_hosted_link/<int:client_id>', methods=['POST'])
def generate_hosted_link(client_id):
    # Ensure the current user has access to this client
    if session.get('client_id') != client_id:
        return "Unauthorized", 403

    if not PLAID_WEBHOOK_URL:
        logging.error("PLAID_WEBHOOK_URL is not set in the environment.")
        return jsonify({'error': 'Server configuration error'}), 500

    try:
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(
                client_user_id=str(client_id)
            ),
            client_name="My App",
            products=[Products(p) for p in PLAID_PRODUCTS],
            country_codes=[CountryCode(c) for c in PLAID_COUNTRY_CODES],
            language='en',
            webhook=PLAID_WEBHOOK_URL,
            hosted_link={}
        )
        response = plaid_client.link_token_create(request)
        
        link_token = response['link_token']
        new_pending_link = PendingPlaidLink(link_token=link_token, client_id=client_id, purpose='hosted')
        db.session.add(new_pending_link)
        db.session.commit()

        hosted_link_url = response['hosted_link_url']
        return jsonify({'hosted_link_url': hosted_link_url})
    except plaid.exceptions.ApiException as e:
        return jsonify(json.loads(e.body)), 500

# @app.route('/api/create_link_token_sms', methods=['POST'])
# def create_link_token_sms():
#     client_id = request.json['client_id']
#     phone_number = request.json['phone_number']
# 
#     client = Client.query.get_or_404(client_id)
#     if not client:
#         return jsonify({'error': 'Client not found'}), 404
# 
#     try:
#         link_token_request = LinkTokenCreateRequest(
#             user=LinkTokenCreateRequestUser(
#                 client_user_id=str(client.id),
#                 phone_number=phone_number
#             ),
#             client_name="My App",
#             products=[Products(p) for p in PLAID_PRODUCTS],
#             country_codes=[CountryCode(c) for c in PLAID_COUNTRY_CODES],
#             language='en',
#             hosted_link={
#                 "delivery_method": "sms",
#                 "completion_redirect_uri": url_for('plaid_link_completion', _external=True),
#                 "is_mobile_app": False
#             }
#         )
#         response = plaid_client.link_token_create(link_token_request)
#         return jsonify(response.to_dict())
#     except plaid.exceptions.ApiException as e:
#         return jsonify(json.loads(e.body)), 500

@app.route('/api/create_link_token_for_update', methods=['POST'])
def create_link_token_for_update():
    plaid_item_id = request.json['plaid_item_id']
    item = PlaidItem.query.get_or_404(plaid_item_id)
    if item.client_id != session['client_id']:
        return "Unauthorized", 403

    try:
        link_token_request = LinkTokenCreateRequest(
            client_name="Logical Books",
            country_codes=[CountryCode(c) for c in PLAID_COUNTRY_CODES],
            language='en',
            access_token=item.access_token,
            redirect_uri=os.environ.get('PLAID_REDIRECT_URI'),  # ← REQUIRED for OAuth institutions
        )
        response = plaid_client.link_token_create(link_token_request)
        return jsonify(response.to_dict())
    except plaid.exceptions.ApiException as e:
        return jsonify(json.loads(e.body)), 500

def _exchange_public_token(public_token, institution_name, institution_id, client_id):
    app.logger.info(f"_exchange_public_token: public_token={public_token[:10]}..., institution_name={institution_name}, institution_id={institution_id}, client_id={client_id}")
    try:
        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_response = plaid_client.item_public_token_exchange(exchange_request)
        access_token = exchange_response['access_token']
        item_id = exchange_response['item_id']
        app.logger.info(f"_exchange_public_token: Received access_token={access_token[:10]}..., item_id={item_id}")

        # Check if this item already exists for this client
        existing_item = PlaidItem.query.filter_by(item_id=item_id, client_id=client_id).first()
        if existing_item:
            app.logger.info(f'_exchange_public_token: Item {item_id} already exists for client {client_id}. Ignoring.')
            return None, None, 'This institution is already linked.' # Indicate that no new item was created

        new_item = PlaidItem(
            client_id=client_id,
            item_id=item_id,
            access_token=access_token,
            institution_name=institution_name,
            institution_id=institution_id
        )
        db.session.add(new_item)
        db.session.commit()
        
        # Also sync accounts right away
        sync_plaid_accounts(new_item.id)

        return new_item, None, 'Bank account linked successfully!'
    except plaid.exceptions.ApiException as e:
        app.logger.error(f"_exchange_public_token: Plaid API exception during token exchange: {e.body}")
        return None, {'error': 'Plaid API error'}, None

@app.route('/api/exchange_public_token', methods=['POST'])
def exchange_public_token():
    body = request.get_json() or {}
    public_token = body.get('public_token')
    link_token   = body.get('link_token')
    app.logger.info(f"exchange_public_token: Received public_token={public_token[:10]}..., link_token={link_token[:10]}...")

    client_id = None
    if link_token:
        pending = PendingPlaidLink.query.filter_by(link_token=link_token).first()
        if pending:
            client_id = pending.client_id
            db.session.delete(pending)
            db.session.commit()
            app.logger.info(f"exchange_public_token: Resolved client_id={client_id} from pending link_token.")

    if client_id is None:
        client_id = session.get('client_id')  # last resort
        app.logger.info(f"exchange_public_token: Resolved client_id={client_id} from session (last resort).")

    if not client_id:
        app.logger.error("exchange_public_token: Could not resolve client for this Link session.")
        return jsonify({'error': 'Could not resolve client for this Link session.'}), 400

    institution_name = body.get('institution_name')
    institution_id = body.get('institution_id')

    new_item, error, success_message = _exchange_public_token(public_token, institution_name, institution_id, client_id)
    if error:
        app.logger.error(f"exchange_public_token: Error during public token exchange: {error}")
        return jsonify(error), 500
    if not new_item:
        app.logger.warning(f"exchange_public_token: Institution {institution_name} already linked or no new item created.")
        return jsonify({'error': f'This institution ({institution_name}) is already linked.'}), 409
    
    flash(success_message, 'success')
    app.logger.info(f"exchange_public_token: Successfully exchanged public token for client_id={client_id}. Redirecting to /plaid.")
    return jsonify({'status': 'success', 'redirect_url': url_for('plaid_page')})

@app.route('/api/plaid_webhook', methods=['POST'])
def plaid_webhook():
    is_valid, error_response = verify_plaid_webhook(request)
    if not is_valid:
        return jsonify({'error': error_response[0]}), error_response[1]

    data = request.get_json()
    app.logger.info(f"Received Plaid webhook: {data}")
    webhook_code = data.get('webhook_code')
    link_token = data.get('link_token')

    logging.info(f"Received Plaid webhook: {data.get('webhook_type')} - {webhook_code}")

    if webhook_code == 'SESSION_FINISHED':
        pending_link = PendingPlaidLink.query.filter_by(link_token=link_token).first()

        if not pending_link:
            logging.warning(f"Webhook for link_token '{link_token}' received, but no pending client found.")
            return jsonify({'status': 'ignored', 'reason': 'client_not_found'})

        client_id = pending_link.client_id

        if data.get('status', '').upper() == 'SUCCESS':
            public_token = data.get('public_tokens')[0] # Assuming one for now
            
            try:
                # For Hosted Link, we must call /link/token/get to fetch the institution details.
                link_get_request = plaid.model.link_token_get_request.LinkTokenGetRequest(link_token=link_token)
                link_get_response = plaid_client.link_token_get(link_get_request)

                institution_id = None
                institution_name = None

                if link_get_response and 'link_sessions' in link_get_response and link_get_response['link_sessions']:
                    first_session = link_get_response['link_sessions'][0]
                    if 'results' in first_session and 'item_add_results' in first_session['results'] and first_session['results']['item_add_results']:
                        first_item_add_result = first_session['results']['item_add_results'][0]
                        if 'institution' in first_item_add_result:
                            institution_id = first_item_add_result['institution'].get('institution_id')
                            institution_name = first_item_add_result['institution'].get('name')

                if not institution_id or not institution_name:
                    logging.error(f"Could not find institution details in /link/token/get response for {link_token}")
                    return jsonify({'status': 'error', 'reason': 'institution_details_missing_from_api'}), 500

                _exchange_public_token(public_token, institution_name, institution_id, client_id)
                logging.info(f"Successfully processed SESSION_FINISHED webhook for client {client_id}")
                db.session.delete(pending_link)
                db.session.commit()
                return jsonify({'status': 'success'})

            except plaid.exceptions.ApiException as e:
                logging.error(f"Plaid API error during /link/token/get: {e}")
                return jsonify({'status': 'error', 'reason': 'plaid_api_error'}), 500
        else:
            logging.info(f"Webhook for link_token '{link_token}' was not successful (status: {data.get('status')}).")
            db.session.delete(pending_link)
            db.session.commit()
            return jsonify({'status': 'ignored', 'reason': 'not_success'})

    return jsonify({'status': 'received'})

@app.route('/api/transactions/sync', methods=['POST'])
def sync_transactions():
    plaid_account_id = request.json['plaid_account_id']
    app.logger.info(f"Syncing transactions for plaid_account_id: {plaid_account_id}")
    plaid_account = PlaidAccount.query.get_or_404(plaid_account_id)
    item = plaid_account.plaid_item
    if item.client_id != session['client_id']:
        return "Unauthorized", 403

    added_count = 0
    
    try:
        cursor = item.cursor
        sync_request = TransactionsSyncRequest(
            access_token=item.access_token,
        )
        if cursor:
            sync_request.cursor = cursor

        response = plaid_client.transactions_sync(sync_request)
        
        added = response['added']

        # Filter transactions to only include those for the requested account
        added_for_account = [t for t in added if t['account_id'] == plaid_account.account_id]
        added_count = len(added_for_account)

        for t in added_for_account:
            new_transaction = Transaction(
                date=t['date'],
                description=t['name'],
                amount=-t['amount'], # Plaid returns positive for debits, negative for credits
                category=t['category'][0] if t['category'] else None,
                client_id=session['client_id'],
                is_approved=False,
                source_account_id=plaid_account.local_account_id
            )
            db.session.add(new_transaction)

        item.cursor = response['next_cursor']
        item.last_synced = datetime.now()
        db.session.commit()

    except Exception as e:
        try:
            error_body = json.loads(e.body)
            if 'error_code' in error_body and error_body['error_code'] == 'NO_ACCOUNTS':
                app.logger.info("No accounts found for this item during transaction sync.")
                return jsonify({'status': 'no_accounts'})
        except:
            pass # Not a Plaid error with a JSON body

        app.logger.error(f"Error syncing transactions: {e}")
        return jsonify({'error': 'An error occurred while syncing transactions.'}), 500

    return jsonify({'status': 'success', 'added': added_count})

@app.route('/api/plaid/set_account', methods=['POST'])
def set_plaid_account():
    plaid_account_id = request.json['plaid_account_id']
    account_id = request.json['account_id']
    plaid_account = PlaidAccount.query.get_or_404(plaid_account_id)
    if plaid_account.plaid_item.client_id != session['client_id']:
        return "Unauthorized", 403
    
    plaid_account.local_account_id = account_id
    db.session.commit()
    return jsonify({'status': 'success'})

def update_balances(plaid_item):
    try:
        balance_request = AccountsBalanceGetRequest(access_token=plaid_item.access_token)
        accounts_response = plaid_client.accounts_balance_get(balance_request)
        balances = accounts_response['accounts']

        for balance_info in balances:
            plaid_account = PlaidAccount.query.filter_by(account_id=balance_info['account_id']).first()
            if plaid_account and plaid_account.local_account:
                plaid_account.local_account.current_balance = balance_info['balances']['current']
                plaid_account.local_account.balance_last_updated = datetime.utcnow()
        
        db.session.commit()
        return True
    except Exception as e:
        app.logger.error(f"Error updating balances: {e}")
        return False

@app.route('/api/plaid/refresh_balances', methods=['POST'])
def refresh_balances():
    plaid_item_id = request.json['plaid_item_id']
    item = PlaidItem.query.get_or_404(plaid_item_id)
    if item.client_id != session['client_id']:
        return "Unauthorized", 403

    if update_balances(item):
        return jsonify({'status': 'success'})
    else:
        return jsonify({'error': 'Failed to update balances'}), 500

def sync_plaid_accounts(plaid_item_id=None):
    with app.app_context():
        app.logger.info(f'Syncing accounts for plaid_item_id: {plaid_item_id}')
        if plaid_item_id:
            plaid_items = [PlaidItem.query.get(plaid_item_id)]
        else:
            plaid_items = PlaidItem.query.filter_by(client_id=session['client_id']).all()
        
        for item in plaid_items:
            if not item: # Handle case where plaid_item_id might not exist
                continue

            try:
                accounts_request = AccountsGetRequest(access_token=item.access_token)
                accounts_response = plaid_client.accounts_get(accounts_request)
                accounts = accounts_response['accounts']
                app.logger.info(f'Found {len(accounts)} accounts for item {item.id}')
<<<<<<< HEAD

                for account in accounts:
                    # Check if the account already exists
                    if not PlaidAccount.query.filter_by(account_id=account['account_id']).first():
=======
                
                valid_plaid_account_ids = {acc['account_id'] for acc in accounts}
                local_plaid_accounts = PlaidAccount.query.filter_by(plaid_item_id=item.id).all()
                local_plaid_account_ids = {acc.account_id for acc in local_plaid_accounts}

                added_count = 0
                for account in accounts:
                    # Check if the account already exists
                    if account['account_id'] not in local_plaid_account_ids:
>>>>>>> feature/plaid-integration-chase
                        app.logger.info(f'Adding account {account["account_id"]} to the database')
                        new_plaid_account = PlaidAccount(
                            plaid_item_id=item.id,
                            account_id=account['account_id'],
                            name=account['name'],
                            mask=account['mask'],
<<<<<<< HEAD
                            type=str(account['type']),
                            subtype=str(account['subtype'])
                        )
                        db.session.add(new_plaid_account)
                db.session.commit()
=======
                            type=account['type'].value,
                            subtype=account['subtype'].value
                        )
                        db.session.add(new_plaid_account)
                        added_count += 1
                
                deleted_count = 0
                # Delete old accounts
                for local_acc in local_plaid_accounts:
                    if local_acc.account_id not in valid_plaid_account_ids:
                        db.session.delete(local_acc)
                        deleted_count += 1

                db.session.commit()
                app.logger.info(f"Sync complete for item {item.id}. Added: {added_count}, Deleted: {deleted_count}")

>>>>>>> feature/plaid-integration-chase
            except plaid.exceptions.ApiException as e:
                app.logger.error(f"Error syncing accounts for item {item.id}: {e}")

@app.route('/api/plaid/fetch_transactions', methods=['POST'])
def fetch_transactions():
    plaid_item_id = request.json.get('plaid_item_id')
    plaid_account_id = request.json.get('plaid_account_id')
    start_date_str = request.json['start_date']
    end_date_str = request.json['end_date']

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    item = None
    target_account_ids = None

    if plaid_item_id:
        item = PlaidItem.query.get_or_404(plaid_item_id)
        plaid_accounts = PlaidAccount.query.filter(PlaidAccount.plaid_item_id == item.id).all()
        target_account_ids = [pa.account_id.strip() for pa in plaid_accounts]
    elif plaid_account_id:
        plaid_account = PlaidAccount.query.get_or_404(plaid_account_id)
        item = plaid_account.plaid_item
        target_account_ids = [plaid_account.account_id.strip()]
    else:
        return jsonify({'error': 'Either plaid_item_id or plaid_account_id must be provided'}), 400

    if item.client_id != session['client_id']:
        return "Unauthorized", 403

    try:
        transactions_get_request = TransactionsGetRequest(
            access_token=item.access_token,
            start_date=start_date,
            end_date=end_date,
        )
        response = plaid_client.transactions_get(transactions_get_request)
        all_transactions = response['transactions']
        
        transactions = []
        if target_account_ids is not None:
            transactions = [t for t in all_transactions if t['account_id'].strip() in target_account_ids]
        else:
            transactions = all_transactions

        account_id_map = {pa.account_id: pa.local_account_id for pa in PlaidAccount.query.filter(PlaidAccount.plaid_item_id == item.id).all()}

        added_count = 0
        for t in transactions:
            if not Transaction.query.filter_by(plaid_transaction_id=t['transaction_id']).first():
                source_account_id = account_id_map.get(t['account_id'])
                new_transaction = Transaction(
                    plaid_transaction_id=t['transaction_id'],
                    date=t['date'],
                    description=t['name'],
                    amount=-t['amount'],
                    category=t['category'][0] if t['category'] else None,
                    client_id=session['client_id'],
                    is_approved=False,
                    source_account_id=source_account_id
                )
                db.session.add(new_transaction)
                added_count += 1
        
        db.session.commit()
    except Exception as e:
        return jsonify({'error': 'An error occurred while fetching transactions.'}), 500

@app.route('/api/plaid/delete_item', methods=['POST'])
def delete_plaid_item():
    plaid_item_id = request.json['plaid_item_id']
    item = PlaidItem.query.get_or_404(plaid_item_id)
    if item.client_id != session['client_id']:
        return "Unauthorized", 403

    try:
        # Remove the item from Plaid
        remove_request = ItemRemoveRequest(access_token=item.access_token)
        plaid_client.item_remove(remove_request)

        # Remove the item from the database
        db.session.delete(item)
        db.session.commit()

        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': 'An error occurred while deleting the item.'}), 500

@app.route('/api/plaid/delete_account', methods=['POST'])
def delete_plaid_account():
    plaid_account_id = request.json['plaid_account_id']
    account = PlaidAccount.query.get_or_404(plaid_account_id)
    if account.plaid_item.client_id != session['client_id']:
        return "Unauthorized", 403

    try:
        db.session.delete(account)
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': 'An error occurred while deleting the account.'}), 500
@app.route('/api/plaid/delete_institution', methods=['POST'])
def delete_institution():
    plaid_item_id = request.json['plaid_item_id']
    item = PlaidItem.query.get_or_404(plaid_item_id)
    if item.client_id != session['client_id']:
        return "Unauthorized", 403

    try:
        # Remove the item from Plaid
        remove_request = ItemRemoveRequest(access_token=item.access_token)
        plaid_client.item_remove(remove_request)

        # Remove the item from the database
        db.session.delete(item)
        db.session.commit()

        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': 'An error occurred while deleting the institution.'}), 500

@app.route('/api/plaid/debug_link_token', methods=['POST'])
def debug_link_token():
    link_token = request.json['link_token']
    try:
        response = plaid_client.link_token_get(LinkTokenGetRequest(link_token=link_token))
        return jsonify(response.to_dict())
    except plaid.exceptions.ApiException as e:
        return jsonify(json.loads(e.body)), 500
    except Exception as e:
        app.logger.error(f"Unexpected error in debug_link_token: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/plaid/delete_institution', methods=['POST'])
def delete_institution():
    institution_id = request.json['institution_id']
    item = PlaidItem.query.get_or_404(institution_id)
    if item.client_id != session['client_id']:
        return "Unauthorized", 403

    try:
        # Remove the item from Plaid
        remove_request = ItemRemoveRequest(access_token=item.access_token)
        plaid_client.item_remove(remove_request)

        # Remove the item from the database
        db.session.delete(item)
        db.session.commit()

        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)})

def json_serial_for_cli(obj):
    """JSON serializer for objects not serializable by default json code"""
    from datetime import date, datetime
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError ("Type %s not serializable" % type(obj))

@click.group()
def inspect_plaid():
    """Commands to inspect Plaid API responses."""
    pass

@inspect_plaid.command()
@click.argument('item_id', type=int)
@with_appcontext
def accounts(item_id):
    """Fetches and saves the /accounts/get response for a given PlaidItem ID."""
    item = PlaidItem.query.get_or_404(item_id)
    try:
        accounts_request = AccountsGetRequest(access_token=item.access_token)
        accounts_response = plaid_client.accounts_get(accounts_request)
        
        with open('plaid_accounts_response.txt', 'w') as f:
            f.write(json.dumps(accounts_response.to_dict(), indent=4, default=json_serial_for_cli))
            
        print("Successfully saved /accounts/get response to plaid_accounts_response.txt")
    except Exception as e:
        print(f"An error occurred: {e}")

@inspect_plaid.command()
@click.argument('item_id', type=int)
@with_appcontext
def balance(item_id):
    """Fetches and saves the /accounts/balance/get response for a given PlaidItem ID."""
    item = PlaidItem.query.get_or_404(item_id)
    try:
        balance_request = AccountsBalanceGetRequest(access_token=item.access_token)
        balance_response = plaid_client.accounts_balance_get(balance_request)
        
        with open('plaid_balance_response.txt', 'w') as f:
            f.write(json.dumps(balance_response.to_dict(), indent=4, default=json_serial_for_cli))
            
        print("Successfully saved /accounts/balance/get response to plaid_balance_response.txt")
    except Exception as e:
        print(f"An error occurred: {e}")

@inspect_plaid.command()
@click.argument('item_id', type=int)
@click.argument('start_date_str')
@click.argument('end_date_str')
@with_appcontext
def transactions(item_id, start_date_str, end_date_str):
    """Fetches and saves the /transactions/get response for a given PlaidItem ID."""
    item = PlaidItem.query.get_or_404(item_id)
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    try:
        transactions_get_request = TransactionsGetRequest(
            access_token=item.access_token,
            start_date=start_date,
            end_date=end_date,
        )
        response = plaid_client.transactions_get(transactions_get_request)
        
        with open('plaid_transactions_response.txt', 'w') as f:
            f.write(json.dumps(response.to_dict(), indent=4, default=json_serial_for_cli))
            
        print("Successfully saved /transactions/get response to plaid_transactions_response.txt")
    except Exception as e:
        print(f"An error occurred: {e}")

app.cli.add_command(inspect_plaid)

@app.cli.command("export-data")
@with_appcontext
def export_data_command():
    """Exports key data to CSV files."""
    import csv
    import sqlalchemy as sa
    
    # Ensure export directory exists
    if not os.path.exists('data_export'):
        os.makedirs('data_export')

    models_to_export = [Client, Vendor, Account, Budget, TransactionRule, CategoryRule, FixedAsset, Product, Inventory, Sale, RecurringTransaction, PlaidItem, PlaidAccount, Transaction, JournalEntry]
    
    for model in models_to_export:
        # Use __tablename__ if available, otherwise use model name
        table_name = getattr(model, '__tablename__', model.__name__.lower())
        records = model.query.all()
        if not records:
            print(f"No records found for {table_name}. Skipping.")
            continue
            
        # Get column names from the model's mapper
        columns = [c.key for c in sa.inspect(model).mapper.column_attrs]
        
        with open(f'data_export/{table_name}.csv', 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(columns)
            for record in records:
                writer.writerow([getattr(record, c) for c in columns])
                
        print(f"Exported {len(records)} records from {table_name}.")

@app.cli.command("import-data")
@with_appcontext
def import_data_command():
    """Imports all data from the data_export.xlsx file."""
    import pandas as pd
    import numpy as np
    from datetime import datetime, date

    export_file = 'data_export/data_export.xlsx'
    if not os.path.exists(export_file):
        print(f"Error: Export file not found at {export_file}")
        return

    try:
        xls = pd.ExcelFile(export_file)
        id_maps = {sheet: {} for sheet in xls.sheet_names}

        # Define order and relationships
        # The order is crucial to satisfy foreign key constraints
        import_order = [
            ('client', Client, {}),
            ('role', Role, {}),
            ('user', User, {'client_id': 'client', 'role_id': 'role'}),
            ('account', Account, {'client_id': 'client', 'parent_id': 'account'}), # parent_id handled specially
            ('vendor', Vendor, {'client_id': 'client'}),
            ('product', Product, {'client_id': 'client'}),
            ('fixed_asset', FixedAsset, {'client_id': 'client'}),
            ('plaid_item', PlaidItem, {'client_id': 'client'}),
            ('plaid_account', PlaidAccount, {'plaid_item_id': 'plaid_item', 'local_account_id': 'account'}),
            ('transaction', Transaction, {'client_id': 'client', 'source_account_id': 'account'}),
            ('journal_entries', JournalEntry, {'client_id': 'client', 'debit_account_id': 'account', 'credit_account_id': 'account', 'transaction_id': 'transaction'}),
            ('reconciliation', Reconciliation, {'client_id': 'client', 'account_id': 'account'}),
            ('transaction_rule', TransactionRule, {'client_id': 'client', 'new_debit_account_id': 'account', 'new_credit_account_id': 'account', 'source_account_id': 'account'}),
            ('category_rule', CategoryRule, {'client_id': 'client', 'debit_account_id': 'account', 'credit_account_id': 'account'}),
            ('budget', Budget, {'client_id': 'client'}),
            ('inventory', Inventory, {'client_id': 'client', 'product_id': 'product'}),
            ('sale', Sale, {'client_id': 'client', 'product_id': 'product'}),
            ('recurring_transaction', RecurringTransaction, {'client_id': 'client', 'debit_account_id': 'account', 'credit_account_id': 'account'}),
            ('document', Document, {'client_id': 'client', 'journal_entry_id': 'journal_entries'}),
            ('import_template', ImportTemplate, {'client_id': 'client', 'account_id': 'account'}),
            ('depreciation', Depreciation, {'client_id': 'client', 'fixed_asset_id': 'fixed_asset'}),
            ('financial_period', FinancialPeriod, {'client_id': 'client'}),
            ('audit_trail', AuditTrail, {'user_id': 'client'}), # user_id in AuditTrail maps to client.id
        ]

        date_cols = {
            'journal_entries': ['date', 'reversal_date'],
            'transaction': ['date'],
            'budget': ['start_date'],
            'fixed_asset': ['purchase_date'],
            'sale': ['date'],
            'recurring_transaction': ['start_date', 'end_date'],
            'reconciliation': ['statement_date', 'created_at'],
            'plaid_item': ['last_synced'],
            'audit_trail': ['date'],
            'depreciation': ['date'],
            'financial_period': ['start_date', 'end_date'],
        }

        # First pass for models without complex self-referencing FKs
        for sheet_name, model_class, fk_mappings in import_order:
            if sheet_name not in xls.sheet_names:
                print(f"Skipping sheet '{sheet_name}': Not found in Excel file.")
                continue
            
            # Special handling for account parent_id in a second pass
            if sheet_name == 'account':
                continue 

            print(f"Importing {sheet_name}...")
            df = pd.read_excel(xls, sheet_name=sheet_name)

            # Convert date columns
            for col in date_cols.get(sheet_name, []):
                if col in df.columns:
                    # Convert to datetime, coercing errors, then to date. Handle NaT.
                    df[col] = pd.to_datetime(df[col], errors='coerce')
                    df[col] = df[col].apply(lambda x: x.date() if pd.notna(x) else None)
            
            # Handle boolean columns (pandas reads as bool, but SQLAlchemy expects 0/1 or True/False)
            for col in df.columns:
                if df[col].dtype == 'bool':
                    df[col] = df[col].astype(bool)

            for _, row in df.iterrows():
                old_id = row.get('id')
                data = {k: None if pd.isna(v) else v for k, v in row.to_dict().items()}
                data.pop('id', None) # Remove old primary key

                # --- Specific fix for 'vendor_id' ---
                data.pop('vendor_id', None) # Remove vendor_id if it exists in old data

                # Map foreign keys
                for fk_col, fk_table in fk_mappings.items():
                    if fk_col in data and data[fk_col] is not None:
                        # Ensure FK is int before lookup
                        original_fk_id = int(data[fk_col]) if pd.notna(data[fk_col]) else None
                        if original_fk_id is not None:
                            data[fk_col] = id_maps[fk_table].get(original_fk_id)
                        else:
                            data[fk_col] = None # Set to None if original FK was NaN or not found

                new_obj = model_class(**data)
                db.session.add(new_obj)
                db.session.flush() # Flush to get the new ID
                if old_id is not None:
                    id_maps[sheet_name][old_id] = new_obj.id
            db.session.commit()
            print(f"Imported {len(df)} {sheet_name}s.")

        # --- Special handling for Account (self-referencing parent_id) ---
        if 'account' in xls.sheet_names:
            print("Importing accounts and setting up parent relationships...")
            df = pd.read_excel(xls, sheet_name='account')
            new_accounts_temp_storage = {} # Store new account objects temporarily

            # First pass: create accounts, map IDs, store old parent_id
            for _, row in df.iterrows():
                old_id = row['id']
                data = {k: None if pd.isna(v) else v for k, v in row.to_dict().items()}
                data.pop('id', None)
                
                old_parent_id = data.pop('parent_id', None) # Temporarily store old parent_id
                
                if data.get('client_id'):
                    data['client_id'] = id_maps['client'].get(int(data['client_id']))
                
                new_account = Account(**data)
                db.session.add(new_account)
                db.session.flush()
                id_maps['account'][old_id] = new_account.id
                new_account.old_parent_id = old_parent_id # Store old parent_id on the object
                new_accounts_temp_storage[new_account.id] = new_account
            db.session.commit()

            # Second pass: update parent_id using new IDs
            for new_acc_id, new_acc_obj in new_accounts_temp_storage.items():
                if new_acc_obj.old_parent_id and pd.notna(new_acc_obj.old_parent_id):
                    new_parent_id = id_maps['account'].get(int(new_acc_obj.old_parent_id))
                    if new_parent_id:
                        new_acc_obj.parent_id = new_parent_id
            db.session.commit()
            print(f"Imported {len(df)} accounts and set up parent relationships.")

        print("\nData import complete.")

    except Exception as e:
        print(f"An error occurred during import: {e}")
        db.session.rollback()