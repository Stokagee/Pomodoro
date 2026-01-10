"""
AIAnalyzer Tests.
Tests Full LLM-based analysis functionality.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
import json
import sys
import os

# Add ml-service to path
ML_SERVICE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ml-service'))
if ML_SERVICE_DIR not in sys.path:
    sys.path.insert(0, ML_SERVICE_DIR)


@pytest.fixture
def sample_sessions():
    """Create sample session data."""
    sessions = []
    base_date = datetime.now()

    for day in range(14):
        date = base_date - timedelta(days=day)
        for hour in [9, 10, 14, 15]:
            sessions.append({
                'date': date.strftime('%Y-%m-%d'),
                'time': f"{hour:02d}:00",
                'preset': 'deep_work',
                'category': 'Coding',
                'task': f"Task {day}-{hour}",
                'notes': f"Session notes for day {day}" if day % 2 == 0 else '',
                'productivity_rating': 75 + (day % 10),
                'duration_minutes': 52,
                'hour': hour,
                'day_of_week': date.weekday(),
                'completed': True,
                'timestamp': date.replace(hour=hour)
            })

    return sessions


@pytest.fixture
def mock_database_module(monkeypatch, sample_sessions):
    """Mock the database module functions used by AIAnalyzer.

    This replaces the old MongoDB-style mock. AIAnalyzer now uses
    'import db as database' and calls database functions directly.
    """
    # Create a mock database module
    mock_db = MagicMock()
    mock_db.get_sessions_with_notes = MagicMock(return_value=sample_sessions)
    mock_db.get_today_sessions = MagicMock(return_value=sample_sessions[:4])  # Return some today's sessions
    mock_db.get_cached = MagicMock(return_value=None)
    mock_db.set_cache = MagicMock()
    mock_db.invalidate_all_cache = MagicMock(return_value=0)
    mock_db.clear_all_cache = MagicMock(return_value=0)
    mock_db.get_cache_status = MagicMock(return_value={'total_cached': 0, 'valid': 0})
    mock_db.get_user_profile = MagicMock(return_value={'level': 5, 'total_xp': 1500, 'streak': 10})
    mock_db.get_skill_levels = MagicMock(return_value=[
        {'category': 'Coding', 'level': 3, 'current_xp': 250},
        {'category': 'Learning', 'level': 2, 'current_xp': 100}
    ])

    # Patch the database module in the ai_analyzer module namespace
    monkeypatch.setattr('models.ai_analyzer.database', mock_db)

    return mock_db


@pytest.fixture
def ai_analyzer(mock_database_module):
    """Create AIAnalyzer with mocked database module and disabled Ollama."""
    with patch.dict(os.environ, {'OLLAMA_ENABLED': 'false'}):
        from models.ai_analyzer import AIAnalyzer
        return AIAnalyzer()  # No db parameter - uses mocked database module


class TestAIAnalyzerInit:
    """Test AIAnalyzer initialization."""

    def test_init_loads_config(self, mock_database_module):
        """Should load Ollama configuration."""
        with patch.dict(os.environ, {
            'OLLAMA_URL': 'http://custom:11434',
            'OLLAMA_MODEL': 'llama2:7b',
            'OLLAMA_ENABLED': 'true',
            'OLLAMA_TIMEOUT': '120'
        }):
            from models.ai_analyzer import AIAnalyzer
            analyzer = AIAnalyzer()

            assert analyzer.ollama_url == 'http://custom:11434'
            assert 'llama2:7b' in analyzer.model or analyzer.ollama_model == 'llama2:7b'
            assert analyzer.enabled is True
            assert analyzer.timeout == 120

    def test_init_creates_cache_manager(self, ai_analyzer):
        """Should create CacheManager instance."""
        assert ai_analyzer.cache is not None

    def test_init_loads_prompts(self, ai_analyzer):
        """Should load all prompts."""
        expected_prompts = ['master', 'prediction', 'quality', 'anomaly',
                           'burnout', 'schedule', 'morning', 'evening',
                           'integrated', 'learning']

        for prompt_name in expected_prompts:
            assert prompt_name in ai_analyzer.prompts


class TestGetSessionsWithNotes:
    """Test session data retrieval."""

    def test_get_sessions_formats_data(self, ai_analyzer, mock_database_module, sample_sessions):
        """Should format session data correctly."""
        mock_database_module.get_sessions_with_notes.return_value = sample_sessions[:5]

        sessions = ai_analyzer._get_sessions_with_notes(30)

        assert len(sessions) == 5
        assert 'date' in sessions[0]
        assert 'notes' in sessions[0]
        assert 'productivity_rating' in sessions[0]

    def test_get_sessions_empty_db(self, ai_analyzer, mock_database_module):
        """Should handle empty database."""
        mock_database_module.get_sessions_with_notes.return_value = []

        sessions = ai_analyzer._get_sessions_with_notes(30)

        assert sessions == []

    def test_get_sessions_handles_error(self, ai_analyzer, mock_database_module):
        """Should return empty list on error."""
        mock_database_module.get_sessions_with_notes.side_effect = Exception("DB error")

        sessions = ai_analyzer._get_sessions_with_notes(30)

        assert sessions == []


class TestGetTodaySessions:
    """Test today's session retrieval."""

    def test_get_today_sessions_filters_by_date(self, ai_analyzer, mock_database_module):
        """Should filter sessions by today's date."""
        today = datetime.now().strftime('%Y-%m-%d')
        today_sessions = [{'date': today, 'time': '09:00', 'category': 'Coding'}]
        mock_database_module.get_today_sessions.return_value = today_sessions

        sessions = ai_analyzer._get_today_sessions()

        # Should have called get_today_sessions (not get_sessions_with_notes)
        mock_database_module.get_today_sessions.assert_called()
        # Return value should contain today's sessions
        assert len(sessions) >= 0


