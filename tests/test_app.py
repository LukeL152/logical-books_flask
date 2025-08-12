import pytest
from app import app, db, Client
from flask import get_flashed_messages

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.drop_all()

def test_create_client(client):
    """Test creating a new client."""
    response = client.post('/clients', data={'name': 'Test Client'})
    assert response.status_code == 302 # Should redirect

    with client.session_transaction() as sess:
        flashed_messages = sess['_flashes']
        assert ('success', 'Client "Test Client" created successfully.') in flashed_messages

    response = client.get(response.headers['Location'], follow_redirects=True)
    assert b'Test Client' in response.data

def test_create_duplicate_client(client):
    """Test that creating a duplicate client is prevented."""
    # Create the first client
    client.post('/clients', data={'name': 'Test Client'})

    # Try to create another client with the same name
    response = client.post('/clients', data={'name': 'Test Client'})
    assert response.status_code == 302 # Should redirect

    with client.session_transaction() as sess:
        flashed_messages = sess['_flashes']
        assert ('danger', 'Client "Test Client" already exists.') in flashed_messages

    response = client.get(response.headers['Location'], follow_redirects=True)
    assert b'Test Client' in response.data # Should still show the existing client

def test_dashboard_loads(client):
    """Test that the dashboard loads after selecting a client."""
    # Create a client first
    client.post('/clients', data={'name': 'Test Client'}, follow_redirects=True)
    # Get the client from the database to get its ID
    test_client = Client.query.filter_by(name='Test Client').first()
    # Select the client
    response = client.get(f'/select_client/{test_client.id}', follow_redirects=True)
    assert response.status_code == 200
    assert b'Dashboard' in response.data