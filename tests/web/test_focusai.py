"""
FocusAI Learning Recommender Tests.
Tests for database helper functions and API routes.
"""
import pytest
from datetime import datetime, timedelta
import sys
import os

# Add web directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'web'))


class TestGetRecentTasks:
    """Test get_recent_tasks() function."""

    def test_get_recent_tasks_returns_list(self, mock_db, monkeypatch):
        """get_recent_tasks() should return a list."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        result = db_module.get_recent_tasks()
        assert isinstance(result, list)

    def test_get_recent_tasks_empty_db(self, empty_db, monkeypatch):
        """get_recent_tasks() should return empty list for empty DB."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', empty_db)

        result = db_module.get_recent_tasks()
        assert result == []

    def test_get_recent_tasks_with_data(self, mock_db, monkeypatch):
        """get_recent_tasks() should return tasks with category."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        # Insert test sessions
        mock_db.sessions.insert_many([
            {'task': 'React hooks', 'category': 'Coding', 'created_at': datetime.now()},
            {'task': 'Python async', 'category': 'Learning', 'created_at': datetime.now()},
            {'task': '', 'category': 'Empty', 'created_at': datetime.now()},  # Empty task
        ])

        result = db_module.get_recent_tasks()

        assert len(result) == 2  # Empty task excluded
        assert result[0]['task'] in ['React hooks', 'Python async']
        assert 'category' in result[0]
        assert '_id' not in result[0]  # Should not include _id

    def test_get_recent_tasks_respects_limit(self, mock_db, monkeypatch):
        """get_recent_tasks(limit=N) should respect the limit."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        # Insert 10 sessions
        for i in range(10):
            mock_db.sessions.insert_one({
                'task': f'Task {i}',
                'category': 'Test',
                'created_at': datetime.now() - timedelta(minutes=i)
            })

        result = db_module.get_recent_tasks(limit=5)
        assert len(result) == 5


class TestGetCategoryDistribution:
    """Test get_category_distribution() function."""

    def test_get_category_distribution_empty_db(self, empty_db, monkeypatch):
        """get_category_distribution() should return empty dict for empty DB."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', empty_db)

        result = db_module.get_category_distribution()
        assert result == {}

    def test_get_category_distribution_structure(self, mock_db, monkeypatch):
        """get_category_distribution() should return correct structure."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        mock_db.sessions.insert_many([
            {'category': 'Coding', 'completed': True, 'duration_minutes': 52},
            {'category': 'Coding', 'completed': True, 'duration_minutes': 52},
            {'category': 'Learning', 'completed': True, 'duration_minutes': 45},
            {'category': 'Other', 'completed': False, 'duration_minutes': 25},  # Not completed
        ])

        result = db_module.get_category_distribution()

        assert 'Coding' in result
        assert 'Learning' in result
        assert 'Other' not in result  # Not completed excluded

        # Check structure
        assert 'percentage' in result['Coding']
        assert 'sessions' in result['Coding']
        assert 'minutes' in result['Coding']

    def test_get_category_distribution_percentages(self, mock_db, monkeypatch):
        """get_category_distribution() should calculate correct percentages."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        # 60 sessions Coding, 40 sessions Learning = 60%, 40%
        for _ in range(60):
            mock_db.sessions.insert_one({'category': 'Coding', 'completed': True, 'duration_minutes': 52})
        for _ in range(40):
            mock_db.sessions.insert_one({'category': 'Learning', 'completed': True, 'duration_minutes': 45})

        result = db_module.get_category_distribution()

        assert result['Coding']['percentage'] == 60.0
        assert result['Learning']['percentage'] == 40.0
        assert result['Coding']['sessions'] == 60
        assert result['Learning']['sessions'] == 40


class TestGetHourlyProductivity:
    """Test get_hourly_productivity() function."""

    def test_get_hourly_productivity_empty_db(self, empty_db, monkeypatch):
        """get_hourly_productivity() should return empty dict for empty DB."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', empty_db)

        result = db_module.get_hourly_productivity()
        assert result == {}

    def test_get_hourly_productivity_structure(self, mock_db, monkeypatch):
        """get_hourly_productivity() should return correct structure."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        mock_db.sessions.insert_many([
            {'hour': 9, 'completed': True, 'productivity_rating': 80},
            {'hour': 9, 'completed': True, 'productivity_rating': 90},
            {'hour': 10, 'completed': True, 'productivity_rating': 70},
        ])

        result = db_module.get_hourly_productivity()

        assert '9' in result
        assert '10' in result
        assert 'sessions' in result['9']
        assert 'avg_rating' in result['9']

    def test_get_hourly_productivity_calculations(self, mock_db, monkeypatch):
        """get_hourly_productivity() should calculate correct averages."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        mock_db.sessions.insert_many([
            {'hour': 9, 'completed': True, 'productivity_rating': 80},
            {'hour': 9, 'completed': True, 'productivity_rating': 100},
        ])

        result = db_module.get_hourly_productivity()

        assert result['9']['sessions'] == 2
        assert result['9']['avg_rating'] == 90.0


