"""
Shared pytest fixtures for Pomodoro Timer v2.0 tests.
Provides MongoDB mocking and sample test data.
"""
import pytest
import mongomock
import sys
import os
from datetime import datetime, timedelta

# Get absolute paths for web and ml-service directories
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, 'web')
ML_SERVICE_DIR = os.path.join(ROOT_DIR, 'ml-service')


@pytest.fixture
def mock_mongo_client():
    """Create mongomock client for isolated testing."""
    client = mongomock.MongoClient()
    yield client
    client.close()


@pytest.fixture
def mock_db(mock_mongo_client):
    """Get test database."""
    return mock_mongo_client['pomodoro_test']


@pytest.fixture
def empty_db(mock_db):
    """Ensure database is empty."""
    mock_db.sessions.delete_many({})
    mock_db.insights.delete_many({})
    mock_db.predictions.delete_many({})
    return mock_db


@pytest.fixture
def sample_sessions_data():
    """
    Sample session data covering various scenarios:
    - All days of week (Monday-Sunday)
    - Hours 6-20
    - All 4 presets
    - All rating values (1-5)
    - Multiple categories
    """
    base_date = datetime(2025, 12, 22)  # Monday

    sessions = [
        # Monday (day_of_week=0) - High productivity morning
        {
            'date': '2025-12-22',
            'time': '09:00',
            'hour': 9,
            'day_of_week': 0,
            'preset': 'deep_work',
            'category': 'SOAP',
            'task': 'WSDL study',
            'duration_minutes': 52,
            'completed': True,
            'productivity_rating': 5,
            'notes': '',
            'created_at': base_date.replace(hour=9)
        },
        {
            'date': '2025-12-22',
            'time': '10:15',
            'hour': 10,
            'day_of_week': 0,
            'preset': 'deep_work',
            'category': 'SOAP',
            'task': 'XML parsing',
            'duration_minutes': 52,
            'completed': True,
            'productivity_rating': 4,
            'notes': '',
            'created_at': base_date.replace(hour=10)
        },
        {
            'date': '2025-12-22',
            'time': '14:00',
            'hour': 14,
            'day_of_week': 0,
            'preset': 'quick_tasks',
            'category': 'LinkedIn',
            'task': 'Network updates',
            'duration_minutes': 25,
            'completed': True,
            'productivity_rating': 3,
            'notes': '',
            'created_at': base_date.replace(hour=14)
        },

        # Tuesday (day_of_week=1)
        {
            'date': '2025-12-23',
            'time': '08:00',
            'hour': 8,
            'day_of_week': 1,
            'preset': 'learning',
            'category': 'Robot Framework',
            'task': 'Browser library',
            'duration_minutes': 45,
            'completed': True,
            'productivity_rating': 4,
            'notes': '',
            'created_at': (base_date + timedelta(days=1)).replace(hour=8)
        },
        {
            'date': '2025-12-23',
            'time': '09:00',
            'hour': 9,
            'day_of_week': 1,
            'preset': 'deep_work',
            'category': 'Robot Framework',
            'task': 'Test automation',
            'duration_minutes': 52,
            'completed': True,
            'productivity_rating': 5,
            'notes': '',
            'created_at': (base_date + timedelta(days=1)).replace(hour=9)
        },
        {
            'date': '2025-12-23',
            'time': '15:00',
            'hour': 15,
            'day_of_week': 1,
            'preset': 'quick_tasks',
            'category': 'Job Search',
            'task': 'CV updates',
            'duration_minutes': 25,
            'completed': True,
            'productivity_rating': 2,
            'notes': 'tired',
            'created_at': (base_date + timedelta(days=1)).replace(hour=15)
        },

        # Wednesday (day_of_week=2)
        {
            'date': '2025-12-24',
            'time': '10:00',
            'hour': 10,
            'day_of_week': 2,
            'preset': 'learning',
            'category': 'REST API',
            'task': 'Postman study',
            'duration_minutes': 45,
            'completed': True,
            'productivity_rating': 4,
            'notes': '',
            'created_at': (base_date + timedelta(days=2)).replace(hour=10)
        },
        {
            'date': '2025-12-24',
            'time': '11:00',
            'hour': 11,
            'day_of_week': 2,
            'preset': 'deep_work',
            'category': 'REST API',
            'task': 'API testing',
            'duration_minutes': 52,
            'completed': True,
            'productivity_rating': 4,
            'notes': '',
            'created_at': (base_date + timedelta(days=2)).replace(hour=11)
        },

        # Thursday (day_of_week=3)
        {
            'date': '2025-12-25',
            'time': '09:30',
            'hour': 9,
            'day_of_week': 3,
            'preset': 'flow_mode',
            'category': 'Database',
            'task': 'SQL practice',
            'duration_minutes': 90,
            'completed': True,
            'productivity_rating': 5,
            'notes': 'great focus',
            'created_at': (base_date + timedelta(days=3)).replace(hour=9)
        },
        {
            'date': '2025-12-25',
            'time': '14:00',
            'hour': 14,
            'day_of_week': 3,
            'preset': 'learning',
            'category': 'Frontend',
            'task': 'CSS study',
            'duration_minutes': 45,
            'completed': True,
            'productivity_rating': 3,
            'notes': '',
            'created_at': (base_date + timedelta(days=3)).replace(hour=14)
        },

        # Friday (day_of_week=4)
        {
            'date': '2025-12-26',
            'time': '08:30',
            'hour': 8,
            'day_of_week': 4,
            'preset': 'deep_work',
            'category': 'SOAP',
            'task': 'SOAP client',
            'duration_minutes': 52,
            'completed': True,
            'productivity_rating': 4,
            'notes': '',
            'created_at': (base_date + timedelta(days=4)).replace(hour=8)
        },
        {
            'date': '2025-12-26',
            'time': '10:00',
            'hour': 10,
            'day_of_week': 4,
            'preset': 'deep_work',
            'category': 'SOAP',
            'task': 'Error handling',
            'duration_minutes': 52,
            'completed': True,
            'productivity_rating': 5,
            'notes': '',
            'created_at': (base_date + timedelta(days=4)).replace(hour=10)
        },
        {
            'date': '2025-12-26',
            'time': '16:00',
            'hour': 16,
            'day_of_week': 4,
            'preset': 'quick_tasks',
            'category': 'LinkedIn',
            'task': 'Messages',
            'duration_minutes': 25,
            'completed': True,
            'productivity_rating': 2,
            'notes': 'distracted',
            'created_at': (base_date + timedelta(days=4)).replace(hour=16)
        },

        # Saturday (day_of_week=5)
        {
            'date': '2025-12-27',
            'time': '10:00',
            'hour': 10,
            'day_of_week': 5,
            'preset': 'learning',
            'category': 'Robot Framework',
            'task': 'Documentation',
            'duration_minutes': 45,
            'completed': True,
            'productivity_rating': 3,
            'notes': '',
            'created_at': (base_date + timedelta(days=5)).replace(hour=10)
        },

        # Sunday (day_of_week=6)
        {
            'date': '2025-12-28',
            'time': '11:00',
            'hour': 11,
            'day_of_week': 6,
            'preset': 'learning',
            'category': 'General',
            'task': 'Planning',
            'duration_minutes': 45,
            'completed': True,
            'productivity_rating': 4,
            'notes': '',
            'created_at': (base_date + timedelta(days=6)).replace(hour=11)
        },

        # Today's sessions (for today stats testing)
        {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': '09:00',
            'hour': 9,
            'day_of_week': datetime.now().weekday(),
            'preset': 'deep_work',
            'category': 'SOAP',
            'task': 'Today task 1',
            'duration_minutes': 52,
            'completed': True,
            'productivity_rating': 4,
            'notes': '',
            'created_at': datetime.now().replace(hour=9, minute=0)
        },
        {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': '10:30',
            'hour': 10,
            'day_of_week': datetime.now().weekday(),
            'preset': 'learning',
            'category': 'Robot Framework',
            'task': 'Today task 2',
            'duration_minutes': 45,
            'completed': True,
            'productivity_rating': 5,
            'notes': '',
            'created_at': datetime.now().replace(hour=10, minute=30)
        },

        # Session without rating (for edge case testing)
        {
            'date': '2025-12-22',
            'time': '16:00',
            'hour': 16,
            'day_of_week': 0,
            'preset': 'quick_tasks',
            'category': 'General',
            'task': 'No rating task',
            'duration_minutes': 25,
            'completed': True,
            'productivity_rating': None,
            'notes': '',
            'created_at': base_date.replace(hour=16)
        },

        # Incomplete session (should be filtered out)
        {
            'date': '2025-12-22',
            'time': '17:00',
            'hour': 17,
            'day_of_week': 0,
            'preset': 'deep_work',
            'category': 'SOAP',
            'task': 'Incomplete',
            'duration_minutes': 52,
            'completed': False,
            'productivity_rating': None,
            'notes': 'cancelled',
            'created_at': base_date.replace(hour=17)
        },
    ]

    return sessions


@pytest.fixture
def sample_sessions(mock_db, sample_sessions_data):
    """Populate mock database with sample sessions."""
    mock_db.sessions.insert_many(sample_sessions_data)
    return sample_sessions_data


@pytest.fixture
def today_date():
    """Get today's date string."""
    return datetime.now().strftime('%Y-%m-%d')


@pytest.fixture
def current_hour():
    """Get current hour."""
    return datetime.now().hour
