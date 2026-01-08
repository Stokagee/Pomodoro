"""
CacheManager Tests.
Tests AI response caching functionality in MongoDB.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import sys
import os

# Add ml-service to path
ML_SERVICE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ml-service'))
if ML_SERVICE_DIR not in sys.path:
    sys.path.insert(0, ML_SERVICE_DIR)


@pytest.fixture
def mock_db():
    """Create a mock MongoDB database."""
    db = MagicMock()
    db.ai_cache = MagicMock()
    return db


@pytest.fixture
def cache_manager(mock_db):
    """Create CacheManager with mocked database."""
    from models.ai_analyzer import CacheManager
    return CacheManager(mock_db)


class TestCacheManagerInit:
    """Test CacheManager initialization."""

    def test_init_creates_indexes(self, mock_db):
        """Should create indexes on initialization."""
        from models.ai_analyzer import CacheManager
        CacheManager(mock_db)

        mock_db.ai_cache.create_index.assert_called()

    def test_init_collection_reference(self, cache_manager, mock_db):
        """Should store reference to ai_cache collection."""
        assert cache_manager.collection == mock_db.ai_cache


class TestCacheDurations:
    """Test cache duration configuration."""

    def test_morning_briefing_duration(self, cache_manager):
        """Morning briefing should cache for 4 hours."""
        assert cache_manager.CACHE_DURATIONS.get('morning_briefing') == 4

    def test_evening_review_duration(self, cache_manager):
        """Evening review should cache for 12 hours."""
        assert cache_manager.CACHE_DURATIONS.get('evening_review') == 12

    def test_integrated_insight_duration(self, cache_manager):
        """Integrated insight should cache for 2 hours."""
        assert cache_manager.CACHE_DURATIONS.get('integrated_insight') == 2

    def test_analyze_quality_duration(self, cache_manager):
        """Quality analysis should cache for 30 minutes."""
        assert cache_manager.CACHE_DURATIONS.get('analyze_quality') == 0.5

    def test_learning_duration(self, cache_manager):
        """Learning recommendations should cache for 24 hours."""
        assert cache_manager.CACHE_DURATIONS.get('learning') == 24


class TestGetCached:
    """Test cache retrieval functionality."""

    def test_cache_hit(self, cache_manager, mock_db):
        """Should return cached data when valid cache exists."""
        expected_data = {'analysis': 'test', 'score': 85}
        mock_db.ai_cache.find_one.return_value = {
            'cache_type': 'morning_briefing',
            'data': expected_data,
            'generated_at': datetime.now(),
            'invalidated': False,
            'expires_at': datetime.now() + timedelta(hours=2)
        }

        result = cache_manager.get_cached('morning_briefing')

        assert result is not None
        assert result['analysis'] == 'test'
        assert result['score'] == 85
        assert result['from_cache'] is True

    def test_cache_miss(self, cache_manager, mock_db):
        """Should return None when no cache exists."""
        mock_db.ai_cache.find_one.return_value = None

        result = cache_manager.get_cached('morning_briefing')

        assert result is None

    def test_cache_with_params(self, cache_manager, mock_db):
        """Should use cache key when params provided."""
        mock_db.ai_cache.find_one.return_value = None

        params = {'preset': 'deep_work', 'category': 'Coding'}
        cache_manager.get_cached('analyze_quality', params)

        # Verify query includes cache_key
        call_args = mock_db.ai_cache.find_one.call_args[0][0]
        assert 'cache_key' in call_args

    def test_cache_query_filters_invalidated(self, cache_manager, mock_db):
        """Should filter out invalidated caches."""
        mock_db.ai_cache.find_one.return_value = None

        cache_manager.get_cached('morning_briefing')

        call_args = mock_db.ai_cache.find_one.call_args[0][0]
        assert call_args['invalidated'] is False

    def test_cache_query_filters_expired(self, cache_manager, mock_db):
        """Should filter out expired caches."""
        mock_db.ai_cache.find_one.return_value = None

        cache_manager.get_cached('morning_briefing')

        call_args = mock_db.ai_cache.find_one.call_args[0][0]
        assert '$gt' in call_args['expires_at']


class TestSetCache:
    """Test cache storage functionality."""

    def test_set_cache_upserts(self, cache_manager, mock_db):
        """Should upsert cache entry."""
        data = {'result': 'test'}
        cache_manager.set_cache('morning_briefing', data)

        mock_db.ai_cache.update_one.assert_called_once()
        call_args = mock_db.ai_cache.update_one.call_args
        assert call_args[1]['upsert'] is True

    def test_set_cache_uses_correct_ttl(self, cache_manager, mock_db):
        """Should set expiration based on cache type."""
        data = {'result': 'test'}
        cache_manager.set_cache('morning_briefing', data)

        call_args = mock_db.ai_cache.update_one.call_args[0][1]['$set']
        expires_at = call_args['expires_at']

        # Morning briefing should expire in ~4 hours
        expected_delta = timedelta(hours=4)
        actual_delta = expires_at - datetime.now()
        assert abs(actual_delta.total_seconds() - expected_delta.total_seconds()) < 60

    def test_set_cache_with_params(self, cache_manager, mock_db):
        """Should include cache key when params provided."""
        data = {'result': 'test'}
        params = {'preset': 'deep_work'}
        cache_manager.set_cache('analyze_quality', data, params)

        call_args = mock_db.ai_cache.update_one.call_args[0][1]['$set']
        assert call_args['cache_key'] is not None

    def test_set_cache_marks_not_invalidated(self, cache_manager, mock_db):
        """Should set invalidated to False."""
        data = {'result': 'test'}
        cache_manager.set_cache('morning_briefing', data)

        call_args = mock_db.ai_cache.update_one.call_args[0][1]['$set']
        assert call_args['invalidated'] is False


class TestInvalidateAll:
    """Test cache invalidation functionality."""

    def test_invalidate_all_updates_all(self, cache_manager, mock_db):
        """Should mark all caches as invalidated."""
        mock_db.ai_cache.update_many.return_value = MagicMock(modified_count=5)

        result = cache_manager.invalidate_all()

        mock_db.ai_cache.update_many.assert_called_once_with(
            {},
            {'$set': {'invalidated': True}}
        )
        assert result == 5

    def test_invalidate_all_returns_count(self, cache_manager, mock_db):
        """Should return number of invalidated entries."""
        mock_db.ai_cache.update_many.return_value = MagicMock(modified_count=10)

        result = cache_manager.invalidate_all()

        assert result == 10


class TestClearAll:
    """Test cache clearing functionality."""

    def test_clear_all_deletes_all(self, cache_manager, mock_db):
        """Should delete all cache entries."""
        mock_db.ai_cache.delete_many.return_value = MagicMock(deleted_count=8)

        result = cache_manager.clear_all()

        mock_db.ai_cache.delete_many.assert_called_once_with({})
        assert result == 8

    def test_clear_all_returns_count(self, cache_manager, mock_db):
        """Should return number of deleted entries."""
        mock_db.ai_cache.delete_many.return_value = MagicMock(deleted_count=15)

        result = cache_manager.clear_all()

        assert result == 15


class TestGetStatus:
    """Test cache status functionality."""

    def test_get_status_returns_counts(self, cache_manager, mock_db):
        """Should return cache statistics."""
        now = datetime.now()
        mock_db.ai_cache.find.return_value = [
            {
                'cache_type': 'morning_briefing',
                'cache_key': None,
                'generated_at': now - timedelta(hours=1),
                'expires_at': now + timedelta(hours=3),
                'invalidated': False
            },
            {
                'cache_type': 'evening_review',
                'cache_key': None,
                'generated_at': now - timedelta(hours=2),
                'expires_at': now - timedelta(hours=1),  # Expired
                'invalidated': False
            }
        ]

        result = cache_manager.get_status()

        assert result['total_cached'] == 2
        assert result['valid'] == 1  # Only one not expired
        assert 'caches' in result

    def test_get_status_cache_details(self, cache_manager, mock_db):
        """Should return details for each cache."""
        now = datetime.now()
        mock_db.ai_cache.find.return_value = [
            {
                'cache_type': 'morning_briefing',
                'cache_key': 'abc123',
                'generated_at': now,
                'expires_at': now + timedelta(hours=4),
                'invalidated': False
            }
        ]

        result = cache_manager.get_status()

        assert len(result['caches']) == 1
        cache_entry = result['caches'][0]
        assert cache_entry['type'] == 'morning_briefing'
        assert cache_entry['key'] == 'abc123'
        assert cache_entry['valid'] is True


class TestGenerateKey:
    """Test cache key generation."""

    def test_same_params_same_key(self, cache_manager):
        """Same parameters should generate same key."""
        params1 = {'preset': 'deep_work', 'category': 'Coding'}
        params2 = {'preset': 'deep_work', 'category': 'Coding'}

        key1 = cache_manager._generate_key(params1)
        key2 = cache_manager._generate_key(params2)

        assert key1 == key2

    def test_different_params_different_key(self, cache_manager):
        """Different parameters should generate different keys."""
        params1 = {'preset': 'deep_work', 'category': 'Coding'}
        params2 = {'preset': 'standard', 'category': 'Learning'}

        key1 = cache_manager._generate_key(params1)
        key2 = cache_manager._generate_key(params2)

        assert key1 != key2

    def test_key_length(self, cache_manager):
        """Key should be 16 characters."""
        params = {'test': 'value'}
        key = cache_manager._generate_key(params)

        assert len(key) == 16


class TestErrorHandling:
    """Test error handling in cache operations."""

    def test_get_cached_handles_error(self, cache_manager, mock_db):
        """get_cached should return None on error."""
        mock_db.ai_cache.find_one.side_effect = Exception("DB error")

        result = cache_manager.get_cached('morning_briefing')

        assert result is None

    def test_set_cache_handles_error(self, cache_manager, mock_db):
        """set_cache should not raise on error."""
        mock_db.ai_cache.update_one.side_effect = Exception("DB error")

        # Should not raise
        cache_manager.set_cache('morning_briefing', {'data': 'test'})

    def test_invalidate_all_handles_error(self, cache_manager, mock_db):
        """invalidate_all should return 0 on error."""
        mock_db.ai_cache.update_many.side_effect = Exception("DB error")

        result = cache_manager.invalidate_all()

        assert result == 0

    def test_clear_all_handles_error(self, cache_manager, mock_db):
        """clear_all should return 0 on error."""
        mock_db.ai_cache.delete_many.side_effect = Exception("DB error")

        result = cache_manager.clear_all()

        assert result == 0

    def test_get_status_handles_error(self, cache_manager, mock_db):
        """get_status should return error dict on failure."""
        mock_db.ai_cache.find.side_effect = Exception("DB error")

        result = cache_manager.get_status()

        assert 'error' in result
