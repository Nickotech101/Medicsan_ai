import pytest

from app import app as flask_app
from app import db


@pytest.fixture
def app():
    # Setup test configuration
    flask_app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test_secret_key",
            # Disable Flask-Limiter so rate limits do not interfere with test counts.
            "RATELIMIT_ENABLED": False,
        }
    )

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


@pytest.fixture
def logged_in_client(client, init_database):
    """Return a test client that is already logged in as a test user."""
    client.post("/register", data={"username": "testuser", "password": "testpass123"})
    client.post("/login", data={"username": "testuser", "password": "testpass123"})
    return client
