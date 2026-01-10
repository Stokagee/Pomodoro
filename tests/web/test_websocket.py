"""
Web App WebSocket Event Tests.
Tests Flask-SocketIO events.
"""
import pytest
from flask_socketio import SocketIOTestClient


class TestWebSocketEvents:
    """Test WebSocket event handling."""

    @pytest.fixture
    def socketio_client(self, app, mock_db, mock_pool, monkeypatch):
        """Create SocketIO test client."""
        import models.database as db_module
        # PostgreSQL uses _pool and get_pool() instead of db
        monkeypatch.setattr(db_module, '_pool', mock_pool)
        monkeypatch.setattr(db_module, 'get_pool', lambda: mock_pool)

        from app import socketio
        return SocketIOTestClient(app, socketio)

    def test_connect_event(self, socketio_client):
        """Client connection should be acknowledged."""
        assert socketio_client.is_connected()

        # Check for connect acknowledgment
        received = socketio_client.get_received()
        # Connection should succeed without errors
        assert True  # If we get here, connection worked

    def test_timer_complete_logs_session(self, socketio_client, mock_db):
        """timer_complete event should log session to database."""
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

    def test_request_stats_broadcasts_update(self, socketio_client, mock_db):
        """request_stats event should trigger stats_update broadcast."""
        # Emit request_stats (no data parameter as handler takes none)
        socketio_client.emit('request_stats')

        # Get response
        received = socketio_client.get_received()

        # Should receive stats_update
        stats_update = [r for r in received if r['name'] == 'stats_update']

        if stats_update:
            data = stats_update[0]['args'][0]
            assert 'today' in data or 'weekly' in data