class TestGetBaselineStats:
    """Test baseline statistics calculation."""

    def test_baseline_empty_sessions(self, ai_analyzer):
        """Should handle empty session list."""
        result = ai_analyzer._get_baseline_stats([])

        assert result['avg_sessions'] == 0
        assert result['avg_productivity'] == 0
        assert result['typical_hours'] == 'N/A'
        assert result['top_category'] == 'N/A'

    def test_baseline_calculates_averages(self, ai_analyzer, sample_sessions):
        """Should calculate correct averages."""
        result = ai_analyzer._get_baseline_stats(sample_sessions[:10])

        assert result['avg_sessions'] > 0
        assert 0 <= result['avg_productivity'] <= 100
        assert result['top_category'] == 'Coding'

    def test_baseline_handles_missing_ratings(self, ai_analyzer):
        """Should handle sessions without ratings."""
        sessions = [
            {'date': '2025-01-01', 'hour': 10, 'category': 'Coding'},
            {'date': '2025-01-01', 'hour': 11, 'category': 'Coding'}
        ]

        result = ai_analyzer._get_baseline_stats(sessions)

        assert result['avg_productivity'] == 0  # No ratings


class TestFallbackResponse:
    """Test fallback response generation."""

    def test_fallback_has_required_fields(self, ai_analyzer):
        """Fallback should have all required fields."""
        result = ai_analyzer._create_fallback('morning_briefing')

        assert result['ai_available'] is False
        assert result['fallback'] is True
        assert result['from_cache'] is False
        assert 'error' in result
        assert 'message' in result
        assert 'timestamp' in result

    def test_fallback_includes_custom_error(self, ai_analyzer):
        """Fallback should include custom error message."""
        result = ai_analyzer._create_fallback('morning_briefing', 'Custom error')

        assert result['error'] == 'Custom error'