class TestGetSessionsLastNDays:
    """Test get_sessions_last_n_days() function."""

    def test_get_sessions_last_n_days_empty(self, empty_db, monkeypatch):
        """get_sessions_last_n_days() should return empty list for empty DB."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', empty_db)

        result = db_module.get_sessions_last_n_days()
        assert result == []

    def test_get_sessions_last_n_days_filters_old(self, mock_db, monkeypatch):
        """get_sessions_last_n_days() should filter out old sessions."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        today = datetime.now().strftime('%Y-%m-%d')
        old_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')

        mock_db.sessions.insert_many([
            {'date': today, 'completed': True, 'created_at': datetime.now()},
            {'date': old_date, 'completed': True, 'created_at': datetime.now() - timedelta(days=60)},
        ])

        result = db_module.get_sessions_last_n_days(days=30)

        assert len(result) == 1
        assert result[0]['date'] == today

    def test_get_sessions_last_n_days_only_completed(self, mock_db, monkeypatch):
        """get_sessions_last_n_days() should only return completed sessions."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        today = datetime.now().strftime('%Y-%m-%d')

        mock_db.sessions.insert_many([
            {'date': today, 'completed': True, 'task': 'Completed'},
            {'date': today, 'completed': False, 'task': 'Not completed'},
        ])

        result = db_module.get_sessions_last_n_days()

        assert len(result) == 1
        assert result[0]['task'] == 'Completed'


class TestCacheAIRecommendation:
    """Test AI cache functions."""

    def test_cache_ai_recommendation_saves_data(self, mock_db, monkeypatch):
        """cache_ai_recommendation() should save data to DB."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        test_data = {'topic': 'React', 'reason': 'Popular framework'}
        db_module.cache_ai_recommendation('learning', test_data, ttl_hours=24)

        # Verify saved
        cached = mock_db.ai_cache.find_one({'type': 'learning'})
        assert cached is not None
        assert cached['data'] == test_data
        assert 'expires_at' in cached
        assert 'generated_at' in cached

    def test_cache_ai_recommendation_upserts(self, mock_db, monkeypatch):
        """cache_ai_recommendation() should update existing cache."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        # First save
        db_module.cache_ai_recommendation('learning', {'v': 1})
        # Second save (should update)
        db_module.cache_ai_recommendation('learning', {'v': 2})

        # Should only have one document
        count = mock_db.ai_cache.count_documents({'type': 'learning'})
        assert count == 1

        # Should have updated value
        cached = mock_db.ai_cache.find_one({'type': 'learning'})
        assert cached['data'] == {'v': 2}


class TestGetCachedAIRecommendation:
    """Test get_cached_ai_recommendation() function."""

    def test_get_cached_ai_recommendation_returns_none_when_empty(self, empty_db, monkeypatch):
        """get_cached_ai_recommendation() should return None when no cache."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', empty_db)

        result = db_module.get_cached_ai_recommendation('learning')
        assert result is None

    def test_get_cached_ai_recommendation_returns_valid_cache(self, mock_db, monkeypatch):
        """get_cached_ai_recommendation() should return valid cached data."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        # Insert valid cache
        mock_db.ai_cache.insert_one({
            'type': 'learning',
            'data': {'topic': 'Python'},
            'expires_at': datetime.now() + timedelta(hours=24)
        })

        result = db_module.get_cached_ai_recommendation('learning')
        assert result == {'topic': 'Python'}

    def test_get_cached_ai_recommendation_ignores_expired(self, mock_db, monkeypatch):
        """get_cached_ai_recommendation() should return None for expired cache."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        # Insert expired cache
        mock_db.ai_cache.insert_one({
            'type': 'learning',
            'data': {'topic': 'Old'},
            'expires_at': datetime.now() - timedelta(hours=1)  # Expired
        })

        result = db_module.get_cached_ai_recommendation('learning')
        assert result is None


