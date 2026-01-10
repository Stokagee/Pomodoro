"""
CacheManager Tests.
Tests AI response caching functionality in PostgreSQL.
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
def mock_database():
    """Create a mock database module."""
    mock = MagicMock()
    mock.get_cached = MagicMock(return_value=None)
    mock.set_cache = MagicMock()
    mock.invalidate_all_cache = MagicMock(return_value=5)
    mock.clear_all_cache = MagicMock(return_value=8)
    mock.get_cache_status = MagicMock(return_value={'total_cached': 2, 'valid': 1, 'caches': []})
    return mock


@pytest.fixture
def cache_manager(mock_database):
    """Create CacheManager with mocked database."""
    with patch.dict('sys.modules', {'db': mock_database}):
        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            return CacheManager()


class TestCacheManagerInit:
    """Test CacheManager initialization."""

    def test_init_no_args(self):
        """Should initialize without arguments."""
        with patch('models.ai_analyzer.database'):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            assert manager is not None

    def test_cache_durations_defined(self, cache_manager):
        """Should have cache durations defined."""
        assert 'morning_briefing' in cache_manager.CACHE_DURATIONS
        assert 'evening_review' in cache_manager.CACHE_DURATIONS


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
        """Learning recommendations should cache for 2 hours (dynamic)."""
        assert cache_manager.CACHE_DURATIONS.get('learning') == 2


class TestGetCached:
    """Test cache retrieval functionality."""

    def test_cache_hit(self, mock_database):
        """Should return cached data when valid cache exists."""
        expected_data = {'analysis': 'test', 'score': 85, 'from_cache': True}
        mock_database.get_cached.return_value = expected_data

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            result = manager.get_cached('morning_briefing')

        assert result is not None
        assert result['analysis'] == 'test'
        assert result['score'] == 85

    def test_cache_miss(self, mock_database):
        """Should return None when no cache exists."""
        mock_database.get_cached.return_value = None

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            result = manager.get_cached('morning_briefing')

        assert result is None

    def test_cache_with_params(self, mock_database):
        """Should use cache key when params provided."""
        mock_database.get_cached.return_value = None

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            params = {'preset': 'deep_work', 'category': 'Coding'}
            manager.get_cached('analyze_quality', params)

        # Verify database.get_cached was called with cache_key
        mock_database.get_cached.assert_called_once()
        call_args = mock_database.get_cached.call_args[0]
        assert call_args[0] == 'analyze_quality'
        assert call_args[1] is not None  # cache_key generated


class TestSetCache:
    """Test cache storage functionality."""

    def test_set_cache_calls_database(self, mock_database):
        """Should call database.set_cache."""
        data = {'result': 'test'}

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            manager.set_cache('morning_briefing', data)

        mock_database.set_cache.assert_called_once()

    def test_set_cache_uses_correct_ttl(self, mock_database):
        """Should set expiration based on cache type."""
        data = {'result': 'test'}

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            manager.set_cache('morning_briefing', data)

        # Morning briefing should use 4 hours TTL
        call_args = mock_database.set_cache.call_args[0]
        assert call_args[3] == 4  # ttl_hours

    def test_set_cache_with_params(self, mock_database):
        """Should include cache key when params provided."""
        data = {'result': 'test'}
        params = {'preset': 'deep_work'}

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            manager.set_cache('analyze_quality', data, params)

        call_args = mock_database.set_cache.call_args[0]
        assert call_args[2] is not None  # cache_key


class TestInvalidateAll:
    """Test cache invalidation functionality."""

    def test_invalidate_all_calls_database(self, mock_database):
        """Should call database.invalidate_all_cache."""
        mock_database.invalidate_all_cache.return_value = 5

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            result = manager.invalidate_all()

        mock_database.invalidate_all_cache.assert_called_once()
        assert result == 5

    def test_invalidate_all_returns_count(self, mock_database):
        """Should return number of invalidated entries."""
        mock_database.invalidate_all_cache.return_value = 10

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            result = manager.invalidate_all()

        assert result == 10


class TestClearAll:
    """Test cache clearing functionality."""

    def test_clear_all_calls_database(self, mock_database):
        """Should call database.clear_all_cache."""
        mock_database.clear_all_cache.return_value = 8

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            result = manager.clear_all()

        mock_database.clear_all_cache.assert_called_once()
        assert result == 8

    def test_clear_all_returns_count(self, mock_database):
        """Should return number of deleted entries."""
        mock_database.clear_all_cache.return_value = 15

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            result = manager.clear_all()

        assert result == 15


class TestGetStatus:
    """Test cache status functionality."""

    def test_get_status_returns_counts(self, mock_database):
        """Should return cache statistics."""
        mock_database.get_cache_status.return_value = {
            'total_cached': 2,
            'valid': 1,
            'invalidated': 1,
            'caches': []
        }

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            result = manager.get_status()

        assert result['total_cached'] == 2
        assert result['valid'] == 1
        assert 'caches' in result

    def test_get_status_cache_details(self, mock_database):
        """Should return details for each cache."""
        mock_database.get_cache_status.return_value = {
            'total_cached': 1,
            'valid': 1,
            'caches': [{
                'type': 'morning_briefing',
                'key': 'abc123',
                'generated_at': datetime.now().isoformat(),
                'valid': True
            }]
        }

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            result = manager.get_status()

        assert len(result['caches']) == 1
        cache_entry = result['caches'][0]
        assert cache_entry['type'] == 'morning_briefing'


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

    def test_get_cached_handles_error(self, mock_database):
        """get_cached should return None on error."""
        mock_database.get_cached.side_effect = Exception("DB error")

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            result = manager.get_cached('morning_briefing')

        assert result is None

    def test_set_cache_handles_error(self, mock_database):
        """set_cache should not raise on error."""
        mock_database.set_cache.side_effect = Exception("DB error")

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            # Should not raise
            manager.set_cache('morning_briefing', {'data': 'test'})

    def test_invalidate_all_handles_error(self, mock_database):
        """invalidate_all should return 0 on error."""
        mock_database.invalidate_all_cache.side_effect = Exception("DB error")

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            result = manager.invalidate_all()

        assert result == 0

    def test_clear_all_handles_error(self, mock_database):
        """clear_all should return 0 on error."""
        mock_database.clear_all_cache.side_effect = Exception("DB error")

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            result = manager.clear_all()

        assert result == 0

    def test_get_status_handles_error(self, mock_database):
        """get_status should return error dict on failure."""
        mock_database.get_cache_status.side_effect = Exception("DB error")

        with patch('models.ai_analyzer.database', mock_database):
            from models.ai_analyzer import CacheManager
            manager = CacheManager()
            result = manager.get_status()

        assert 'error' in result
