from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from markupsafe import Markup
from app import db
from app.models import TransactionRule, CategoryRule, Client, Account, Transaction
from app.utils import get_account_choices
from collections import OrderedDict

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/rules')
def rules():
    return redirect(url_for('settings.transaction_rules'))

@settings_bp.route('/transaction_rules')
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

@settings_bp.route('/get_categories_for_account/<int:account_id>')
def get_categories_for_account(account_id):
    categories = db.session.query(Transaction.category).filter_by(source_account_id=account_id, client_id=session['client_id']).distinct().all()
    return json.dumps([c[0] for c in categories if c[0]])

@settings_bp.route('/category_rules', methods=['GET', 'POST'])
def category_rules():
    if request.method == 'POST':
        keyword = request.form['keyword']
        category = request.form['category']
        new_rule = CategoryRule(keyword=keyword, category=category, client_id=session['client_id'])
        db.session.add(new_rule)
        db.session.commit()
        flash('Category rule created successfully.', 'success')
        return redirect(url_for('settings.category_rules'))
    else:
        rules = CategoryRule.query.filter_by(client_id=session['client_id']).all()
        account_choices = get_account_choices(session['client_id'])
        return render_template('category_rules.html', rules=rules, accounts=account_choices)

@settings_bp.route('/add_transaction_rule', methods=['GET', 'POST'])
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
        return redirect(url_for('settings.transaction_rules'))

@settings_bp.route('/add_category_rule', methods=['POST'])
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
        return redirect(url_for('settings.category_rules'))
    
    if not category:
        flash('A category rule must specify a category to set.', 'danger')
        return redirect(url_for('settings.category_rules'))

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
    return redirect(url_for('settings.category_rules'))

@settings_bp.route('/delete_transaction_rule/<int:rule_id>')
def delete_transaction_rule(rule_id):
    rule = TransactionRule.query.get_or_404(rule_id)
    if rule.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(rule)
    db.session.commit()
    flash('Transaction rule deleted successfully.', 'success')
    return redirect(url_for('settings.transaction_rules'))

@settings_bp.route('/delete_category_rule/<int:rule_id>')
def delete_category_rule(rule_id):
    rule = CategoryRule.query.get_or_404(rule_id)
    if rule.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(rule)
    db.session.commit()
    flash('Category rule deleted successfully.', 'success')
    return redirect(url_for('settings.category_rules'))

@settings_bp.route('/edit_transaction_rule/<int:rule_id>', methods=['GET', 'POST'])
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
        return redirect(url_for('settings.transaction_rules'))
    else:
        return render_template('edit_transaction_rule.html', rule=rule, categories=categories, accounts=accounts)

@settings_bp.route('/edit_category_rule/<int:rule_id>', methods=['GET', 'POST'])
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
            return redirect(url_for('settings.edit_category_rule', rule_id=rule_id))
        
        if not rule.category:
            flash('A category rule must specify a category to set.', 'danger')
            return redirect(url_for('settings.edit_category_rule', rule_id=rule_id))

        rule.value = float(value_str) if value_str else None

        db.session.commit()
        flash('Category rule updated successfully.', 'success')
        return redirect(url_for('settings.category_rules'))
    else:
        account_choices = get_account_choices(session['client_id'])
        return render_template('edit_category_rule.html', rule=rule, accounts=account_choices)