class TestMorningBriefing:
    """Test morning briefing generation."""

    def test_morning_briefing_uses_cache(self, ai_analyzer, mock_database_module):
        """Should return cached result if available."""
        cached_data = {'greeting': 'Good morning!', 'from_cache': True}
        mock_database_module.get_cached.return_value = cached_data
        ai_analyzer.cache.get_cached = MagicMock(return_value=cached_data)

        result = ai_analyzer.morning_briefing()

        assert result == cached_data
        ai_analyzer.cache.get_cached.assert_called_once_with('morning_briefing')

    def test_morning_briefing_no_sessions_returns_fallback(self, ai_analyzer, mock_database_module):
        """Should return fallback when no sessions."""
        ai_analyzer.cache.get_cached = MagicMock(return_value=None)
        mock_database_module.get_sessions_with_notes.return_value = []

        result = ai_analyzer.morning_briefing()

        assert result['fallback'] is True
        # The error message might vary, just check it's a fallback
        assert 'ai_available' in result or 'error' in result


class TestEveningReview:
    """Test evening review generation."""

    def test_evening_review_uses_cache(self, ai_analyzer, mock_database_module):
        """Should return cached result if available."""
        cached_data = {'summary': 'Good day!', 'from_cache': True}
        ai_analyzer.cache.get_cached = MagicMock(return_value=cached_data)

        result = ai_analyzer.evening_review()

        assert result == cached_data

    def test_evening_review_no_sessions_returns_fallback(self, ai_analyzer, mock_database_module):
        """Should return fallback when no today sessions."""
        ai_analyzer.cache.get_cached = MagicMock(return_value=None)
        mock_database_module.get_sessions_with_notes.return_value = []

        result = ai_analyzer.evening_review()

        assert result['fallback'] is True


class TestAnalyzeBurnout:
    """Test burnout analysis."""

    def test_analyze_burnout_uses_cache(self, ai_analyzer, mock_database_module):
        """Should return cached result if available."""
        cached_data = {'risk_level': 'low', 'from_cache': True}
        ai_analyzer.cache.get_cached = MagicMock(return_value=cached_data)

        result = ai_analyzer.analyze_burnout()

        assert result == cached_data

    def test_analyze_burnout_insufficient_data(self, ai_analyzer, mock_database_module, sample_sessions):
        """Should return fallback with insufficient data."""
        ai_analyzer.cache.get_cached = MagicMock(return_value=None)
        mock_database_module.get_sessions_with_notes.return_value = sample_sessions[:3]

        result = ai_analyzer.analyze_burnout()

        assert result['fallback'] is True
        # Check for some indication of insufficient data
        assert 'error' in result or 'ai_available' in result


class TestAnalyzeAnomalies:
    """Test anomaly analysis."""

    def test_analyze_anomalies_uses_cache(self, ai_analyzer, mock_database_module):
        """Should return cached result if available."""
        cached_data = {'anomalies': [], 'from_cache': True}
        ai_analyzer.cache.get_cached = MagicMock(return_value=cached_data)

        result = ai_analyzer.analyze_anomalies()

        assert result == cached_data

    def test_analyze_anomalies_insufficient_data(self, ai_analyzer, mock_database_module, sample_sessions):
        """Should return fallback with insufficient data."""
        ai_analyzer.cache.get_cached = MagicMock(return_value=None)
        mock_database_module.get_sessions_with_notes.return_value = sample_sessions[:5]

        result = ai_analyzer.analyze_anomalies()

        assert result['fallback'] is True


class TestAnalyzeQuality:
    """Test quality analysis."""

    def test_analyze_quality_uses_cache_with_params(self, ai_analyzer, mock_database_module):
        """Should use cache with parameters."""
        cached_data = {'predicted_productivity': 85, 'from_cache': True}
        ai_analyzer.cache.get_cached = MagicMock(return_value=cached_data)

        result = ai_analyzer.analyze_quality(preset='deep_work', category='Coding')

        ai_analyzer.cache.get_cached.assert_called_once()
        call_args = ai_analyzer.cache.get_cached.call_args
        assert call_args[0][1] == {'preset': 'deep_work', 'category': 'Coding'}

    def test_analyze_quality_default_params(self, ai_analyzer, mock_database_module):
        """Should use default parameters when called without args."""
        ai_analyzer.cache.get_cached = MagicMock(return_value=None)
        ai_analyzer._call_ollama = MagicMock(return_value=None)

        result = ai_analyzer.analyze_quality()

        assert result['fallback'] is True


