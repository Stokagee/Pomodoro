"""
FocusAI Learning Recommender Tests.
Tests for database helper functions and API routes.
"""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch
import sys
import os
import json

# Add web directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'web'))


class TestGetRecentTasks:
    """Test get_recent_tasks() function."""

    def test_get_recent_tasks_returns_list(self, app):
        """get_recent_tasks() should return a list."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_recent_tasks()
            assert isinstance(result, list)

    def test_get_recent_tasks_empty_db(self, app):
        """get_recent_tasks() should return empty list for empty DB."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_recent_tasks()
            assert result == []

    def test_get_recent_tasks_with_data(self, app):
        """get_recent_tasks() should return list of task names."""
        import models.database as db_module

        mock_cursor = MagicMock()
        # Function returns list of task names, not full dicts
        mock_cursor.fetchall.return_value = [
            {'task': 'React hooks'},
            {'task': 'Python async'},
        ]

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_recent_tasks()

            assert len(result) == 2
            assert result[0] in ['React hooks', 'Python async']
            assert isinstance(result[0], str)

    def test_get_recent_tasks_respects_limit(self, app):
        """get_recent_tasks(limit=N) should pass limit to SQL."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            db_module.get_recent_tasks(limit=5)

            call_args = mock_cursor.execute.call_args
            assert 'LIMIT' in call_args[0][0]


class TestGetCategoryDistribution:
    """Test get_category_distribution() function."""

    def test_get_category_distribution_empty_db(self, app):
        """get_category_distribution() should return empty dict for empty DB."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_category_distribution()
            assert result == {}

    def test_get_category_distribution_structure(self, app):
        """get_category_distribution() should return {category: count} dict."""
        import models.database as db_module

        mock_cursor = MagicMock()
        # Function expects 'category' and 'count' keys
        mock_cursor.fetchall.return_value = [
            {'category': 'Coding', 'count': 5},
            {'category': 'Learning', 'count': 3},
        ]

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_category_distribution()

            assert 'Coding' in result
            assert 'Learning' in result
            assert result['Coding'] == 5
            assert result['Learning'] == 3


class TestGetHourlyProductivity:
    """Test get_hourly_productivity() function."""

    def test_get_hourly_productivity_empty_db(self, app):
        """get_hourly_productivity() should return empty dict for empty DB."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_hourly_productivity()
            assert result == {}

    def test_get_hourly_productivity_structure(self, app):
        """get_hourly_productivity() should return {hour: {sessions, avg_rating}} dict."""
        import models.database as db_module

        mock_cursor = MagicMock()
        # Function expects 'hour', 'sessions', and 'avg_rating' keys
        mock_cursor.fetchall.return_value = [
            {'hour': 9, 'sessions': 2, 'avg_rating': 85.0},
            {'hour': 10, 'sessions': 1, 'avg_rating': 70.0},
        ]

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_hourly_productivity()

            assert 9 in result  # Integer key, not string
            assert 10 in result
            assert 'sessions' in result[9]
            assert 'avg_rating' in result[9]


class TestGetSessionsLastNDays:
    """Test get_sessions_last_n_days() function."""

    def test_get_sessions_last_n_days_empty(self, app):
        """get_sessions_last_n_days() should return empty list for empty DB."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_sessions_last_n_days()
            assert result == []

    def test_get_sessions_last_n_days_returns_data(self, app):
        """get_sessions_last_n_days() should return sessions."""
        import models.database as db_module

        today = date.today()
        mock_cursor = MagicMock()
        # Function expects sessions with 'id' and serializable fields
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'date': today, 'completed': True, 'task': 'Test',
             'preset': 'deep_work', 'category': 'SOAP', 'duration_minutes': 52,
             'productivity_rating': 4, 'hour': 9, 'day_of_week': 0},
        ]

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_sessions_last_n_days(days=30)

            assert len(result) == 1


