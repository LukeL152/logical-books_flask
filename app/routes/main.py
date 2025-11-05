from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from flask_login import login_required, current_user, login_user, logout_user
from app.models import Client, Notification, User
from flask import jsonify
from app import db

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
    with open('BOOKKEEPING_GUIDE.md', 'r') as f:
        content = f.read()
    return render_template('bookkeeping_guide.html', content=content)

@main_bp.route('/add-notification', methods=['GET', 'POST'])
def add_notification():
    if request.method == 'POST':
        message = request.form.get('message')
        if message:
            notification = Notification(message=message)
            db.session.add(notification)
            db.session.commit()
            flash('Notification added successfully!', 'success')
            return redirect(url_for('main.add_notification'))
    return render_template('add_notification.html')

@main_bp.route('/notifications/delete/<int:notification_id>', methods=['DELETE'])
def delete_notification(notification_id):
    notification = Notification.query.get(notification_id)
    if notification:
        db.session.delete(notification)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@main_bp.route('/notifications')
def notifications():
    notifications = Notification.query.filter_by(is_read=False).order_by(Notification.created_at.desc()).all()
    return jsonify([{'id': n.id, 'message': n.message, 'created_at': n.created_at} for n in notifications])