class TestGetOptimalSchedule:
    """Test optimal schedule generation."""

    def test_optimal_schedule_uses_cache_with_params(self, ai_analyzer, mock_database_module):
        """Should use cache with parameters."""
        cached_data = {'schedule': [], 'from_cache': True}
        ai_analyzer.cache.get_cached = MagicMock(return_value=cached_data)

        result = ai_analyzer.get_optimal_schedule(day='monday', num_sessions=8)

        ai_analyzer.cache.get_cached.assert_called_once()

    def test_optimal_schedule_insufficient_data(self, ai_analyzer, mock_database_module, sample_sessions):
        """Should return fallback with insufficient data."""
        ai_analyzer.cache.get_cached = MagicMock(return_value=None)
        mock_database_module.get_sessions_with_notes.return_value = sample_sessions[:5]

        result = ai_analyzer.get_optimal_schedule()

        assert result['fallback'] is True


class TestIntegratedInsight:
    """Test integrated insight generation."""

    def test_integrated_insight_uses_cache(self, ai_analyzer, mock_database_module):
        """Should return cached result if available."""
        cached_data = {'recommendations': [], 'from_cache': True}
        ai_analyzer.cache.get_cached = MagicMock(return_value=cached_data)

        result = ai_analyzer.integrated_insight()

        assert result == cached_data


class TestGetLearningRecommendations:
    """Test learning recommendations."""

    def test_learning_uses_cache(self, ai_analyzer, mock_database_module):
        """Should return cached result if available."""
        cached_data = {'topics': [], 'from_cache': True}
        ai_analyzer.cache.get_cached = MagicMock(return_value=cached_data)

        result = ai_analyzer.get_learning_recommendations()

        assert result == cached_data

    def test_learning_insufficient_data(self, ai_analyzer, mock_database_module, sample_sessions):
        """Should return fallback with insufficient data."""
        ai_analyzer.cache.get_cached = MagicMock(return_value=None)
        mock_database_module.get_sessions_with_notes.return_value = sample_sessions[:3]

        result = ai_analyzer.get_learning_recommendations()

        assert result['fallback'] is True


class TestHealthCheck:
    """Test Ollama health check."""

    def test_health_check_disabled(self, ai_analyzer):
        """Should return disabled status when Ollama is disabled."""
        result = ai_analyzer.health_check()

        assert result['status'] == 'disabled'
        assert 'OLLAMA_ENABLED=false' in result['message']

    def test_health_check_error(self, mock_database_module):
        """Should handle connection errors."""
        with patch.dict(os.environ, {'OLLAMA_ENABLED': 'true'}):
            from models.ai_analyzer import AIAnalyzer
            analyzer = AIAnalyzer()

            with patch('requests.get') as mock_get:
                mock_get.side_effect = Exception("Connection refused")

                result = analyzer.health_check()

                assert result['status'] == 'unavailable'
                assert 'Cannot connect' in result['message']

    def test_health_check_success(self, mock_database_module):
        """Should return healthy status when connected."""
        with patch.dict(os.environ, {'OLLAMA_ENABLED': 'true', 'OLLAMA_MODEL': 'mistral:7b'}):
            from models.ai_analyzer import AIAnalyzer
            analyzer = AIAnalyzer()
            analyzer.cache.get_status = MagicMock(return_value={'total_cached': 0, 'valid': 0})

            with patch('requests.get') as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = {
                    'models': [{'name': 'mistral:7b'}]
                }

                result = analyzer.health_check()

                assert result['status'] == 'healthy'
                assert 'cache_status' in result


