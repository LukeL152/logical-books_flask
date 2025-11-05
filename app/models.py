from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from app import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'))
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))

    role = db.relationship('Role', backref='users')
    client = db.relationship('Client', backref='users', foreign_keys=[client_id])

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)

    def __repr__(self):
        return f'<Role {self.name}>'

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_name = db.Column(db.String(120), nullable=False)
    contact_name = db.Column(db.String(120))
    contact_email = db.Column(db.String(120))
    contact_phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    entity_structure = db.Column(db.String(50))
    services_offered = db.Column(db.String(200))
    payment_method = db.Column(db.String(50))
    billing_cycle = db.Column(db.String(50))
    client_status = db.Column(db.String(50))
    notes = db.Column(db.Text)

    def __repr__(self):
        return f'<Client {self.business_name}>'

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # e.g., Asset, Liability, Equity, Revenue, Expense
    opening_balance = db.Column(db.Float, default=0.0)
    current_balance = db.Column(db.Float, default=0.0)
    balance_last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(120)) # e.g., Cash, Bank, Accounts Receivable, etc.
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('account.id'))

    client = db.relationship('Client', backref='accounts')
    parent = db.relationship('Account', remote_side=[id], backref=db.backref('children', lazy='dynamic'))

    def __repr__(self):
        return f'<Account {self.name} ({self.type})>'

class JournalEntries(db.Model):
    __tablename__ = 'journal_entries'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    debit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    credit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(120))
    notes = db.Column(db.Text)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    locked = db.Column(db.Boolean, default=False) # For accruals, etc.
    is_accrual = db.Column(db.Boolean, default=False)
    is_reversing = db.Column(db.Boolean, default=False)
    reversal_date = db.Column(db.Date)
    status = db.Column(db.String(50), default='posted') # posted, void, pending
    transaction_type = db.Column(db.String(50)) # e.g., 'sale', 'expense', 'deposit'
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id'))

    debit_account = db.relationship('Account', foreign_keys=[debit_account_id], backref='debit_entries')
    credit_account = db.relationship('Account', foreign_keys=[credit_account_id], backref='credit_entries')
    client = db.relationship('Client', backref='journal_entries')
    transaction = db.relationship('Transaction', backref='journal_entries')

    def __repr__(self):
        return f'<JournalEntries {self.date} - {self.description}: {self.amount}>'

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'))
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    journal_entry = db.relationship('JournalEntries', backref='documents')
    client = db.relationship('Client', backref='documents')

    def __repr__(self):
        return f'<Document {self.filename}>'

class ImportTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    date_col = db.Column(db.Integer, nullable=False)
    description_col = db.Column(db.Integer, nullable=False)
    amount_col = db.Column(db.Integer)
    debit_col = db.Column(db.Integer)
    credit_col = db.Column(db.Integer)
    category_col = db.Column(db.Integer)
    notes_col = db.Column(db.Integer)
    has_header = db.Column(db.Boolean, default=True)
    negate_amount = db.Column(db.Boolean, default=False)

    client = db.relationship('Client', backref='import_templates')
    account = db.relationship('Account', backref='import_templates')

    def __repr__(self):
        return f'<ImportTemplate {self.name}>'

budget_keywords = db.Table('budget_keywords',
    db.Column('budget_id', db.Integer, db.ForeignKey('budget.id'), primary_key=True),
    db.Column('keyword_id', db.Integer, db.ForeignKey('keyword.id'), primary_key=True)
)

