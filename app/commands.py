import click
from flask.cli import with_appcontext
import json
from datetime import datetime, date
from app.models import PlaidItem, Client, Vendor, Account, Budget, TransactionRule, FixedAsset, Product, Inventory, Sale, RecurringTransaction, PlaidAccount, Transaction, JournalEntries, Role, User, Document, ImportTemplate, Depreciation, FinancialPeriod, AuditTrail
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from app import db
from flask import current_app
import os
import pandas as pd
import numpy as np

def json_serial_for_cli(obj):
    """JSON serializer for objects not serializable by default json code"""
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
        accounts_response = current_app.plaid_client.accounts_get(accounts_request)
        
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
        balance_response = current_app.plaid_client.accounts_balance_get(balance_request)
        
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
        response = current_app.plaid_client.transactions_get(transactions_get_request)
        
        with open('plaid_transactions_response.txt', 'w') as f:
            f.write(json.dumps(response.to_dict(), indent=4, default=json_serial_for_cli))
            
        print("Successfully saved /transactions/get response to plaid_transactions_response.txt")
    except Exception as e:
        print(f"An error occurred: {e}")

@click.command("export-data")
@with_appcontext
def export_data_command():
    """Exports key data to CSV files."""
    import csv
    import sqlalchemy as sa
    
    # Ensure export directory exists
    if not os.path.exists('data_export'):
        os.makedirs('data_export')

    models_to_export = [Client, Vendor, Account, Budget, TransactionRule, FixedAsset, Product, Inventory, Sale, RecurringTransaction, PlaidItem, PlaidAccount, Transaction, JournalEntries]
    
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

@click.command('create-user')
@click.argument('username')
@click.argument('password')
@click.argument('client_id', type=int)
@with_appcontext
def create_user(username, password, client_id):
    """Creates a new user."""
    if User.query.filter_by(username=username).first():
        print(f'User "{username}" already exists.')
        return

    client = Client.query.get(client_id)
    if not client:
        print(f"Client with ID {client_id} does not exist.")
        return

    admin_role = Role.query.filter_by(name='Admin').first()
    if not admin_role:
        admin_role = Role(name='Admin')
        db.session.add(admin_role)
        db.session.commit()

    new_user = User(username=username, client_id=client_id, role_id=admin_role.id)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    print(f'User "{username}" created successfully for client {client.business_name}.')

@click.command("import-data")
@with_appcontext
def import_data_command():
    """Imports all data from the data_export.xlsx file."""
    
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
            ('journal_entries', JournalEntries, {'client_id': 'client', 'debit_account_id': 'account', 'credit_account_id': 'account', 'transaction_id': 'transaction'}),
            ('reconciliation', Reconciliation, {'client_id': 'client', 'account_id': 'account'}),
            ('transaction_rule', TransactionRule, {'client_id': 'client', 'new_debit_account_id': 'account', 'new_credit_account_id': 'account', 'source_account_id': 'account'}),
            
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