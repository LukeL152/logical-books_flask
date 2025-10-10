from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.models import FixedAsset, Depreciation, Account, JournalEntry
from app.utils import log_audit
from datetime import datetime

fixed_assets_bp = Blueprint('fixed_assets', __name__)

@fixed_assets_bp.route('/fixed_assets')
def fixed_assets():
    assets = FixedAsset.query.filter_by(client_id=session['client_id']).order_by(FixedAsset.purchase_date.desc()).all()
    return render_template('fixed_assets.html', assets=assets)

@fixed_assets_bp.route('/add_fixed_asset', methods=['GET', 'POST'])
def add_fixed_asset():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        purchase_date = datetime.strptime(request.form['purchase_date'], '%Y-%m-%d').date()
        cost = abs(float(request.form['cost']))
        useful_life = int(request.form['useful_life'])
        salvage_value = float(request.form['salvage_value'])

        new_asset = FixedAsset(
            name=name, 
            description=description, 
            purchase_date=purchase_date, 
            cost=cost, 
            useful_life=useful_life, 
            salvage_value=salvage_value, 
            client_id=session['client_id']
        )
        db.session.add(new_asset)
        db.session.commit()

        # Create a journal entry for the purchase of the fixed asset
        fixed_asset_account = Account.query.filter_by(type='Fixed Asset', client_id=session['client_id']).first()
        cash_account = Account.query.filter_by(type='Asset', name='Cash', client_id=session['client_id']).first()
        if fixed_asset_account and cash_account:
            new_entry = JournalEntry(
                date=purchase_date,
                description=f"Purchase of {name}",
                debit_account_id=fixed_asset_account.id,
                credit_account_id=cash_account.id,
                amount=cost,
                client_id=session['client_id']
            )
            db.session.add(new_entry)
            db.session.commit()

        flash('Fixed asset added successfully.', 'success')
        return redirect(url_for('fixed_assets.fixed_assets'))
    return render_template('add_fixed_asset.html')

@fixed_assets_bp.route('/delete_fixed_asset/<int:asset_id>')
def delete_fixed_asset(asset_id):
    asset = FixedAsset.query.get_or_404(asset_id)
    if asset.client_id != session.get('client_id'):
        flash('You do not have permission to delete this asset.', 'danger')
        return redirect(url_for('fixed_assets.fixed_assets'))

    # Delete journal entries associated with depreciation for this asset
    depreciation_entries = Depreciation.query.filter_by(fixed_asset_id=asset.id).all()
    for dep_entry in depreciation_entries:
        JournalEntry.query.filter_by(description=f"Depreciation for {asset.name}", date=dep_entry.date).delete()

    # Delete the journal entry for the purchase of the asset
    JournalEntry.query.filter_by(description=f"Purchase of {asset.name}", date=asset.purchase_date).delete()

    # Delete all depreciation entries for this asset
    Depreciation.query.filter_by(fixed_asset_id=asset.id).delete()

    db.session.delete(asset)
    db.session.commit()

    log_audit(f'Deleted fixed asset: {asset.name}')

    flash('Fixed asset and all associated entries deleted successfully.', 'success')
    return redirect(url_for('fixed_assets.fixed_assets'))

@fixed_assets_bp.route('/depreciation_schedule/<int:asset_id>')
def depreciation_schedule(asset_id):
    asset = FixedAsset.query.get_or_404(asset_id)
    if asset.client_id != session['client_id']:
        return "Unauthorized", 403

    depreciation_entries = Depreciation.query.filter_by(fixed_asset_id=asset.id).order_by(Depreciation.date).all()
    schedule = []
    accumulated_depreciation = 0
    book_value = asset.cost

    for entry in depreciation_entries:
        accumulated_depreciation += entry.amount
        book_value -= entry.amount
        schedule.append({
            'date': entry.date.strftime('%Y-%m-%d'),
            'amount': entry.amount,
            'accumulated_depreciation': accumulated_depreciation,
            'book_value': book_value
        })

    return render_template('depreciation_schedule.html', asset=asset, schedule=schedule)