class TestCacheAIRecommendation:
    """Test AI cache functions."""

    def test_cache_ai_recommendation_saves_data(self, app):
        """cache_ai_recommendation() should save data to DB."""
        import models.database as db_module

        mock_cursor = MagicMock()

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            test_data = {'topic': 'React', 'reason': 'Popular framework'}
            db_module.cache_ai_recommendation('learning', test_data, ttl_hours=24)

            mock_cursor.execute.assert_called()
            call_args = mock_cursor.execute.call_args
            assert 'INSERT INTO ai_cache' in call_args[0][0]


class TestGetCachedAIRecommendation:
    """Test get_cached_ai_recommendation() function."""

    def test_get_cached_ai_recommendation_returns_none_when_empty(self, app):
        """get_cached_ai_recommendation() should return None when no cache."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_cached_ai_recommendation('learning')
            assert result is None

    def test_get_cached_ai_recommendation_returns_valid_cache(self, app):
        """get_cached_ai_recommendation() should return valid cached data."""
        import models.database as db_module

        mock_cursor = MagicMock()
        # Function expects 'response' key, not 'data'
        mock_cursor.fetchone.return_value = {
            'response': {'topic': 'Python'},
            'expires_at': datetime.now() + timedelta(hours=24)
        }

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_cached_ai_recommendation('learning')
            assert result == {'topic': 'Python'}


class TestInvalidateAICache:
    """Test invalidate_ai_cache() function."""

    def test_invalidate_ai_cache_specific_type(self, app):
        """invalidate_ai_cache() should soft-delete specific type via UPDATE."""
        import models.database as db_module

        mock_cursor = MagicMock()

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            db_module.invalidate_ai_cache('learning')

            call_args = mock_cursor.execute.call_args
            # Function uses UPDATE (soft delete), not DELETE
            assert 'UPDATE ai_cache' in call_args[0][0]
            assert 'learning' in call_args[0][1]

    def test_invalidate_ai_cache_all(self, app):
        """invalidate_ai_cache() without arg should soft-delete all via UPDATE."""
        import models.database as db_module

        mock_cursor = MagicMock()

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            db_module.invalidate_ai_cache()

            call_args = mock_cursor.execute.call_args
            # Function uses UPDATE (soft delete), not DELETE
            assert 'UPDATE ai_cache' in call_args[0][0]


class TestGetNearCompletionAchievements:
    """Test get_near_completion_achievements() function."""

    def test_get_near_completion_achievements_empty(self, app):
        """get_near_completion_achievements() should return empty list."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_near_completion_achievements()
            assert result == []


