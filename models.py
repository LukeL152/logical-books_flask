from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from database import db

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
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)


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
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    is_approved = db.Column(db.Boolean, nullable=False, default=False)

class AuditTrail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    action = db.Column(db.String(200), nullable=False)
    user = db.relationship('Client', backref='audit_trails')