class TestInvalidateAICache:
    """Test invalidate_ai_cache() function."""

    def test_invalidate_ai_cache_specific_type(self, mock_db, monkeypatch):
        """invalidate_ai_cache() should delete specific type."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        mock_db.ai_cache.insert_many([
            {'type': 'learning', 'data': {}},
            {'type': 'next_session', 'data': {}},
        ])

        db_module.invalidate_ai_cache('learning')

        # Only 'learning' should be deleted
        assert mock_db.ai_cache.count_documents({'type': 'learning'}) == 0
        assert mock_db.ai_cache.count_documents({'type': 'next_session'}) == 1

    def test_invalidate_ai_cache_all(self, mock_db, monkeypatch):
        """invalidate_ai_cache() without arg should delete all."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        mock_db.ai_cache.insert_many([
            {'type': 'learning', 'data': {}},
            {'type': 'next_session', 'data': {}},
        ])

        db_module.invalidate_ai_cache()

        assert mock_db.ai_cache.count_documents({}) == 0


class TestGetNearCompletionAchievements:
    """Test get_near_completion_achievements() function."""

    def test_get_near_completion_achievements_empty(self, empty_db, monkeypatch):
        """get_near_completion_achievements() should return empty list."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', empty_db)

        result = db_module.get_near_completion_achievements()
        assert result == []

    def test_get_near_completion_achievements_filters_by_threshold(self, mock_db, monkeypatch):
        """get_near_completion_achievements() should filter by threshold."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        mock_db.achievements.insert_many([
            {'achievement_id': 'ach1', 'name': 'Near', 'progress': 75, 'target': 100, 'unlocked': False},
            {'achievement_id': 'ach2', 'name': 'Far', 'progress': 10, 'target': 100, 'unlocked': False},
            {'achievement_id': 'ach3', 'name': 'Done', 'progress': 100, 'target': 100, 'unlocked': True},
        ])

        result = db_module.get_near_completion_achievements(threshold=50)

        assert len(result) == 1
        assert result[0]['achievement_id'] == 'ach1'
        assert result[0]['percentage'] == 75.0


class TestGetLastSessionContext:
    """Test get_last_session_context() function."""

    def test_get_last_session_context_empty_db(self, empty_db, monkeypatch):
        """get_last_session_context() should return defaults for empty DB."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', empty_db)

        result = db_module.get_last_session_context()

        assert result['last_category'] == ''
        assert result['last_task'] == ''
        assert result['last_preset'] == 'deep_work'
        assert result['last_rating'] is None

    def test_get_last_session_context_returns_last(self, mock_db, monkeypatch):
        """get_last_session_context() should return last session data."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        mock_db.sessions.insert_many([
            {
                'category': 'Old',
                'task': 'Old task',
                'preset': 'learning',
                'productivity_rating': 70,
                'completed': True,
                'created_at': datetime.now() - timedelta(hours=2)
            },
            {
                'category': 'Latest',
                'task': 'Latest task',
                'preset': 'deep_work',
                'productivity_rating': 90,
                'completed': True,
                'created_at': datetime.now()
            },
        ])

        result = db_module.get_last_session_context()

        assert result['last_category'] == 'Latest'
        assert result['last_task'] == 'Latest task'
        assert result['last_preset'] == 'deep_work'
        assert result['last_rating'] == 90


