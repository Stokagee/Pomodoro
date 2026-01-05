"""
ML Service specific pytest fixtures.
Provides Flask app and test client with mocked MongoDB.
"""
import pytest
import sys
import os

# Get absolute path and add to sys.path for imports
ML_SERVICE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'ml-service')
ML_SERVICE_DIR = os.path.abspath(ML_SERVICE_DIR)

# Ensure ml-service directory is first in path for these tests
if ML_SERVICE_DIR not in sys.path:
    sys.path.insert(0, ML_SERVICE_DIR)


def _add_ml_to_path():
    """Helper to ensure ml-service directory is in path."""
    if ML_SERVICE_DIR not in sys.path:
        sys.path.insert(0, ML_SERVICE_DIR)
    # Remove web if present to avoid conflicts
    web_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'web'))
    if web_dir in sys.path:
        sys.path.remove(web_dir)


@pytest.fixture
def ml_app(mock_db, monkeypatch):
    """Create ML Flask app with mocked MongoDB."""
    _add_ml_to_path()

    # Patch before importing
    import app as ml_app_module

    monkeypatch.setattr(ml_app_module, 'db', mock_db)

    ml_app_module.app.config['TESTING'] = True

    return ml_app_module.app


@pytest.fixture
def ml_client(ml_app):
    """Create test client for ML service."""
    return ml_app.test_client()


@pytest.fixture
def analyzer(sample_sessions_data):
    """Create ProductivityAnalyzer with sample data (list of sessions)."""
    _add_ml_to_path()
    from models.productivity_analyzer import ProductivityAnalyzer
    return ProductivityAnalyzer(sample_sessions_data)


@pytest.fixture
def recommender(sample_sessions_data):
    """Create PresetRecommender with sample data (list of sessions)."""
    _add_ml_to_path()
    from models.preset_recommender import PresetRecommender
    return PresetRecommender(sample_sessions_data)


@pytest.fixture
def predictor(sample_sessions_data):
    """Create SessionPredictor with sample data (list of sessions)."""
    _add_ml_to_path()
    from models.session_predictor import SessionPredictor
    return SessionPredictor(sample_sessions_data)


@pytest.fixture
def empty_analyzer():
    """Create ProductivityAnalyzer with empty session list."""
    _add_ml_to_path()
    from models.productivity_analyzer import ProductivityAnalyzer
    return ProductivityAnalyzer([])


@pytest.fixture
def empty_recommender():
    """Create PresetRecommender with empty session list."""
    _add_ml_to_path()
    from models.preset_recommender import PresetRecommender
    return PresetRecommender([])


@pytest.fixture
def empty_predictor():
    """Create SessionPredictor with empty session list."""
    _add_ml_to_path()
    from models.session_predictor import SessionPredictor
    return SessionPredictor([])
