from app import app, db, Transaction

with app.app_context():
    count = Transaction.query.filter_by(client_id=1).count()
    print(f"Transaction count for client_id=1: {count}")