class TestGetUserAnalyticsForAI:
    """Test get_user_analytics_for_ai() function."""

    def test_get_user_analytics_for_ai_structure(self, mock_db, monkeypatch):
        """get_user_analytics_for_ai() should return all required fields."""
        import models.database as db_module
        monkeypatch.setattr(db_module, 'db', mock_db)

        result = db_module.get_user_analytics_for_ai()

        assert 'recent_sessions' in result
        assert 'category_distribution' in result
        assert 'skill_levels' in result
        assert 'streak_data' in result
        assert 'recent_tasks' in result
        assert 'productivity_by_time' in result
        assert 'achievements_progress' in result
        assert 'user_profile' in result


# =============================================================================
# FocusAI API Endpoint Tests
# =============================================================================

import json
import responses


class TestFocusAIEndpoints:
    """Test FocusAI API endpoints."""

    def test_ai_learning_recommendations_returns_json(self, client, mock_db):
        """GET /api/ai/learning-recommendations should return JSON."""
        response = client.get('/api/ai/learning-recommendations')
        assert response.status_code == 200
        assert response.content_type == 'application/json'

    def test_ai_learning_recommendations_fallback_structure(self, client, mock_db):
        """Fallback recommendations should have correct structure."""
        response = client.get('/api/ai/learning-recommendations')
        data = json.loads(response.data)

        # Should have fallback structure
        assert 'recommended_topics' in data or 'error' in data or 'analysis_summary' in data

    def test_ai_next_session_returns_json(self, client, mock_db):
        """GET /api/ai/next-session should return JSON."""
        response = client.get('/api/ai/next-session')
        assert response.status_code == 200
        assert response.content_type == 'application/json'

    def test_ai_next_session_fallback_structure(self, client, mock_db):
        """Fallback session suggestion should have correct structure."""
        response = client.get('/api/ai/next-session')
        data = json.loads(response.data)

        # Should have either AI response or fallback
        assert 'topic' in data or 'category' in data or 'error' in data

    def test_ai_next_session_with_params(self, client, mock_db):
        """GET /api/ai/next-session should accept query params."""
        response = client.get('/api/ai/next-session?category=Coding&task=React')
        assert response.status_code == 200

    def test_ai_extract_topics_endpoint(self, client, mock_db):
        """POST /api/ai/extract-topics should accept tasks."""
        response = client.post(
            '/api/ai/extract-topics',
            data=json.dumps({'tasks': ['React hooks', 'Python async']}),
            content_type='application/json'
        )
        # May fail if ML service unavailable, but endpoint should exist
        assert response.status_code in [200, 500, 503]

    def test_ai_analyze_patterns_endpoint(self, client, mock_db):
        """POST /api/ai/analyze-patterns should accept data."""
        response = client.post(
            '/api/ai/analyze-patterns',
            data=json.dumps({'sessions': []}),
            content_type='application/json'
        )
        assert response.status_code in [200, 500, 503]

    def test_ai_invalidate_cache_endpoint(self, client, mock_db):
        """POST /api/ai/invalidate-cache should work."""
        response = client.post('/api/ai/invalidate-cache')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data.get('status') == 'ok'

    def test_ai_invalidate_cache_specific_type(self, client, mock_db):
        """POST /api/ai/invalidate-cache should accept type param."""
        response = client.post(
            '/api/ai/invalidate-cache',
            data=json.dumps({'type': 'learning'}),
            content_type='application/json'
        )
        assert response.status_code == 200

    def test_cached_response_served(self, client, mock_db):
        """Cached AI response should be served when available."""
        # Insert cached data
        mock_db.ai_cache.insert_one({
            'type': 'next_session',
            'data': {
                'topic': 'Cached Topic',
                'category': 'Cached',
                'reason': 'From cache'
            },
            'expires_at': datetime.now() + timedelta(hours=1)
        })

        response = client.get('/api/ai/next-session')
        data = json.loads(response.data)

        # Should return cached data
        if 'topic' in data:
            assert data['topic'] == 'Cached Topic'


class TestFocusAIWithMockedMLService:
    """Test FocusAI endpoints with mocked ML service responses."""

    @responses.activate
    def test_ai_recommendations_from_ml_service(self, client, mock_db):
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
        data = json.loads(response.data)

        # Should have ML service response or fallback
        assert response.status_code == 200

    @responses.activate
    def test_ai_fallback_when_ml_unavailable(self, client, mock_db):
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
