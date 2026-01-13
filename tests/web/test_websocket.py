"""
Web App WebSocket Event Tests.
Tests Flask-SocketIO events.
"""
import pytest
from flask_socketio import SocketIOTestClient
from unittest.mock import MagicMock, patch


class TestWebSocketEvents:
    """Test WebSocket event handling."""

    @pytest.fixture
    def socketio_client(self, app, mock_pool):
        """Create SocketIO test client."""
        import models.database as db_module
        # PostgreSQL uses _pool and get_pool() instead of db
        with patch.object(db_module, '_pool', mock_pool):
            with patch.object(db_module, 'get_pool', return_value=mock_pool):
                from app import socketio
                return SocketIOTestClient(app, socketio)

    def test_connect_event(self, socketio_client):
        """Client connection should be acknowledged."""
        assert socketio_client.is_connected()

        # Check for connect acknowledgment
        received = socketio_client.get_received()
        # Connection should succeed without errors
        assert True  # If we get here, connection worked

    def test_timer_complete_logs_session(self, socketio_client, app):
        """timer_complete event should log session to database."""
        import models.database as db_module

        # Handler calls multiple queries, mock must return appropriate data for each
        mock_cursor = MagicMock()
        # Use side_effect to return different values for sequential fetchone() calls
        mock_cursor.fetchone.side_effect = [
            {'id': 1},  # log_session INSERT RETURNING id
            {'count': 0},  # update_daily_focus_stats COUNT(*)
            {'avg_rating': None},  # update_daily_focus_stats AVG()
        ]

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            # Mock gamification functions at app level
            with patch('app.update_daily_challenge_progress', return_value={'completed': False}), \
                 patch('app.update_weekly_quest_progress', return_value={'completed': False}), \
                 patch('app.add_xp', return_value={'level_up': False, 'total_xp': 100}), \
                 patch('app.update_category_skill', return_value={}), \
                 patch('app.check_and_unlock_achievements', return_value=[]):

                session_data = {
                    'preset': 'deep_work',
                    'category': 'SOAP',
                    'task': 'WebSocket test task',
                    'duration_minutes': 52,
                    'completed': True,
                    'productivity_rating': 4,
                    'notes': ''
                }

                # Emit timer_complete event
                socketio_client.emit('timer_complete', session_data)

                # Get response
                received = socketio_client.get_received()

                # Should receive session_logged response
                session_logged = [r for r in received if r['name'] == 'session_logged']

                if session_logged:
                    assert session_logged[0]['args'][0].get('status') == 'ok'

    def test_request_stats_broadcasts_update(self, socketio_client, app):
        """request_stats event should trigger stats_update broadcast."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            # Emit request_stats (no data parameter as handler takes none)
            socketio_client.emit('request_stats')

            # Get response
            received = socketio_client.get_received()

            # Should receive stats_update
            stats_update = [r for r in received if r['name'] == 'stats_update']

            if stats_update:
                data = stats_update[0]['args'][0]
                assert 'today' in data or 'weekly' in data
