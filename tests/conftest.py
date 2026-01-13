"""
Shared pytest fixtures for Pomodoro Timer v2.0 tests.
Provides PostgreSQL mocking and sample test data.
"""
import pytest
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

# Get absolute paths for web and ml-service directories
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, 'web')
ML_SERVICE_DIR = os.path.join(ROOT_DIR, 'ml-service')


class MockCursor:
    """Mock PostgreSQL cursor with RealDictCursor behavior."""

    def __init__(self, data_store):
        self.data_store = data_store
        self._results = []
        self._index = 0
        self.rowcount = 0

    def execute(self, query, params=None):
        """Mock execute - store query for inspection."""
        self._last_query = query
        self._last_params = params
        query_lower = query.lower().strip()

        # Handle different query types
        if 'insert into sessions' in query_lower:
            session_id = len(self.data_store.get('sessions', [])) + 1
            self._results = [{'id': session_id}]
            self.rowcount = 1
        elif 'select count(*)' in query_lower and 'from sessions' in query_lower:
            # Count query for sessions
            sessions = self.data_store.get('sessions', [])
            count = len([s for s in sessions if s.get('completed', True)])
            self._results = [{'count': count}]
        elif 'select coalesce(sum(duration_minutes)' in query_lower:
            # Sum of minutes
            sessions = self.data_store.get('sessions', [])
            total = sum(s.get('duration_minutes', 0) for s in sessions if s.get('completed', True))
            self._results = [{'total': total}]
        elif 'select count(distinct category)' in query_lower:
            # Distinct category count
            sessions = self.data_store.get('sessions', [])
            categories = set(s.get('category', '') for s in sessions if s.get('completed', True))
            self._results = [{'count': len(categories)}]
        elif 'group by category' in query_lower and 'order by count' in query_lower:
            # Max category query
            sessions = self.data_store.get('sessions', [])
            cat_counts = {}
            for s in sessions:
                if s.get('completed', True):
                    cat = s.get('category', 'Unknown')
                    cat_counts[cat] = cat_counts.get(cat, 0) + 1
            if cat_counts:
                max_cat = max(cat_counts.items(), key=lambda x: x[1])
                self._results = [{'category': max_cat[0], 'count': max_cat[1]}]
            else:
                self._results = []
        elif 'select avg(productivity_rating)' in query_lower:
            # Average rating query
            sessions = self.data_store.get('sessions', [])
            ratings = [s['productivity_rating'] for s in sessions
                      if s.get('productivity_rating') is not None and s.get('completed', True)]
            avg = sum(ratings) / len(ratings) if ratings else None
            self._results = [{'avg_rating': avg}]
        elif 'select' in query_lower and 'from sessions' in query_lower:
            # Add id field to sessions if missing
            sessions = self.data_store.get('sessions', [])
            for i, s in enumerate(sessions):
                if 'id' not in s:
                    s['id'] = i + 1
            self._results = sessions
        elif 'insert into daily_focus' in query_lower or 'on conflict' in query_lower:
            # Upsert daily focus
            focus_id = len(self.data_store.get('daily_focus', [])) + 1
            self._results = [{'id': focus_id}]
            self.rowcount = 1
        elif 'update daily_focus' in query_lower:
            self._results = []
            self.rowcount = 1
        elif 'select' in query_lower and 'from daily_focus' in query_lower:
            self._results = self.data_store.get('daily_focus', [])
        elif 'insert into insights' in query_lower:
            insight_id = len(self.data_store.get('insights', [])) + 1
            self._results = [{'id': insight_id}]
            self.rowcount = 1
        elif 'select' in query_lower and 'from insights' in query_lower:
            self._results = self.data_store.get('insights', [])
        elif 'insert into ai_cache' in query_lower:
            cache_id = len(self.data_store.get('ai_cache', [])) + 1
            self._results = [{'id': cache_id}]
            self.rowcount = 1
        elif 'select' in query_lower and 'from ai_cache' in query_lower:
            self._results = self.data_store.get('ai_cache', [])
        elif 'delete from ai_cache' in query_lower:
            self.data_store['ai_cache'] = []
            self.rowcount = 1
        elif 'delete from sessions' in query_lower:
            self.data_store['sessions'] = []
            self.rowcount = len(self.data_store.get('sessions', []))
        elif 'select 1' in query_lower:
            self._results = [{'?column?': 1}]
        elif 'pg_extension' in query_lower:
            self._results = [{'extname': 'vector'}]
        elif 'select' in query_lower and 'from achievements' in query_lower:
            self._results = self.data_store.get('achievements', [])
        elif 'select' in query_lower and 'from streaks' in query_lower:
            streaks = self.data_store.get('streaks', [])
            self._results = streaks if streaks else [{
                'id': 1,
                'user_id': 'default',
                'current_streak': 0,
                'longest_streak': 0,
                'last_session_date': None,
                'streak_start_date': None,
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }]
        elif 'select' in query_lower and 'from daily_challenges' in query_lower:
            self._results = self.data_store.get('daily_challenges', [])
        elif 'insert into daily_challenges' in query_lower:
            challenge_id = len(self.data_store.get('daily_challenges', [])) + 1
            self._results = [{'id': challenge_id}]
            self.rowcount = 1
        elif 'select' in query_lower and 'from wellness_checkins' in query_lower:
            self._results = self.data_store.get('wellness_checkins', [])
        elif 'select' in query_lower and 'from user_profile' in query_lower:
            profiles = self.data_store.get('user_profile', [])
            self._results = profiles if profiles else [{
                'id': 1,
                'user_id': 'default',
                'xp': 0,
                'total_xp_earned': 0,
                'level': 1,
                'title': 'Beginner',
                'streak_freezes_available': 3,
                'streak_freeze_used_dates': [],
                'vacation_mode': False,
                'vacation_days_remaining': 0,
                'vacation_start_date': None,
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }]
        else:
            self._results = []
        self._index = 0

    def fetchone(self):
        """Fetch one result."""
        if self._results and self._index < len(self._results):
            result = self._results[self._index]
            self._index += 1
            return result
        return None

    def fetchall(self):
        """Fetch all results."""
        return self._results

    def close(self):
        """Close cursor."""
        pass