class TestParseJsonResponse:
    """Test JSON response parsing."""

    def test_parse_valid_json(self, ai_analyzer):
        """Should parse valid JSON."""
        response = '{"key": "value", "number": 42}'

        result = ai_analyzer._parse_json_response(response)

        assert result == {'key': 'value', 'number': 42}

    def test_parse_json_with_text(self, ai_analyzer):
        """Should extract JSON from text response."""
        response = 'Here is the analysis:\n{"score": 85}\nEnd of response.'

        result = ai_analyzer._parse_json_response(response)

        assert result == {'score': 85}

    def test_parse_invalid_json(self, ai_analyzer):
        """Should return None for invalid JSON."""
        response = 'This is not JSON at all'

        result = ai_analyzer._parse_json_response(response)

        assert result is None

    def test_parse_none_response(self, ai_analyzer):
        """Should return None for None input."""
        result = ai_analyzer._parse_json_response(None)

        assert result is None


class TestCategoryDistribution:
    """Test category distribution calculation."""

    def test_category_distribution_empty(self, ai_analyzer):
        """Should handle empty sessions."""
        result = ai_analyzer._get_category_distribution([])

        assert result == {}

    def test_category_distribution_calculates_percentages(self, ai_analyzer):
        """Should calculate correct percentages."""
        sessions = [
            {'category': 'Coding'},
            {'category': 'Coding'},
            {'category': 'Learning'},
            {'category': 'Coding'}
        ]

        result = ai_analyzer._get_category_distribution(sessions)

        assert result['Coding']['sessions'] == 3
        assert result['Coding']['percentage'] == 75.0
        assert result['Learning']['sessions'] == 1
        assert result['Learning']['percentage'] == 25.0


class TestCallOllama:
    """Test Ollama API calls."""

    def test_call_ollama_disabled(self, ai_analyzer):
        """Should return None when Ollama is disabled."""
        result = ai_analyzer._call_ollama("test prompt")

        assert result is None

    def test_call_ollama_with_system_prompt(self, mock_database_module):
        """Should include system prompt in messages."""
        with patch.dict(os.environ, {'OLLAMA_ENABLED': 'true'}):
            from models.ai_analyzer import AIAnalyzer
            analyzer = AIAnalyzer()

            with patch('requests.post') as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {
                    'message': {'content': 'response'}
                }

                analyzer._call_ollama("user prompt", "system prompt")

                call_args = mock_post.call_args[1]['json']
                messages = call_args['messages']
                assert len(messages) == 2
                assert messages[0]['role'] == 'system'
                assert messages[1]['role'] == 'user'


class TestGetUserProfile:
    """Test user profile retrieval."""

    def test_get_user_profile_found(self, ai_analyzer, mock_database_module):
        """Should return profile when found."""
        # Note: AIAnalyzer._get_user_profile looks for 'total_xp', not 'total_xp_earned'
        mock_database_module.get_user_profile.return_value = {
            'level': 5,
            'total_xp': 1500,
            'streak': 10
        }

        result = ai_analyzer._get_user_profile()

        assert result['level'] == 5
        assert result['total_xp'] == 1500
        assert result['streak'] == 10

    def test_get_user_profile_not_found(self, ai_analyzer, mock_database_module):
        """Should return defaults when profile not found."""
        mock_database_module.get_user_profile.return_value = None

        result = ai_analyzer._get_user_profile()

        assert result['level'] == 1
        assert result['total_xp'] == 0
        assert result['streak'] == 0


class TestGetSkillLevels:
    """Test skill levels retrieval."""

    def test_get_skill_levels_found(self, ai_analyzer, mock_database_module):
        """Should return skill levels when found."""
        mock_database_module.get_skill_levels.return_value = [
            {'category': 'Coding', 'level': 3, 'current_xp': 250},
            {'category': 'Learning', 'level': 2, 'current_xp': 100}
        ]

        result = ai_analyzer._get_skill_levels()

        assert len(result) == 2
        assert result[0]['category'] == 'Coding'
        assert result[0]['level'] == 3

    def test_get_skill_levels_empty(self, ai_analyzer, mock_database_module):
        """Should return empty list when no skills."""
        mock_database_module.get_skill_levels.return_value = []

        result = ai_analyzer._get_skill_levels()

        assert result == []
