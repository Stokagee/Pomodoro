"""
Web App Database Operation Tests.
Tests PostgreSQL operations in models/database.py.
"""
import pytest
from datetime import datetime, date
from unittest.mock import MagicMock, patch
import sys
import os

# Add web directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'web'))


class TestLogSession:
    """Test session logging operations."""

    def test_log_session_creates_document(self, app):
        """log_session() should return session id."""
        import models.database as db_module

        # Mock get_cursor context manager
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 1}

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.log_session(
                preset='deep_work',
                category='SOAP',
                task='Test task',
                duration_minutes=52
            )

            assert result is not None
            assert result == '1'
            mock_cursor.execute.assert_called_once()

    def test_log_session_all_fields_stored(self, app):
        """log_session() should pass all fields to SQL."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 2}

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.log_session(
                preset='learning',
                category='Robot Framework',
                task='Full fields test',
                duration_minutes=45,
                completed=True,
                productivity_rating=5,
                notes='Test notes'
            )

            assert result == '2'
            # Check execute was called with correct parameters
            call_args = mock_cursor.execute.call_args
            assert 'INSERT INTO sessions' in call_args[0][0]
            params = call_args[0][1]
            assert params[0] == 'learning'  # preset
            assert params[1] == 'Robot Framework'  # category
            assert params[2] == 'Full fields test'  # task
            assert params[3] == 45  # duration_minutes
            assert params[4] == True  # completed
            assert params[5] == 5  # productivity_rating

    def test_log_session_auto_fields(self, app):
        """log_session() should include date/time in SQL params."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 3}

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            db_module.log_session(
                preset='quick_tasks',
                category='General',
                task='Auto fields test',
                duration_minutes=25
            )

            call_args = mock_cursor.execute.call_args
            params = call_args[0][1]
            # Check that date and time are passed
            assert isinstance(params[8], date)  # date
            assert params[8] == date.today()


class TestGetTodayStats:
    """Test today's statistics retrieval."""

    def test_get_today_stats_empty_db(self, app):
        """get_today_stats() should return zeros for empty DB."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            stats = db_module.get_today_stats()

            assert stats['sessions'] == 0
            assert stats['total_minutes'] == 0

    def test_get_today_stats_with_sessions(self, app):
        """get_today_stats() should calculate correct stats."""
        import models.database as db_module

        today = date.today()
        mock_sessions = [
            {
                'id': 1,
                'date': today,
                'time': '09:00:00',
                'preset': 'deep_work',
                'category': 'SOAP',
                'task': 'Task 1',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 4,
                'notes': '',
                'hour': 9,
                'day_of_week': today.weekday(),
                'created_at': datetime.now()
            },
            {
                'id': 2,
                'date': today,
                'time': '10:00:00',
                'preset': 'learning',
                'category': 'Robot Framework',
                'task': 'Task 2',
                'duration_minutes': 45,
                'completed': True,
                'productivity_rating': 5,
                'notes': '',
                'hour': 10,
                'day_of_week': today.weekday(),
                'created_at': datetime.now()
            }
        ]

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_sessions

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            stats = db_module.get_today_stats()

            assert stats['sessions'] == 2
            assert stats['total_minutes'] == 97  # 52 + 45

    def test_get_today_stats_avg_rating(self, app):
        """get_today_stats() should calculate correct average rating."""
        import models.database as db_module

        today = date.today()
        mock_sessions = [
            {
                'id': 1,
                'date': today,
                'time': '09:00:00',
                'preset': 'deep_work',
                'category': 'SOAP',
                'task': 'Rated 4',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 4,  # Old format: 4 -> 80%
                'notes': '',
                'hour': 9,
                'day_of_week': today.weekday(),
                'created_at': datetime.now()
            },
            {
                'id': 2,
                'date': today,
                'time': '10:00:00',
                'preset': 'deep_work',
                'category': 'SOAP',
                'task': 'Rated 5',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 5,  # Old format: 5 -> 100%
                'notes': '',
                'hour': 10,
                'day_of_week': today.weekday(),
                'created_at': datetime.now()
            }
        ]

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_sessions

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            stats = db_module.get_today_stats()

            # Rating 4 -> 80%, Rating 5 -> 100%, avg = 90%
            assert stats['avg_rating'] == 90.0


class TestGetWeeklyStats:
    """Test weekly statistics retrieval."""

    def test_get_weekly_stats_aggregation(self, app):
        """get_weekly_stats() should aggregate by day/category/preset."""
        import models.database as db_module

        today = date.today()
        mock_sessions = [
            {
                'date': today,
                'time': '09:00:00',
                'preset': 'deep_work',
                'category': 'SOAP',
                'duration_minutes': 52,
                'productivity_rating': 80,
                'hour': 9,
                'day_of_week': today.weekday()
            },
            {
                'date': today,
                'time': '10:00:00',
                'preset': 'learning',
                'category': 'Robot Framework',
                'duration_minutes': 45,
                'productivity_rating': 85,
                'hour': 10,
                'day_of_week': today.weekday()
            }
        ]

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_sessions

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            stats = db_module.get_weekly_stats()

            assert 'total_minutes' in stats
            assert 'total_sessions' in stats
            assert 'daily' in stats
            assert isinstance(stats['daily'], dict)


class TestGetHistory:
    """Test session history retrieval."""

    def test_get_history_returns_list(self, app):
        """get_history() should return list of sessions."""
        import models.database as db_module

        mock_sessions = [
            {
                'id': 1,
                'date': date.today(),
                'time': '09:00:00',
                'preset': 'deep_work',
                'category': 'SOAP',
                'task': 'Test',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 80,
                'notes': '',
                'created_at': datetime.now()
            }
        ]

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_sessions

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            history = db_module.get_history()

            assert isinstance(history, list)
            assert len(history) == 1

    def test_get_history_limit_works(self, app):
        """get_history(limit=N) should pass limit to SQL."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            db_module.get_history(limit=3)

            # Check that LIMIT was passed
            call_args = mock_cursor.execute.call_args
            assert 'LIMIT' in call_args[0][0]
            assert call_args[0][1] == (3,)


class TestInsightOperations:
    """Test insight storage and retrieval."""

    def test_save_insight(self, app):
        """save_insight() should execute INSERT query."""
        import models.database as db_module

        mock_cursor = MagicMock()

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            test_insight = {
                'best_hours': [9, 10, 11],
                'best_day': 'Monday',
                'trend': 'up'
            }

            db_module.save_insight('productivity_analysis', test_insight)

            mock_cursor.execute.assert_called_once()
            call_args = mock_cursor.execute.call_args
            assert 'INSERT INTO insights' in call_args[0][0]
            assert call_args[0][1][0] == 'productivity_analysis'

    def test_get_insight(self, app):
        """get_insight() should retrieve stored insight."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'type': 'test_insight',
            'data': {'key': 'value'},
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_insight('test_insight')

            assert result is not None
            assert result['data']['key'] == 'value'
            mock_cursor.execute.assert_called_once()
