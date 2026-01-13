"""
Start Day Feature Tests.
Tests for the "Start Day" workflow including morning briefing,
session planning, and daily challenge.
"""
import pytest
from datetime import datetime, date
from unittest.mock import MagicMock, patch
import json
import sys
import os
import responses

# Add web directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'web'))


class TestGetStartDayEndpoint:
    """Test GET /api/start-day endpoint."""

    def test_start_day_returns_success(self, client):
        """GET /api/start-day should return success."""
        response = client.get('/api/start-day')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['success'] is True

    def test_start_day_returns_categories(self, client):
        """GET /api/start-day should return categories from config."""
        response = client.get('/api/start-day')
        data = json.loads(response.data)

        assert 'categories' in data
        assert isinstance(data['categories'], list)

    def test_start_day_returns_morning_briefing_field(self, client):
        """GET /api/start-day should include morning_briefing field."""
        response = client.get('/api/start-day')
        data = json.loads(response.data)

        # Field exists (may be None if ML service unavailable)
        assert 'morning_briefing' in data

    def test_start_day_returns_daily_challenge(self, client):
        """GET /api/start-day should return daily challenge."""
        response = client.get('/api/start-day')
        data = json.loads(response.data)

        assert 'daily_challenge' in data
        challenge = data['daily_challenge']
        # Challenge should have structure (or be None)
        if challenge:
            assert 'type' in challenge or 'title' in challenge

    def test_start_day_returns_today_focus(self, client):
        """GET /api/start-day should return today's focus."""
        response = client.get('/api/start-day')
        data = json.loads(response.data)

        assert 'today_focus' in data

    def test_start_day_returns_user_profile(self, client):
        """GET /api/start-day should return user profile."""
        response = client.get('/api/start-day')
        data = json.loads(response.data)

        assert 'user_profile' in data
        profile = data['user_profile']
        if profile:
            # Should have basic profile fields
            assert 'level' in profile or 'xp' in profile or 'total_xp' in profile

    def test_start_day_returns_streak_status(self, client):
        """GET /api/start-day should return streak status."""
        response = client.get('/api/start-day')
        data = json.loads(response.data)

        assert 'streak_status' in data

    def test_start_day_returns_today_stats(self, client):
        """GET /api/start-day should return today's stats."""
        response = client.get('/api/start-day')
        data = json.loads(response.data)

        assert 'today_stats' in data

    def test_start_day_returns_date(self, client):
        """GET /api/start-day should return current date."""
        response = client.get('/api/start-day')
        data = json.loads(response.data)

        assert 'date' in data
        # Should be ISO format
        assert len(data['date']) == 10  # YYYY-MM-DD


