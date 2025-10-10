from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.models import Client, JournalEntry, ImportTemplate, Account, Budget, TransactionRule, PlaidAccount, PlaidItem
from app.utils import log_audit

clients_bp = Blueprint('clients', __name__)

@clients_bp.route('/clients')
def clients():
    clients = Client.query.all()
    return render_template('clients.html', clients=clients)

@clients_bp.route('/client/<int:client_id>')
def client_detail(client_id):
    client = Client.query.get_or_404(client_id)
    return render_template('client_detail.html', client=client)

@clients_bp.route('/add_client', methods=['GET', 'POST'])
def add_client():
    if request.method == 'POST':
        if Client.query.filter_by(business_name=request.form['business_name']).first():
            flash(f'Client "{request.form["business_name"]}" already exists.', 'danger')
            return redirect(url_for('clients.clients'))
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
        log_audit(f'Created client: {new_client.business_name}')
        flash(f'Client "{new_client.business_name}" created successfully.', 'success')
        return redirect(url_for('clients.clients'))
    return render_template('add_client.html')

@clients_bp.route('/select_client/<int:client_id>')
def select_client(client_id):
    session['client_id'] = client_id
    return redirect(url_for('main.index'))

@clients_bp.route('/edit_client/<int:client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)
    if request.method == 'POST':
        if Client.query.filter(Client.business_name == request.form['business_name'], Client.id != client_id).first():
            flash(f'Client with business name "{request.form["business_name"]}" already exists.', 'danger')
            return redirect(url_for('clients.edit_client', client_id=client_id))
        
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
        return redirect(url_for('clients.clients'))
    else:
        return render_template('edit_client.html', client=client)

@clients_bp.route('/delete_client/<int:client_id>')
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    # Delete all data associated with the client first
    JournalEntry.query.filter_by(client_id=client_id).delete()
    ImportTemplate.query.filter_by(client_id=client_id).delete()
    Account.query.filter_by(client_id=client_id).delete()
    Budget.query.filter_by(client_id=client_id).delete()
    TransactionRule.query.filter_by(client_id=client_id).delete()
    PlaidAccount.query.filter_by(client_id=client_id).delete()
    PlaidItem.query.filter_by(client_id=client_id).delete()
    log_audit(f'Deleted client: {client.business_name}')
    db.session.delete(client)
    db.session.commit()
    flash('Client deleted successfully.', 'success')
    # Clear the session if the deleted client was the active one
    if session.get('client_id') == client_id:
        session.pop('client_id', None)
    return redirect(url_for('clients.clients'))
