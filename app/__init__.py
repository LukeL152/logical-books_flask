from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_apscheduler import APScheduler
from flask_login import LoginManager
import os
import plaid
from plaid.api import plaid_api
import logging
import json
from datetime import datetime, timedelta
from markupsafe import Markup
db = SQLAlchemy()
migrate = Migrate()
scheduler = APScheduler()

from app.models import (
    User, Role, Client, Account, JournalEntries, Document, ImportTemplate,
    Budget, FinancialPeriod, FixedAsset, Depreciation, Product, Inventory,
    Sale, RecurringTransaction, PlaidItem, PlaidAccount, PendingPlaidLink,
    Transaction, AuditTrail, TransactionRule, Vendor, Reconciliation,
    Notification
)

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, timedelta):
            return str(obj)
        return super().default(self, obj)

def create_app():
    app = Flask(__name__)

    from app.routes.main import main_bp
    from app.routes.accounts import accounts_bp
    from app.routes.clients import clients_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.fixed_assets import fixed_assets_bp
    from app.routes.inventory import inventory_bp
    from app.routes.journal import journal_bp
    from app.routes.plaid import plaid_bp
    from app.routes.reports import reports_bp
    from app.routes.settings import settings_bp
    from app.routes.transactions import transactions_bp
    from app.routes.vendors import vendors_bp
    from app.routes.notifications import notifications_bp
    from app.routes.guides import guides_bp

    app.config['SECRET_KEY'] = 'your_secret_key'  # Change this in a real application
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'bookkeeping.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Plaid client setup
    app.config['PLAID_CLIENT_ID'] = os.environ.get('PLAID_CLIENT_ID')
    app.config['PLAID_SECRET'] = os.environ.get('PLAID_SECRET')
    app.config['PLAID_ENV'] = os.environ.get('PLAID_ENV', 'sandbox')
    app.config['PLAID_PRODUCTS'] = os.environ.get('PLAID_PRODUCTS', 'transactions').split(',')
    app.config['PLAID_COUNTRY_CODES'] = os.environ.get('PLAID_COUNTRY_CODES', 'US').split(',')
    app.config['PLAID_WEBHOOK_URL'] = os.environ.get('PLAID_WEBHOOK_URL')

    if app.config['PLAID_ENV'] == 'sandbox':
        host = plaid.Environment.Sandbox
    elif app.config['PLAID_ENV'] == 'development':
        host = plaid.Environment.Development
    elif app.config['PLAID_ENV'] == 'production':
        host = plaid.Environment.Production
    else:
        raise ValueError("Invalid PLAID_ENV")

    configuration = plaid.Configuration(
        host=host,
        api_key={
            'clientId': app.config['PLAID_CLIENT_ID'],
            'secret': app.config['PLAID_SECRET'],
        }
    )

    api_client = plaid.ApiClient(configuration)
    app.plaid_client = plaid_api.PlaidApi(api_client)

    db.init_app(app)
    migrate.init_app(app, db)

    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return models.User.query.get(int(user_id))

    if not scheduler.running:
        from app import tasks
        scheduler.init_app(app)
        scheduler.start()
        scheduler.add_job(id='calculate_depreciation', func=tasks.calculate_and_record_depreciation, trigger='cron', day=1, hour=0)
        scheduler.add_job(id='reverse_accruals', func=tasks.reverse_accruals, trigger='cron', day=1, hour=0)
        scheduler.add_job(id='create_recurring_journal_entries', func=tasks.create_recurring_journal_entries, trigger='cron', day=1, hour=0)
        scheduler.add_job(id='cleanup_pending_plaid_links', func=tasks.cleanup_pending_plaid_links, trigger='cron', day='*', hour=2)
        scheduler.add_job(id='check_budgets', func=tasks.check_budgets, trigger='cron', day='*', hour=3)
        scheduler.add_job(id='check_notification_rules', func=tasks.check_notification_rules, trigger='cron', day='*', hour=4)

    app.json_encoder = CustomJSONEncoder

    @app.template_filter('tojson')
    def tojson_filter(obj):
        return json.dumps(obj)

    @app.template_filter('nl2br')
    def nl2br(s):
        return Markup(s.replace('\n', '<br>\n')) if s else ''

    app.register_blueprint(main_bp)
    app.register_blueprint(accounts_bp, url_prefix='/accounts')
    app.register_blueprint(clients_bp, url_prefix='/clients')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(fixed_assets_bp, url_prefix='/fixed_assets')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(journal_bp, url_prefix='/journal')
    app.register_blueprint(plaid_bp, url_prefix='/plaid')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(settings_bp, url_prefix='/settings')
    app.register_blueprint(transactions_bp, url_prefix='/transactions')
    app.register_blueprint(vendors_bp, url_prefix='/vendors')
    app.register_blueprint(notifications_bp, url_prefix='/notifications')
    app.register_blueprint(guides_bp)

    from app import commands
    app.cli.add_command(commands.inspect_plaid)
    app.cli.add_command(commands.export_data_command)
    app.cli.add_command(commands.import_data_command)
    app.cli.add_command(commands.create_user)

    with app.app_context():
        return app