budget_categories = db.Table('budget_categories',
    db.Column('budget_id', db.Integer, db.ForeignKey('budget.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('category.id'), primary_key=True)
)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    def __repr__(self):
        return f'<Category {self.name}>'


class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    period = db.Column(db.String(50), nullable=False) # e.g., 'monthly', 'quarterly', 'yearly'
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('budget.id'))
    parent = db.relationship('Budget', remote_side=[id], backref=db.backref('children', lazy='dynamic'))
    keywords = db.relationship('Keyword', secondary=budget_keywords,
                               backref=db.backref('budgets', lazy='dynamic'),
                               cascade="all, delete")
    categories = db.relationship('Category', secondary=budget_categories,
                                 backref=db.backref('budgets', lazy='dynamic'))

    def __repr__(self):
        return f'<Budget {self.name} for {self.amount}>'

    def get_all_descendants(self):
        descendants = []
        for child in self.children:
            descendants.append(child)
            descendants.extend(child.get_all_descendants())
        return descendants

    @property
    def total_budgeted(self):
        total = self.amount
        for child in self.children:
            total += child.total_budgeted
        return total

    def get_spending_breakdown(self, start_date, end_date):
        all_categories = [c.name for c in self.categories]
        
        spending_breakdown_query = db.session.query(
            JournalEntries.category,
            func.sum(JournalEntries.amount).label('total')
        ).filter(
            JournalEntries.client_id == self.client_id,
            JournalEntries.date >= start_date,
            JournalEntries.date <= end_date,
            JournalEntries.category.in_(all_categories)
        ).group_by(JournalEntries.category).order_by(func.sum(JournalEntries.amount).desc())

        return spending_breakdown_query.all()

    def get_historical_performance(self, start_date, end_date):
        from app.utils import get_budgets_actual_spent

        periods = []
        current_date = start_date
        while current_date <= end_date:
            if self.period == 'monthly':
                period_start = current_date.replace(day=1)
                period_end = (period_start + relativedelta(months=1)) - timedelta(days=1)
                period_name = period_start.strftime('%B %Y')
                current_date = period_end + timedelta(days=1)
            elif self.period == 'quarterly':
                current_quarter_start_month = (current_date.month - 1) // 3 * 3 + 1
                period_start = current_date.replace(month=current_quarter_start_month, day=1)
                period_end = (period_start + relativedelta(months=3)) - timedelta(days=1)
                period_name = f"Q{(current_quarter_start_month - 1) // 3 + 1} {current_date.year}"
                current_date = period_end + timedelta(days=1)
            else: # yearly
                period_start = current_date.replace(month=1, day=1)
                period_end = (period_start + relativedelta(years=1)) - timedelta(days=1)
                period_name = str(current_date.year)
                current_date = period_end + timedelta(days=1)

            effective_start = max(period_start, start_date)
            effective_end = min(period_end, end_date)

            actual_spendings = get_budgets_actual_spent([self.id], effective_start, effective_end)
            actual_spent = actual_spendings.get(self.id, 0.0)

            periods.append({
                'period_name': period_name,
                'budgeted': self.amount,
                'actual': actual_spent
            })
        
        return periods

class Keyword(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    def __repr__(self):
        return f'<Keyword {self.name}>'

class FinancialPeriod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    client = db.relationship('Client', backref='financial_periods')

    def __repr__(self):
        return f'<FinancialPeriod {self.name}>'

class FixedAsset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    purchase_date = db.Column(db.Date, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    salvage_value = db.Column(db.Float, nullable=False)
    useful_life = db.Column(db.Integer, nullable=False) # in years
    depreciation_method = db.Column(db.String(50), nullable=False) # e.g., 'straight-line'
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    client = db.relationship('Client', backref='fixed_assets')

    def __repr__(self):
        return f'<FixedAsset {self.name}>'

class Depreciation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fixed_asset_id = db.Column(db.Integer, db.ForeignKey('fixed_asset.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    fixed_asset = db.relationship('FixedAsset', backref='depreciations')
    client = db.relationship('Client', backref='depreciations')

    def __repr__(self):
        return f'<Depreciation {self.amount} on {self.date}>'

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    purchase_price = db.Column(db.Float, nullable=False)
    sale_price = db.Column(db.Float, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    client = db.relationship('Client', backref='products')

    def __repr__(self):
        return f'<Product {self.name}>'

class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    purchase_date = db.Column(db.Date, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    product = db.relationship('Product', backref='inventory_records')
    client = db.relationship('Client', backref='inventory_records')

    def __repr__(self):
        return f'<Inventory {self.product.name} - {self.quantity}>'

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    sale_price = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    product = db.relationship('Product', backref='sales')
    client = db.relationship('Client', backref='sales')

    def __repr__(self):
        return f'<Sale {self.product.name} - {self.quantity}>'

class RecurringTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(255), nullable=False)
    debit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    credit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    frequency = db.Column(db.String(50), nullable=False) # e.g., 'monthly', 'quarterly', 'yearly'
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    debit_account = db.relationship('Account', foreign_keys=[debit_account_id], backref='recurring_debit_transactions')
    credit_account = db.relationship('Account', foreign_keys=[credit_account_id], backref='recurring_credit_transactions')
    client = db.relationship('Client', backref='recurring_transactions')

    def __repr__(self):
        return f'<RecurringTransaction {self.description} - {self.amount}>'

class PlaidItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    item_id = db.Column(db.String(255), unique=True, nullable=False)
    access_token = db.Column(db.String(255), nullable=False)
    institution_id = db.Column(db.String(255), nullable=False)
    institution_name = db.Column(db.String(255), nullable=False)
    last_synced = db.Column(db.DateTime, default=datetime.utcnow)
    cursor = db.Column(db.String(255)) # For Plaid Transactions Sync

    client = db.relationship('Client', backref='plaid_items')

    def __repr__(self):
        return f'<PlaidItem {self.institution_name}>'

class PlaidAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plaid_item_id = db.Column(db.Integer, db.ForeignKey('plaid_item.id'), nullable=False)
    account_id = db.Column(db.String(255), nullable=False) # Plaid's account ID
    name = db.Column(db.String(255), nullable=False)
    mask = db.Column(db.String(10))
    type = db.Column(db.String(50))
    subtype = db.Column(db.String(50))
    local_account_id = db.Column(db.Integer, db.ForeignKey('account.id')) # Link to local Account model

    plaid_item = db.relationship('PlaidItem', backref='plaid_accounts')
    local_account = db.relationship('Account', backref='plaid_account_link')

    def __repr__(self):
        return f'<PlaidAccount {self.name} ({self.mask})>'

class PendingPlaidLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    link_token = db.Column(db.String(255), unique=True, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    purpose = db.Column(db.String(50), nullable=False) # 'standard' or 'hosted'

    client = db.relationship('Client', backref='pending_plaid_links')

    def __repr__(self):
        return f'<PendingPlaidLink {self.link_token}>'

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plaid_transaction_id = db.Column(db.String(255), unique=True) # Plaid's transaction ID
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(120))
    notes = db.Column(db.Text)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    is_approved = db.Column(db.Boolean, default=False)
    debit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    credit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    rule_modified = db.Column(db.Boolean, default=False)
    source_account_id = db.Column(db.Integer, db.ForeignKey('account.id')) # The account from which the transaction originated (e.g., bank account)

    client = db.relationship('Client', backref='transactions')
    debit_account = db.relationship('Account', foreign_keys=[debit_account_id], backref='transaction_debits')
    credit_account = db.relationship('Account', foreign_keys=[credit_account_id], backref='transaction_credits')
    source_account = db.relationship('Account', foreign_keys=[source_account_id], backref='source_transactions')

    def __repr__(self):
        return f'<Transaction {self.date} - {self.description}: {self.amount}>'

class AuditTrail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'))
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)

    user = db.relationship('User', backref='audit_trails')
    client = db.relationship('Client', backref='audit_trails')

    def __repr__(self):
        return f'<AuditTrail {self.date} - {self.action}>'

class TransactionRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    keyword = db.Column(db.String(255), nullable=False)
    new_category = db.Column(db.String(120))
    new_debit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    new_credit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    source_account_id = db.Column(db.Integer, db.ForeignKey('account.id')) # Optional: apply rule only to transactions from this account

    client = db.relationship('Client', backref='transaction_rules')
    new_debit_account = db.relationship('Account', foreign_keys=[new_debit_account_id], backref='rule_debits')
    new_credit_account = db.relationship('Account', foreign_keys=[new_credit_account_id], backref='rule_credits')
    source_account = db.relationship('Account', foreign_keys=[source_account_id], backref='rule_source_accounts')

    def __repr__(self):
        return f'<TransactionRule {self.keyword} -> {self.new_category}>'

class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    contact_name = db.Column(db.String(120))
    contact_email = db.Column(db.String(120))
    contact_phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    notes = db.Column(db.Text)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    client = db.relationship('Client', backref='vendors')

    def __repr__(self):
        return f'<Vendor {self.name}>'

class Reconciliation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    statement_date = db.Column(db.Date, nullable=False)
    statement_balance = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_reconciled = db.Column(db.Boolean, default=False)

    client = db.relationship('Client', backref='reconciliations')
    account = db.relationship('Account', backref='reconciliations')

    def __repr__(self):
        return f'<Reconciliation {self.statement_date} - {self.statement_balance}>'

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='notifications')

    def __repr__(self):
        return f'<Notification {self.id}>'