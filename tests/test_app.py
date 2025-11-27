import pytest
from app import create_app, db
from app.models import Client, Account, JournalEntries, Transaction, Budget, User, Role


@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test_secret'
    })

    with app.app_context():
        db.create_all()
        # Create a client for the user
        client = Client(business_name='Test Client for User', contact_name='Test User')
        db.session.add(client)
        db.session.commit()

        # Create a user and role for testing
        role = Role.query.filter_by(name='Admin').first()
        if not role:
            role = Role(name='Admin')
            db.session.add(role)
            db.session.commit()
        user = User(username='testuser', role_id=role.id, client_id=client.id)
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def authenticated_client(client):
    response = client.post('/login', data={'username': 'testuser', 'password': 'password'}, follow_redirects=True)
    assert response.status_code == 200
    yield client
    client.get('/logout', follow_redirects=True)


def test_create_client(authenticated_client):
    response = authenticated_client.post('/clients/add_client', data={
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

def test_create_duplicate_client(authenticated_client):
    """Test that creating a duplicate client is prevented."""
    # Create the first client
    authenticated_client.post('/clients/add_client', data={
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
    response = authenticated_client.post('/clients/add_client', data={
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
    assert b'A client with that business name already exists.' in response.data

def test_dashboard_loads(authenticated_client):
    """Test that the dashboard loads after selecting a client."""
    # Create a client first
    response = authenticated_client.post('/clients/add_client', data={
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
    # Get the client from the database to get its ID
    test_client = Client.query.filter_by(business_name='Test Client').first()
    # Select the client
    response = authenticated_client.get(f'/clients/client_detail/{test_client.id}', follow_redirects=True)
    assert response.status_code == 200
    assert b'Dashboard' in response.data