from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify
from app import db
from app.models import NotificationRule, Notification

notifications_bp = Blueprint('notifications', __name__)

@notifications_bp.route('/notification_rules', methods=['GET', 'POST'])
def notification_rules():
    if request.method == 'POST':
        name = request.form.get('name')
        criteria_type = request.form.get('criteria_type')
        criteria_value = request.form.get('criteria_value')
        notification_method = request.form.get('notification_method')

        if name and criteria_type and criteria_value and notification_method:
            rule = NotificationRule(
                name=name,
                criteria_type=criteria_type,
                criteria_value=float(criteria_value),
                notification_method=notification_method,
                client_id=session['client_id']
            )
            db.session.add(rule)
            db.session.commit()
            flash('Notification rule created successfully!', 'success')
            return redirect(url_for('notifications.notification_rules'))

    rules = NotificationRule.query.filter_by(client_id=session['client_id']).all()
    return render_template('notification_rules.html', rules=rules)

@notifications_bp.route('/notification_rules/delete/<int:rule_id>', methods=['POST'])
def delete_notification_rule(rule_id):
    rule = NotificationRule.query.get(rule_id)
    if rule and rule.client_id == session['client_id']:
        db.session.delete(rule)
        db.session.commit()
        flash('Notification rule deleted successfully!', 'success')
    else:
        flash('Failed to delete notification rule.', 'danger')
    return redirect(url_for('notifications.notification_rules'))

@notifications_bp.route('/delete/<int:notification_id>', methods=['DELETE'])
def delete_notification(notification_id):
    notification = Notification.query.get(notification_id)
    if notification:
        db.session.delete(notification)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404