from flask import Blueprint, redirect, url_for, session, request, render_template, flash
from flask_login import login_user, logout_user, current_user
from app.models import User

main_bp = Blueprint('main', __name__)

@main_bp.before_request
def before_request():
    if 'client_id' not in session and request.endpoint not in ['clients.clients', 'clients.add_client', 'clients.select_client', 'clients.edit_client', 'clients.delete_client', 'plaid.plaid_webhook', 'plaid.debug_link_token', 'plaid.plaid_oauth_return']:
        return redirect(url_for('clients.clients'))

@main_bp.route('/')
def index():
    return redirect(url_for('dashboard.dashboard'))

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user is None or not user.check_password(request.form['password']):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('main.login'))
        login_user(user)
        session['client_id'] = user.client_id
        return redirect(url_for('main.index'))
    return render_template('login.html')

@main_bp.route('/logout')
def logout():
    logout_user()
    session.pop('client_id', None)
    return redirect(url_for('main.login'))

import markdown
import os

@main_bp.route('/bookkeeping_guide')
def bookkeeping_guide():
    with open(os.path.join(os.path.dirname(__file__), '..', '..', 'BOOKKEEPING_GUIDE.md'), 'r') as f:
        content = f.read()
    guide_content = markdown.markdown(content)
    return render_template('bookkeeping_guide.html', guide_content=guide_content)
