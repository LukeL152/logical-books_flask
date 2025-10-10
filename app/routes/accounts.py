from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.models import Account
from app.utils import get_account_choices

accounts_bp = Blueprint('accounts', __name__)

@accounts_bp.route('/accounts')
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

@accounts_bp.route('/add_account', methods=['POST'])
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
        return redirect(url_for('accounts.accounts'))
    new_account = Account(name=name, type=account_type, category=category, opening_balance=opening_balance, parent_id=parent_id, client_id=session['client_id'])
    db.session.add(new_account)
    db.session.commit()
    flash(f'Account "{name}" created successfully.', 'success')
    return redirect(url_for('accounts.accounts'))

@accounts_bp.route('/edit_account/<int:account_id>', methods=['GET', 'POST'])
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
            return redirect(url_for('accounts.edit_account', account_id=account_id))

        # A more complex check would be needed to prevent circular dependencies
        # (e.g., setting parent to one of its own children), but this covers the direct case.

        if Account.query.filter(Account.name == name, Account.id != account_id, Account.client_id == session['client_id']).first():
            flash(f'Account "{name}" already exists.', 'danger')
            return redirect(url_for('accounts.edit_account', account_id=account_id))
        
        account.name = name
        account.type = request.form['type']
        account.category = request.form.get('category')
        account.opening_balance = float(request.form['opening_balance'])
        account.parent_id = parent_id
        db.session.commit()
        flash('Account updated successfully.', 'success')
        return redirect(url_for('accounts.accounts'))
    else:
        account_choices = get_account_choices(session['client_id'])
        return render_template('edit_account.html', account=account, account_choices=account_choices)

@accounts_bp.route('/delete_account/<int:account_id>')
def delete_account(account_id):
    account = Account.query.get_or_404(account_id)
    if account.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(account)
    db.session.commit()
    flash('Account deleted successfully.', 'success')
    return redirect(url_for('accounts.accounts'))

@accounts_bp.route('/reconcile_account/<int:account_id>')
def reconcile_account(account_id):
    # Placeholder for reconciliation logic
    account = Account.query.get_or_404(account_id)
    if account.client_id != session['client_id']:
        return "Unauthorized", 403
    return render_template('reconciliation.html', account=account)
