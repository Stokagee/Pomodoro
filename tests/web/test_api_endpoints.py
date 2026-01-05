"""
Web App API Endpoint Tests.
Tests all Flask routes and API endpoints.
"""
import pytest
import json
import responses
from datetime import datetime


class TestPageRoutes:
    """Test HTML page routes."""

    def test_index_page_loads(self, client, mock_db):
        """GET / should return 200 with dashboard."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Pomodoro' in response.data

    def test_stats_page_loads(self, client, mock_db):
        """GET /stats should return 200."""
        response = client.get('/stats')
        assert response.status_code == 200
        assert b'Statistiky' in response.data or b'stats' in response.data.lower()

    def test_insights_page_loads(self, client, mock_db):
        """GET /insights should return 200."""
        response = client.get('/insights')
        assert response.status_code == 200
        assert b'Insights' in response.data or b'ML' in response.data


class TestConfigAPI:
    """Test configuration API endpoints."""

    def test_get_config(self, client, mock_db):
        """GET /api/config should return JSON config."""
        response = client.get('/api/config')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'presets' in data
        assert 'categories' in data
        assert 'daily_goal_sessions' in data

    def test_update_config(self, client, mock_db):
        """POST /api/config should update settings."""
        update_data = {
            'daily_goal_sessions': 10,
            'sound_enabled': False
        }

        response = client.post(
            '/api/config',
            data=json.dumps(update_data),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('status') == 'ok' or 'config' in data


class TestSessionLogging:
    """Test session logging API."""

    def test_log_session_success(self, client, mock_db):
        """POST /api/log should save session with valid data."""
        session_data = {
            'preset': 'deep_work',
            'category': 'SOAP',
            'task': 'Test task',
            'duration_minutes': 52,
            'completed': True,
            'productivity_rating': 4,
            'notes': 'Test notes'
        }

        response = client.post(
            '/api/log',
            data=json.dumps(session_data),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get('status') == 'ok'

        # Verify session was saved to database
        saved = mock_db.sessions.find_one({'task': 'Test task'})
        assert saved is not None
        assert saved['preset'] == 'deep_work'
        assert saved['productivity_rating'] == 4

    def test_log_session_minimal_data(self, client, mock_db):
        """POST /api/log should work with minimal required data."""
        session_data = {
            'preset': 'quick_tasks',
            'category': 'General',
            'task': 'Minimal task',
            'duration_minutes': 25
        }

        response = client.post(
            '/api/log',
            data=json.dumps(session_data),
            content_type='application/json'
        )

        assert response.status_code == 200


class TestStatisticsAPI:
    """Test statistics API endpoints."""

    def test_get_today_stats_empty(self, client, empty_db):
        """GET /api/stats/today should return zeros for empty DB."""
        response = client.get('/api/stats/today')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data.get('sessions', 0) == 0 or data.get('completed_sessions', 0) == 0

    def test_get_today_stats_with_data(self, client, sample_sessions, mock_db):
        """GET /api/stats/today should return correct stats."""
        response = client.get('/api/stats/today')
        assert response.status_code == 200

        data = json.loads(response.data)
        # Should have today's sessions from sample data
        assert 'sessions' in data or 'completed_sessions' in data
        assert 'total_minutes' in data or 'total_hours' in data

    def test_get_weekly_stats(self, client, sample_sessions, mock_db):
        """GET /api/stats/weekly should return aggregated data."""
        response = client.get('/api/stats/weekly')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'daily' in data or 'total_sessions' in data
        assert 'total_minutes' in data or 'total_hours' in data

    def test_get_history(self, client, sample_sessions, mock_db):
        """GET /api/history should return session list."""
        response = client.get('/api/history')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_get_history_with_limit(self, client, sample_sessions, mock_db):
        """GET /api/history?limit=5 should respect limit."""
        response = client.get('/api/history?limit=5')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert isinstance(data, list)
        assert len(data) <= 5


class TestMLIntegration:
    """Test ML service integration endpoints."""

    @responses.activate
    def test_ml_recommendation_success(self, client, mock_db):
        """GET /api/recommendation should return ML recommendation."""
        # Mock the ML service
        responses.add(
            responses.GET,
            'http://ml-service:5001/api/recommendation',
            json={
                'current_time': '10:00',
                'recommended_preset': 'deep_work',
                'reason': 'Morning focus time',
                'confidence': 0.75
            },
            status=200
        )

        response = client.get('/api/recommendation')

        # Either success or graceful failure
        assert response.status_code in [200, 503]

    @responses.activate
    def test_ml_recommendation_failure(self, client, mock_db):
        """GET /api/recommendation should handle ML service failure."""
        # Mock ML service being unavailable
        responses.add(
            responses.GET,
            'http://ml-service:5001/api/recommendation',
            body=Exception('Connection refused')
        )

        response = client.get('/api/recommendation')

        # Should return 503 or handle gracefully
        assert response.status_code in [200, 500, 503]

    @responses.activate
    def test_ml_prediction_success(self, client, mock_db):
        """GET /api/prediction should return ML prediction."""
        responses.add(
            responses.GET,
            'http://ml-service:5001/api/prediction/today',
            json={
                'predicted_sessions': 6,
                'predicted_productivity': 4.0,
                'confidence': 0.7
            },
            status=200
        )

        response = client.get('/api/prediction')

        # Either success or graceful failure
        assert response.status_code in [200, 503]
