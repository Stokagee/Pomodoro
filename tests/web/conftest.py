"""
Web App specific pytest fixtures.
Provides Flask app and test client with mocked MongoDB.
"""
import pytest
import sys
import os
import json

# Get absolute path and add to sys.path for imports
WEB_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'web')
WEB_DIR = os.path.abspath(WEB_DIR)

# Ensure web directory is first in path for these tests
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)


def _add_web_to_path():
    """Helper to ensure web directory is in path."""
    if WEB_DIR not in sys.path:
        sys.path.insert(0, WEB_DIR)
    # Remove ml-service if present to avoid conflicts
    ml_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ml-service'))
    if ml_dir in sys.path:
        sys.path.remove(ml_dir)


@pytest.fixture
def web_config():
    """Load web app config."""
    config_path = os.path.join(WEB_DIR, 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def app(mock_db, monkeypatch):
    """Create Flask app with mocked MongoDB."""
    _add_web_to_path()

    # Patch the database module before importing app
    import models.database as db_module

    # Mock the MongoDB connection
    monkeypatch.setattr(db_module, 'db', mock_db)
    monkeypatch.setattr(db_module, 'client', mock_db.client)

    # Import app after patching
    from app import app as flask_app

    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False

    return flask_app


@pytest.fixture
def client(app):
    """Create test client for HTTP requests."""
    return app.test_client()


@pytest.fixture
def app_context(app):
    """Create application context."""
    with app.app_context():
        yield


@pytest.fixture
def mock_ml_service_success(monkeypatch):
    """Mock successful ML service responses."""
    import responses

    responses.add(
        responses.GET,
        'http://ml-service:5001/api/recommendation',
        json={
            'current_time': '10:00',
            'recommended_preset': 'deep_work',
            'reason': 'Morning hours are best for deep work',
            'alternative': 'learning',
            'confidence': 0.75
        },
        status=200
    )

    responses.add(
        responses.GET,
        'http://ml-service:5001/api/prediction/today',
        json={
            'date': '2025-12-28',
            'predicted_sessions': 6,
            'predicted_productivity': 4.0,
            'confidence': 0.7
        },
        status=200
    )

    return responses


@pytest.fixture
def mock_ml_service_unavailable(monkeypatch):
    """Mock ML service unavailable."""
    import responses

    responses.add(
        responses.GET,
        'http://ml-service:5001/api/recommendation',
        json={'error': 'Service unavailable'},
        status=503
    )

    responses.add(
        responses.GET,
        'http://ml-service:5001/api/prediction/today',
        json={'error': 'Service unavailable'},
        status=503
    )

    return responses