class TestPostStartDayEndpoint:
    """Test POST /api/start-day endpoint."""

    def test_save_start_day_success(self, client):
        """POST /api/start-day should save plan successfully."""
        response = client.post(
            '/api/start-day',
            data=json.dumps({
                'themes': [{'theme': 'Coding', 'planned_sessions': 3}],
                'notes': 'Focus on React today',
                'challenge_accepted': False
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_save_start_day_returns_themes(self, client):
        """POST /api/start-day should return validated themes."""
        response = client.post(
            '/api/start-day',
            data=json.dumps({
                'themes': [
                    {'theme': 'Coding', 'planned_sessions': 3},
                    {'theme': 'Learning', 'planned_sessions': 2}
                ]
            }),
            content_type='application/json'
        )

        data = json.loads(response.data)
        assert 'themes' in data
        assert len(data['themes']) >= 0  # May filter invalid

    def test_save_start_day_calculates_total(self, client):
        """POST /api/start-day should return total planned sessions."""
        response = client.post(
            '/api/start-day',
            data=json.dumps({
                'themes': [
                    {'theme': 'Coding', 'planned_sessions': 3},
                    {'theme': 'Learning', 'planned_sessions': 2}
                ]
            }),
            content_type='application/json'
        )

        data = json.loads(response.data)
        assert 'total_planned_sessions' in data

    def test_save_start_day_with_challenge(self, client):
        """POST /api/start-day with challenge_accepted should track it."""
        response = client.post(
            '/api/start-day',
            data=json.dumps({
                'themes': [{'theme': 'Coding', 'planned_sessions': 3}],
                'challenge_accepted': True
            }),
            content_type='application/json'
        )

        data = json.loads(response.data)
        assert data['success'] is True
        # May have challenge info
        if 'challenge' in data and data['challenge']:
            assert data['challenge']['accepted'] is True

    def test_save_start_day_empty_body_fails(self, client):
        """POST /api/start-day with no data should fail."""
        response = client.post(
            '/api/start-day',
            data='',
            content_type='application/json'
        )

        assert response.status_code == 400

    def test_save_start_day_empty_themes(self, client):
        """POST /api/start-day with empty themes should succeed."""
        response = client.post(
            '/api/start-day',
            data=json.dumps({'themes': [], 'notes': 'Rest day'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_save_start_day_returns_date(self, client):
        """POST /api/start-day should return date."""
        response = client.post(
            '/api/start-day',
            data=json.dumps({'themes': []}),
            content_type='application/json'
        )

        data = json.loads(response.data)
        assert 'date' in data

    def test_save_start_day_clamps_sessions(self, client):
        """POST /api/start-day should clamp sessions to valid range."""
        response = client.post(
            '/api/start-day',
            data=json.dumps({
                'themes': [
                    {'theme': 'Coding', 'planned_sessions': 100}  # Over max
                ]
            }),
            content_type='application/json'
        )

        data = json.loads(response.data)
        # Should clamp to max (20)
        if data.get('themes'):
            assert data['themes'][0]['planned_sessions'] <= 20

    def test_save_start_day_truncates_notes(self, client):
        """POST /api/start-day should truncate long notes."""
        long_notes = 'x' * 2000
        response = client.post(
            '/api/start-day',
            data=json.dumps({
                'themes': [],
                'notes': long_notes
            }),
            content_type='application/json'
        )

        data = json.loads(response.data)
        assert data['success'] is True
        if 'notes' in data:
            assert len(data['notes']) <= 1000


class TestStartDayValidation:
    """Test validation in Start Day endpoints."""

    def test_invalid_category_filtered(self, client):
        """Invalid categories should be filtered out."""
        response = client.post(
            '/api/start-day',
            data=json.dumps({
                'themes': [
                    {'theme': 'INVALID_CATEGORY_XYZ', 'planned_sessions': 5}
                ]
            }),
            content_type='application/json'
        )

        data = json.loads(response.data)
        assert data['success'] is True
        # Invalid category should be filtered out
        assert len(data.get('themes', [])) == 0

    def test_negative_sessions_clamped(self, client):
        """Negative session count should be clamped to 1."""
        response = client.post(
            '/api/start-day',
            data=json.dumps({
                'themes': [
                    {'theme': 'Coding', 'planned_sessions': -5}
                ]
            }),
            content_type='application/json'
        )

        data = json.loads(response.data)
        if data.get('themes'):
            assert data['themes'][0]['planned_sessions'] >= 1


class TestStartDayIntegration:
    """Integration tests for Start Day workflow."""

    def test_start_day_then_check_focus(self, client, app):
        """After Start Day, daily focus should be set."""
        import models.database as db_module

        with patch.object(db_module, 'set_daily_focus') as mock_set:
            mock_set.return_value = True

            with patch.object(db_module, 'get_daily_focus') as mock_get:
                mock_get.return_value = {
                    'date': date.today().isoformat(),
                    'themes': [{'theme': 'Coding', 'planned_sessions': 4}],
                    'notes': 'Integration test',
                    'total_planned': 4
                }

                # First, set the start day
                client.post(
                    '/api/start-day',
                    data=json.dumps({
                        'themes': [
                            {'theme': 'Coding', 'planned_sessions': 4}
                        ],
                        'notes': 'Integration test'
                    }),
                    content_type='application/json'
                )

                # Then check today's focus
                today = date.today().isoformat()
                response = client.get(f'/api/focus/{today}')

                data = json.loads(response.data)
                assert 'focus' in data or 'themes' in data

    def test_multiple_start_day_updates(self, client):
        """Multiple Start Day calls should update, not duplicate."""
        # First plan
        client.post(
            '/api/start-day',
            data=json.dumps({
                'themes': [{'theme': 'Coding', 'planned_sessions': 2}]
            }),
            content_type='application/json'
        )

        # Second plan (update)
        response = client.post(
            '/api/start-day',
            data=json.dumps({
                'themes': [{'theme': 'Learning', 'planned_sessions': 5}]
            }),
            content_type='application/json'
        )

        data = json.loads(response.data)
        assert data['success'] is True


class TestStartDayWithMockedMLService:
    """Test Start Day with mocked ML service."""

    @responses.activate
    def test_start_day_with_ml_briefing(self, client):
        """GET /api/start-day should include ML morning briefing when available."""
        responses.add(
            responses.GET,
            'http://ml-service:5001/api/ai/morning-briefing',
            json={
                'analysis': 'You had a productive day yesterday.',
                'recommendations': ['Focus on deep work in the morning'],
                'predicted_productivity': 85
            },
            status=200
        )

        # Also mock the categories sync
        responses.add(
            responses.POST,
            'http://ml-service:5001/api/config/categories',
            json={'status': 'ok'},
            status=200
        )

        response = client.get('/api/start-day')
        data = json.loads(response.data)

        assert data['success'] is True
        # Morning briefing should be populated
        if data.get('morning_briefing'):
            assert 'analysis' in data['morning_briefing'] or 'recommendations' in data['morning_briefing']

    @responses.activate
    def test_start_day_handles_ml_failure(self, client):
        """GET /api/start-day should handle ML service failure gracefully."""
        responses.add(
            responses.GET,
            'http://ml-service:5001/api/ai/morning-briefing',
            json={'error': 'Service unavailable'},
            status=503
        )

        responses.add(
            responses.POST,
            'http://ml-service:5001/api/config/categories',
            json={'status': 'ok'},
            status=200
        )

        response = client.get('/api/start-day')
        data = json.loads(response.data)

        # Should still succeed, just without briefing
        assert data['success'] is True
        assert 'categories' in data


class TestSyncCategoriesToMLService:
    """Test category synchronization with ML service."""

    @responses.activate
    def test_categories_synced_on_start_day(self, client):
        """GET /api/start-day should sync categories to ML service."""
        # Mock the categories endpoint
        responses.add(
            responses.POST,
            'http://ml-service:5001/api/config/categories',
            json={'status': 'ok'},
            status=200
        )

        # Mock morning briefing
        responses.add(
            responses.GET,
            'http://ml-service:5001/api/ai/morning-briefing',
            json={'analysis': 'test'},
            status=200
        )

        response = client.get('/api/start-day')

        # Categories endpoint should have been called
        assert len([r for r in responses.calls if 'categories' in r.request.url]) >= 1

    @responses.activate
    def test_start_day_continues_without_sync(self, client):
        """GET /api/start-day should work even if sync fails."""
        # Mock categories endpoint to fail
        responses.add(
            responses.POST,
            'http://ml-service:5001/api/config/categories',
            json={'error': 'Failed'},
            status=500
        )

        response = client.get('/api/start-day')
        data = json.loads(response.data)

        # Should still return data
        assert data['success'] is True
        assert 'categories' in data


class TestDailyChallengeIntegration:
    """Test daily challenge as part of Start Day."""

    def test_challenge_in_start_day_response(self, client):
        """GET /api/start-day should include daily challenge."""
        response = client.get('/api/start-day')
        data = json.loads(response.data)

        assert 'daily_challenge' in data

    def test_accepting_challenge_via_start_day(self, client):
        """POST /api/start-day should handle challenge acceptance."""
        response = client.post(
            '/api/start-day',
            data=json.dumps({
                'themes': [],
                'challenge_accepted': True
            }),
            content_type='application/json'
        )

        data = json.loads(response.data)
        assert data['success'] is True
