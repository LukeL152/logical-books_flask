import pytest
from app import create_app, db
from app.models import Client, Account, JournalEntry, Transaction, Budget


@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False
    })

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_create_client(client):
    response = client.post('/add_client', data={
        'business_name': 'Test Client', 
        'contact_name': 'test', 
        'contact_email': 'test@test.com',
        'contact_phone': '1234567890',
        'address': '123 Main St',
        'entity_structure': 'Sole Proprietorship',
        'services_offered': 'Bookkeeping',
        'payment_method': 'Credit Card',
        'billing_cycle': 'Monthly',
        'client_status': 'Active',
        'notes': ''
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Test Client' in response.data

def test_create_duplicate_client(client):
    """Test that creating a duplicate client is prevented."""
    # Create the first client
    client.post('/add_client', data={
        'business_name': 'Test Client', 
        'contact_name': 'test', 
        'contact_email': 'test@test.com',
        'contact_phone': '1234567890',
        'address': '123 Main St',
        'entity_structure': 'Sole Proprietorship',
        'services_offered': 'Bookkeeping',
        'payment_method': 'Credit Card',
        'billing_cycle': 'Monthly',
        'client_status': 'Active',
        'notes': ''
    }, follow_redirects=True)

    # Try to create another client with the same name
    response = client.post('/add_client', data={
        'business_name': 'Test Client', 
        'contact_name': 'test', 
        'contact_email': 'test@test.com',
        'contact_phone': '1234567890',
        'address': '123 Main St',
        'entity_structure': 'Sole Proprietorship',
        'services_offered': 'Bookkeeping',
        'payment_method': 'Credit Card',
        'billing_cycle': 'Monthly',
        'client_status': 'Active',
        'notes': ''
    }, follow_redirects=True)
    assert b'already exists' in response.data

def test_dashboard_loads(client):
    """Test that the dashboard loads after selecting a client."""
    # Create a client first
    client.post('/add_client', data={
        'business_name': 'Test Client', 
        'contact_name': 'test', 
        'contact_email': 'test@test.com',
        'contact_phone': '1234567890',
        'address': '123 Main St',
        'entity_structure': 'Sole Proprietorship',
        'services_offered': 'Bookkeeping',
        'payment_method': 'Credit Card',
        'billing_cycle': 'Monthly',
        'client_status': 'Active',
        'notes': ''
    }, follow_redirects=True)
    # Get the client from the database to get its ID
    test_client = Client.query.filter_by(business_name='Test Client').first()
    # Select the client
    response = client.get(f'/select_client/{test_client.id}', follow_redirects=True)
    assert response.status_code == 200
    assert b'Dashboard' in response.data