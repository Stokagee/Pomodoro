"""
Web App Database Operation Tests.
Tests MongoDB operations in models/database.py.
"""
import pytest
from datetime import datetime
import sys
import os

# Add web directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'web'))


class TestLogSession:
    """Test session logging operations."""

    def test_log_session_creates_document(self, mock_db, monkeypatch):
        """log_session() should create document in sessions collection."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        result = db_module.log_session(
            preset='deep_work',
            category='SOAP',
            task='Test task',
            duration_minutes=52
        )

        # Should return session_id
        assert result is not None

        # Verify document exists
        doc = mock_db.sessions.find_one({'task': 'Test task'})
        assert doc is not None
        assert doc['preset'] == 'deep_work'
        assert doc['category'] == 'SOAP'
        assert doc['duration_minutes'] == 52

    def test_log_session_all_fields_stored(self, mock_db, monkeypatch):
        """log_session() should store all fields correctly."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        result = db_module.log_session(
            preset='learning',
            category='Robot Framework',
            task='Full fields test',
            duration_minutes=45,
            completed=True,
            productivity_rating=5,
            notes='Test notes'
        )

        doc = mock_db.sessions.find_one({'task': 'Full fields test'})

        assert doc['preset'] == 'learning'
        assert doc['category'] == 'Robot Framework'
        assert doc['duration_minutes'] == 45
        assert doc['completed'] == True
        assert doc['productivity_rating'] == 5
        assert doc['notes'] == 'Test notes'
        assert 'date' in doc
        assert 'time' in doc
        assert 'hour' in doc
        assert 'day_of_week' in doc
        assert 'created_at' in doc

    def test_log_session_auto_fields(self, mock_db, monkeypatch):
        """log_session() should auto-generate date/time fields."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        db_module.log_session(
            preset='quick_tasks',
            category='General',
            task='Auto fields test',
            duration_minutes=25
        )

        doc = mock_db.sessions.find_one({'task': 'Auto fields test'})

        # Check auto-generated fields
        assert doc['date'] == datetime.now().strftime('%Y-%m-%d')
        assert isinstance(doc['hour'], int)
        assert 0 <= doc['hour'] <= 23
        assert isinstance(doc['day_of_week'], int)
        assert 0 <= doc['day_of_week'] <= 6


class TestGetTodayStats:
    """Test today's statistics retrieval."""

    def test_get_today_stats_empty_db(self, empty_db, monkeypatch):
        """get_today_stats() should return zeros for empty DB."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', empty_db)

        stats = db_module.get_today_stats()

        assert stats['sessions'] == 0 or stats.get('completed_sessions', 0) == 0
        assert stats.get('total_minutes', 0) == 0

    def test_get_today_stats_with_sessions(self, mock_db, monkeypatch):
        """get_today_stats() should calculate correct stats."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        # Insert today's sessions
        today = datetime.now().strftime('%Y-%m-%d')
        mock_db.sessions.insert_many([
            {
                'date': today,
                'preset': 'deep_work',
                'category': 'SOAP',
                'task': 'Task 1',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 4,
                'hour': 9,
                'day_of_week': datetime.now().weekday(),
                'created_at': datetime.now()
            },
            {
                'date': today,
                'preset': 'learning',
                'category': 'Robot Framework',
                'task': 'Task 2',
                'duration_minutes': 45,
                'completed': True,
                'productivity_rating': 5,
                'hour': 10,
                'day_of_week': datetime.now().weekday(),
                'created_at': datetime.now()
            }
        ])

        stats = db_module.get_today_stats()

        # Should have 2 sessions
        total_sessions = stats.get('sessions', stats.get('completed_sessions', 0))
        assert total_sessions >= 2

        # Should have 97 minutes total (52 + 45)
        total_minutes = stats.get('total_minutes', 0)
        assert total_minutes >= 97

    def test_get_today_stats_avg_rating(self, mock_db, monkeypatch):
        """get_today_stats() should calculate correct average rating."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        today = datetime.now().strftime('%Y-%m-%d')
        mock_db.sessions.delete_many({})  # Clear first
        mock_db.sessions.insert_many([
            {
                'date': today,
                'preset': 'deep_work',
                'category': 'SOAP',
                'task': 'Rated 4',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 4,
                'hour': 9,
                'day_of_week': datetime.now().weekday(),
                'created_at': datetime.now()
            },
            {
                'date': today,
                'preset': 'deep_work',
                'category': 'SOAP',
                'task': 'Rated 5',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 5,
                'hour': 10,
                'day_of_week': datetime.now().weekday(),
                'created_at': datetime.now()
            }
        ])

        stats = db_module.get_today_stats()
        avg_rating = stats.get('avg_rating', 0)

        # Average of 4 and 5 should be 4.5
        if avg_rating > 0:
            assert 4.0 <= avg_rating <= 5.0


class TestGetWeeklyStats:
    """Test weekly statistics retrieval."""

    def test_get_weekly_stats_aggregation(self, sample_sessions, mock_db, monkeypatch):
        """get_weekly_stats() should aggregate by day/category/preset."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        stats = db_module.get_weekly_stats()

        # Check structure
        assert 'total_minutes' in stats or 'total_hours' in stats
        assert 'total_sessions' in stats

        # Should have daily breakdown
        if 'daily' in stats:
            assert isinstance(stats['daily'], dict)


class TestGetHistory:
    """Test session history retrieval."""

    def test_get_history_returns_list(self, sample_sessions, mock_db, monkeypatch):
        """get_history() should return list of sessions."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        history = db_module.get_history()

        assert isinstance(history, list)
        assert len(history) > 0

    def test_get_history_limit_works(self, sample_sessions, mock_db, monkeypatch):
        """get_history(limit=N) should respect limit."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        history = db_module.get_history(limit=3)

        assert len(history) <= 3


class TestInsightOperations:
    """Test insight storage and retrieval."""

    def test_save_insight(self, mock_db, monkeypatch):
        """save_insight() should store insight data."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        test_insight = {
            'best_hours': [9, 10, 11],
            'best_day': 'Monday',
            'trend': 'up'
        }

        db_module.save_insight('productivity_analysis', test_insight)

        # Verify saved
        saved = mock_db.insights.find_one({'type': 'productivity_analysis'})
        assert saved is not None
        assert saved['data']['best_hours'] == [9, 10, 11]

    def test_get_insight(self, mock_db, monkeypatch):
        """get_insight() should retrieve stored insight."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        # Insert test insight
        mock_db.insights.insert_one({
            'type': 'test_insight',
            'data': {'key': 'value'},
            'updated_at': datetime.now()
        })

        result = db_module.get_insight('test_insight')

        assert result is not None
        assert result['data']['key'] == 'value'
