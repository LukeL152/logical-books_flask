from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.models import Product, Inventory, Sale, Account, JournalEntry
from datetime import datetime

inventory_bp = Blueprint('inventory', __name__)

@inventory_bp.route('/products')
def products():
    products = Product.query.filter_by(client_id=session['client_id']).order_by(Product.name).all()
    return render_template('products.html', products=products)

@inventory_bp.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        cost = abs(float(request.form['cost']))

        new_product = Product(
            name=name, 
            description=description, 
            cost=cost, 
            client_id=session['client_id']
        )
        db.session.add(new_product)
        db.session.commit()

        # Add product to inventory with initial quantity of 0
        new_inventory_item = Inventory(
            quantity=0,
            product_id=new_product.id,
            client_id=session['client_id']
        )
        db.session.add(new_inventory_item)
        db.session.commit()

        flash('Product added successfully.', 'success')
        return redirect(url_for('inventory.products'))
    return render_template('add_product.html')

@inventory_bp.route('/inventory')
def inventory():
    inventory = Inventory.query.filter_by(client_id=session['client_id']).all()
    return render_template('inventory.html', inventory=inventory)

@inventory_bp.route('/sales')
def sales():
    sales = Sale.query.filter_by(client_id=session['client_id']).order_by(Sale.date.desc()).all()
    return render_template('sales.html', sales=sales)

@inventory_bp.route('/add_sale', methods=['GET', 'POST'])
def add_sale():
    products = Product.query.filter_by(client_id=session['client_id']).order_by(Product.name).all()
    if request.method == 'POST':
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        product_id = request.form['product_id']
        quantity = int(request.form['quantity'])
        price = float(request.form['price'])

        # Check if there is enough inventory
        inventory_item = Inventory.query.filter_by(product_id=product_id, client_id=session['client_id']).first()
        if not inventory_item or inventory_item.quantity < quantity:
            flash('Not enough inventory for this sale.', 'danger')
            return render_template('add_sale.html', products=products)

        # Create the sale
        new_sale = Sale(
            date=date,
            product_id=product_id,
            quantity=quantity,
            price=price,
            client_id=session['client_id']
        )
        db.session.add(new_sale)

        # Update inventory
        inventory_item.quantity -= quantity

        # Create journal entries for the sale
        cogs_account = Account.query.filter_by(category='COGS', client_id=session['client_id']).first()
        sales_revenue_account = Account.query.filter_by(type='Revenue', client_id=session['client_id']).first()
        inventory_account = Account.query.filter_by(type='Inventory', client_id=session['client_id']).first()
        cash_account = Account.query.filter_by(type='Asset', name='Cash', client_id=session['client_id']).first()

        if cogs_account and sales_revenue_account and inventory_account and cash_account:
            # 1. Record the sale
            db.session.add(JournalEntry(
                date=date,
                description=f"Sale of {quantity} {new_sale.product.name}",
                debit_account_id=cash_account.id,
                credit_account_id=sales_revenue_account.id,
                amount=abs(price * quantity),
                client_id=session['client_id']
            ))

            # 2. Record the cost of goods sold
            db.session.add(JournalEntry(
                date=date,
                description=f"COGS for sale of {quantity} {new_sale.product.name}",
                debit_account_id=cogs_account.id,
                credit_account_id=inventory_account.id,
                amount=abs(new_sale.product.cost * quantity),
                client_id=session['client_id']
            ))

        db.session.commit()
        flash('Sale recorded successfully.', 'success')
        return redirect(url_for('inventory.sales'))

    return render_template('add_sale.html', products=products)