class MockConnection:
    """Mock PostgreSQL connection."""

    def __init__(self, data_store):
        self.data_store = data_store

    def cursor(self, cursor_factory=None):
        return MockCursor(self.data_store)

    def commit(self):
        pass

    def rollback(self):
        pass


class MockPool:
    """Mock PostgreSQL connection pool."""

    def __init__(self, data_store):
        self.data_store = data_store

    def getconn(self):
        return MockConnection(self.data_store)

    def putconn(self, conn):
        pass


@pytest.fixture
def mock_db_data():
    """Shared data store for mock database."""
    return {
        'sessions': [],
        'insights': [],
        'predictions': [],
        'daily_focus': [],
        'weekly_plans': [],
        'achievements': [],
        'user_profile': [],
    }


@pytest.fixture
def mock_pool(mock_db_data):
    """Create mock PostgreSQL pool."""
    return MockPool(mock_db_data)


@pytest.fixture
def empty_db(mock_db_data):
    """Ensure database is empty."""
    mock_db_data['sessions'] = []
    mock_db_data['insights'] = []
    mock_db_data['predictions'] = []
    return mock_db_data


@pytest.fixture
def mock_db(mock_db_data, mock_pool, monkeypatch):
    """Create mock database compatible with PostgreSQL tests.

    This fixture provides a mock PostgreSQL database environment
    by patching psycopg2 and pgvector modules.
    """
    import sys
    from unittest.mock import MagicMock

    # Ensure web directory is in path
    if WEB_DIR not in sys.path:
        sys.path.insert(0, WEB_DIR)

    # Mock psycopg2 before importing database
    mock_psycopg2 = MagicMock()
    mock_psycopg2.pool.ThreadedConnectionPool = MagicMock(return_value=mock_pool)
    monkeypatch.setitem(sys.modules, 'psycopg2', mock_psycopg2)
    monkeypatch.setitem(sys.modules, 'psycopg2.pool', mock_psycopg2.pool)
    monkeypatch.setitem(sys.modules, 'psycopg2.sql', MagicMock())
    monkeypatch.setitem(sys.modules, 'psycopg2.extras', MagicMock())

    # Mock pgvector
    mock_pgvector = MagicMock()
    mock_pgvector.psycopg2.register_vector = MagicMock()
    monkeypatch.setitem(sys.modules, 'pgvector', mock_pgvector)
    monkeypatch.setitem(sys.modules, 'pgvector.psycopg2', mock_pgvector.psycopg2)

    # Import and patch database module
    import models.database as db_module
    monkeypatch.setattr(db_module, '_pool', mock_pool)
    monkeypatch.setattr(db_module, 'get_pool', lambda: mock_pool)

    return mock_db_data


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
    # mock_db is now mock_db_data dict (PostgreSQL compatible)
    mock_db['sessions'] = sample_sessions_data
    return sample_sessions_data


@pytest.fixture
def today_date():
    """Get today's date string."""
    return datetime.now().strftime('%Y-%m-%d')


@pytest.fixture
def current_hour():
    """Get current hour."""
    return datetime.now().hour
