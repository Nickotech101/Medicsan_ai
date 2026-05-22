import os
import pytest
import tempfile
from app import app as flask_app
from app import db, User, History, Favorite, Analytics

@pytest.fixture
def app():
    # Setup test configuration
    flask_app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test_secret_key"
    })
    
    # We can also mock the data paths if necessary, but it's easier to patch them in the tests.
    
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def init_database(app):
    with app.app_context():
        # Create tables
        db.create_all()
        
        # We can add a test user here if needed for global use, or do it in specific tests.
        
        yield db  # this is where the testing happens!
        
        db.session.remove()
        db.drop_all()