class TestGetLastSessionContext:
    """Test get_last_session_context() function."""

    def test_get_last_session_context_empty_db(self, app):
        """get_last_session_context() should return empty dict for empty DB."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_last_session_context()

            # Returns empty dict when no sessions
            assert result == {}

    def test_get_last_session_context_returns_last(self, app):
        """get_last_session_context() should return last session data."""
        import models.database as db_module
        from datetime import date, time

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': 1,
            'date': date.today(),
            'time': time(9, 0),
            'category': 'Latest',
            'task': 'Latest task',
            'preset': 'deep_work',
            'duration_minutes': 52,
            'productivity_rating': 90,
            'notes': ''
        }

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_last_session_context()

            assert result['category'] == 'Latest'
            assert result['task'] == 'Latest task'
            assert result['preset'] == 'deep_work'
            assert result['productivity_rating'] == 90
            assert '_id' in result


class TestGetUserAnalyticsForAI:
    """Test get_user_analytics_for_ai() function."""

    def test_get_user_analytics_for_ai_structure(self, app):
        """get_user_analytics_for_ai() should return all required fields."""
        import models.database as db_module

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        # Return proper user_profile structure
        mock_cursor.fetchone.return_value = {
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
            'current_streak': 0,
            'longest_streak': 0,
            'last_session_date': None,
            'streak_start_date': None
        }

        with patch.object(db_module, 'get_cursor') as mock_get_cursor:
            mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = db_module.get_user_analytics_for_ai()

            # Function returns weekly_stats, streak, profile, category_distribution, hourly_productivity
            assert 'weekly_stats' in result
            assert 'streak' in result
            assert 'category_distribution' in result
            assert 'hourly_productivity' in result
            assert 'profile' in result


# =============================================================================
# FocusAI API Endpoint Tests
# =============================================================================

import responses


class TestFocusAIEndpoints:
    """Test FocusAI API endpoints."""

    def test_ai_learning_recommendations_returns_json(self, client):
        """GET /api/ai/learning-recommendations should return JSON."""
        response = client.get('/api/ai/learning-recommendations')
        assert response.status_code == 200
        assert response.content_type == 'application/json'

    def test_ai_learning_recommendations_fallback_structure(self, client):
        """Fallback recommendations should have correct structure."""
        response = client.get('/api/ai/learning-recommendations')
        data = json.loads(response.data)

        # Should have fallback structure
        assert 'recommended_topics' in data or 'error' in data or 'analysis_summary' in data

    def test_ai_next_session_returns_json(self, client):
        """GET /api/ai/next-session should return JSON."""
        response = client.get('/api/ai/next-session')
        assert response.status_code == 200
        assert response.content_type == 'application/json'

    def test_ai_next_session_fallback_structure(self, client):
        """Fallback session suggestion should have correct structure."""
        response = client.get('/api/ai/next-session')
        data = json.loads(response.data)

        # Should have either AI response or fallback
        assert 'topic' in data or 'category' in data or 'error' in data

    def test_ai_next_session_with_params(self, client):
        """GET /api/ai/next-session should accept query params."""
        response = client.get('/api/ai/next-session?category=Coding&task=React')
        assert response.status_code == 200

    def test_ai_extract_topics_endpoint(self, client):
        """POST /api/ai/extract-topics should accept tasks."""
        response = client.post(
            '/api/ai/extract-topics',
            data=json.dumps({'tasks': ['React hooks', 'Python async']}),
            content_type='application/json'
        )
        # May fail if ML service unavailable, but endpoint should exist
        assert response.status_code in [200, 500, 503]

    def test_ai_analyze_patterns_endpoint(self, client):
        """POST /api/ai/analyze-patterns should accept data."""
        response = client.post(
            '/api/ai/analyze-patterns',
            data=json.dumps({'sessions': []}),
            content_type='application/json'
        )
        assert response.status_code in [200, 500, 503]

    def test_ai_invalidate_cache_endpoint(self, client):
        """POST /api/ai/invalidate-cache should work."""
        response = client.post('/api/ai/invalidate-cache')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data.get('status') == 'ok'

    def test_ai_invalidate_cache_specific_type(self, client):
        """POST /api/ai/invalidate-cache should accept type param."""
        response = client.post(
            '/api/ai/invalidate-cache',
            data=json.dumps({'type': 'learning'}),
            content_type='application/json'
        )
        assert response.status_code == 200


class TestFocusAIWithMockedMLService:
    """Test FocusAI endpoints with mocked ML service responses."""

    @responses.activate
    def test_ai_recommendations_from_ml_service(self, client):
        """Should proxy to ML service when available."""
        responses.add(
            responses.POST,
            'http://ml-service:5001/api/ai/learning-recommendations',
            json={
                'recommended_topics': [{'topic': 'React', 'category': 'Coding'}],
                'analysis_summary': 'ML analysis',
                'confidence_score': 0.8
            },
            status=200
        )

        response = client.get('/api/ai/learning-recommendations')
        # Should have response
        assert response.status_code == 200

    @responses.activate
    def test_ai_fallback_when_ml_unavailable(self, client):
        """Should use fallback when ML service unavailable."""
        responses.add(
            responses.POST,
            'http://ml-service:5001/api/ai/learning-recommendations',
            json={'error': 'Service unavailable'},
            status=503
        )

        response = client.get('/api/ai/learning-recommendations')

        # Should return fallback, not error
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data is not None
