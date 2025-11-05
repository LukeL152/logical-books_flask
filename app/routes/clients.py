from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from app import db
from app.models import Client, JournalEntries, ImportTemplate, Account, Budget, TransactionRule, PlaidAccount, PlaidItem
from sqlalchemy.exc import IntegrityError

clients_bp = Blueprint('clients', __name__)

@clients_bp.route('/clients')
def clients():
    clients = Client.query.order_by(Client.business_name).all()
    return render_template('clients.html', clients=clients)

@clients_bp.route('/add_client', methods=['GET', 'POST'])
def add_client():
    if request.method == 'POST':
        business_name = request.form['business_name']
        contact_name = request.form['contact_name']
        contact_email = request.form['contact_email']
        contact_phone = request.form['contact_phone']
        address = request.form['address']
        entity_structure = request.form['entity_structure']
        services_offered = request.form['services_offered']
        payment_method = request.form['payment_method']
        billing_cycle = request.form['billing_cycle']
        client_status = request.form['client_status']
        notes = request.form['notes']

        new_client = Client(
            business_name=business_name,
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone,
            address=address,
            entity_structure=entity_structure,
            services_offered=services_offered,
            payment_method=payment_method,
            billing_cycle=billing_cycle,
            client_status=client_status,
            notes=notes
        )
        db.session.add(new_client)
        db.session.commit()
        flash('Client added successfully!', 'success')
        return redirect(url_for('clients.clients'))
    return render_template('add_client.html')

@clients_bp.route('/edit_client/<int:client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)

    if request.method == 'POST':
        client.business_name = request.form['business_name']
        client.contact_name = request.form['contact_name']
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
        flash('Client updated successfully!', 'success')
        return redirect(url_for('clients.clients'))
    return render_template('edit_client.html', client=client)

@clients_bp.route('/delete_client/<int:client_id>', methods=['POST'])
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)

    try:
        # Find all Plaid items for the client
        plaid_items = PlaidItem.query.filter_by(client_id=client.id).all()
        for item in plaid_items:
            # Delete all Plaid accounts associated with each item
            PlaidAccount.query.filter_by(plaid_item_id=item.id).delete()
        
        # Now delete the Plaid items themselves
        PlaidItem.query.filter_by(client_id=client.id).delete()

        db.session.delete(client)
        db.session.commit()
        flash('Client deleted successfully!', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('Cannot delete client because there are still associated records (e.g., journal entries, transactions). Please delete those first.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred: {e}', 'danger')
    return redirect(url_for('clients.clients'))

@clients_bp.route('/client_detail/<int:client_id>')
def client_detail(client_id):
    client = Client.query.get_or_404(client_id)
    
    session['client_id'] = client.id
    session['client_name'] = client.business_name
    
    flash(f'Switched to client: {client.business_name}', 'info')
    return redirect(url_for('dashboard.dashboard'))