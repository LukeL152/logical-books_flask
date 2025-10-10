from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.models import Vendor

vendors_bp = Blueprint('vendors', __name__)

@vendors_bp.route('/vendors')
def vendors():
    vendors = Vendor.query.filter_by(client_id=session['client_id']).order_by(Vendor.name).all()
    return render_template('vendors.html', vendors=vendors)

@vendors_bp.route('/add_vendor', methods=['GET', 'POST'])
def add_vendor():
    if request.method == 'POST':
        if Vendor.query.filter_by(name=request.form['name'], client_id=session['client_id']).first():
            flash(f'Vendor "{request.form["name"]}" already exists.', 'danger')
            return redirect(url_for('vendors.vendors'))
        new_vendor = Vendor(
            name=request.form['name'],
            contact_name=request.form['contact_name'],
            contact_email=request.form['contact_email'],
            contact_phone=request.form['contact_phone'],
            address=request.form['address'],
            notes=request.form['notes'],
            client_id=session['client_id']
        )
        db.session.add(new_vendor)
        db.session.commit()
        flash(f'Vendor "{new_vendor.name}" created successfully.', 'success')
        return redirect(url_for('vendors.vendors'))
    return render_template('add_vendor.html')

@vendors_bp.route('/edit_vendor/<int:vendor_id>', methods=['GET', 'POST'])
def edit_vendor(vendor_id):
    vendor = Vendor.query.get_or_404(vendor_id)
    if vendor.client_id != session['client_id']:
        return "Unauthorized", 403
    if request.method == 'POST':
        if Vendor.query.filter(Vendor.name == request.form['name'], Vendor.id != vendor_id, Vendor.client_id == session['client_id']).first():
            flash(f'Vendor with name "{request.form["name"]}" already exists.', 'danger')
            return redirect(url_for('vendors.edit_vendor', vendor_id=vendor_id))
        
        vendor.name = request.form['name']
        vendor.contact_name = request.form['contact_name']
        vendor.contact_email = request.form['contact_email']
        vendor.contact_phone = request.form['contact_phone']
        vendor.address = request.form['address']
        vendor.notes = request.form['notes']
        
        db.session.commit()
        flash('Vendor updated successfully.', 'success')
        return redirect(url_for('vendors.vendors'))
    else:
        return render_template('edit_vendor.html', vendor=vendor)

@vendors_bp.route('/delete_vendor/<int:vendor_id>')
def delete_vendor(vendor_id):
    vendor = Vendor.query.get_or_404(vendor_id)
    if vendor.client_id != session['client_id']:
        return "Unauthorized", 403
    db.session.delete(vendor)
    db.session.commit()
    flash('Vendor deleted successfully.', 'success')
    return redirect(url_for('vendors.vendors'))
