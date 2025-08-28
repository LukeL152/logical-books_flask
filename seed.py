from app import app, db, Client, Account, JournalEntry, Rule, ImportTemplate

def seed_data():
    with app.app_context():
        # Clear existing data
        db.reflect()
        db.drop_all()
        db.create_all()

        # Create a client
        client = Client(name='Test Client')
        db.session.add(client)
        db.session.commit()

        # Create accounts
        cash = Account(name='Cash', type='Asset', opening_balance=10000, client_id=client.id)
        accounts_receivable = Account(name='Accounts Receivable', type='Accounts Receivable', opening_balance=0, client_id=client.id)
        office_supplies = Account(name='Office Supplies', type='Asset', opening_balance=500, client_id=client.id)
        accounts_payable = Account(name='Accounts Payable', type='Accounts Payable', opening_balance=0, client_id=client.id)
        common_stock = Account(name='Common Stock', type='Equity', opening_balance=10500, client_id=client.id)
        sales_revenue = Account(name='Sales Revenue', type='Revenue', opening_balance=0, client_id=client.id)
        rent_expense = Account(name='Rent Expense', type='Expense', opening_balance=0, client_id=client.id)

        db.session.add_all([cash, accounts_receivable, office_supplies, accounts_payable, common_stock, sales_revenue, rent_expense])
        db.session.commit()

        # Create journal entries
        entry1 = JournalEntry(date='2025-01-05', description='Sale on credit', debit_account_id=accounts_receivable.id, credit_account_id=sales_revenue.id, amount=1500, client_id=client.id)
        entry2 = JournalEntry(date='2025-01-10', description='Cash sale', debit_account_id=cash.id, credit_account_id=sales_revenue.id, amount=500, client_id=client.id)
        entry3 = JournalEntry(date='2025-01-15', description='Paid rent', debit_account_id=rent_expense.id, credit_account_id=cash.id, amount=1000, client_id=client.id)

        db.session.add_all([entry1, entry2, entry3])
        db.session.commit()

        # Create a rule
        rule1 = Rule(name='Categorize all sales', keyword='sale', category='Sales', client_id=client.id)
        db.session.add(rule1)
        db.session.commit()

        # Create an import template
        template1 = ImportTemplate(account_id=cash.id, date_col=0, description_col=1, amount_col=2)
        db.session.add(template1)
        db.session.commit()

        print("Database seeded!")

if __name__ == '__main__':
    seed_data()
