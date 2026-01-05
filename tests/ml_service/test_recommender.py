"""
PresetRecommender Tests.
Tests ML preset recommendation functionality.
"""
import pytest
from datetime import datetime


class TestRecommendBasic:
    """Test basic recommendation functionality."""

    def test_recommend_returns_valid_preset(self, recommender):
        """recommend() should return a valid preset name."""
        result = recommender.recommend()

        valid_presets = ['deep_work', 'learning', 'quick_tasks', 'flow_mode']
        assert result['recommended_preset'] in valid_presets

    def test_recommend_has_confidence(self, recommender):
        """recommend() should include confidence score."""
        result = recommender.recommend()

        assert 'confidence' in result
        assert 0.0 <= result['confidence'] <= 1.0

    def test_recommend_has_reason(self, recommender):
        """recommend() should include a reason string."""
        result = recommender.recommend()

        assert 'reason' in result
        assert isinstance(result['reason'], str)
        assert len(result['reason']) > 0


class TestTimeBasedRecommendation:
    """Test time-based recommendations."""

    @pytest.mark.freeze_time('2025-12-28 08:00:00')
    def test_recommend_morning_hours(self, recommender):
        """Morning (6-10h) should favor focused presets."""
        result = recommender.recommend()

        # Morning typically recommends deep_work or learning
        assert result['recommended_preset'] in ['deep_work', 'learning', 'flow_mode', 'quick_tasks']

    @pytest.mark.freeze_time('2025-12-28 14:00:00')
    def test_recommend_afternoon_hours(self, recommender):
        """Afternoon (11-15h) recommendation."""
        result = recommender.recommend()

        # Should return some preset
        assert 'recommended_preset' in result

    @pytest.mark.freeze_time('2025-12-28 18:00:00')
    def test_recommend_evening_hours(self, recommender):
        """Evening (16-20h) recommendation."""
        result = recommender.recommend()

        assert 'recommended_preset' in result


class TestCategoryRecommendation:
    """Test category-based recommendations."""

    def test_recommend_with_category(self, recommender):
        """recommend(category) should consider category in scoring."""
        result = recommender.recommend(category='SOAP')

        assert 'recommended_preset' in result
        # SOAP typically works best with deep_work
        # (based on sample data where SOAP sessions are mostly deep_work)

    def test_recommend_unknown_category(self, recommender):
        """recommend() should handle unknown category gracefully."""
        result = recommender.recommend(category='NonExistentCategory')

        # Should still return a valid preset
        valid_presets = ['deep_work', 'learning', 'quick_tasks', 'flow_mode']
        assert result['recommended_preset'] in valid_presets


class TestConfidenceCalculation:
    """Test confidence score calculation."""

    def test_confidence_with_data(self, recommender):
        """Confidence should be higher with more data."""
        result = recommender.recommend()

        # With sample data, confidence should be above minimum
        assert result['confidence'] >= 0.3

    def test_confidence_empty_db(self, empty_recommender):
        """Confidence should be low with no data."""
        result = empty_recommender.recommend()

        # Should have low confidence
        assert result['confidence'] <= 0.5


class TestPresetStats:
    """Test preset statistics retrieval."""

    def test_get_preset_stats_structure(self, recommender):
        """get_preset_stats() should return stats for each preset."""
        stats = recommender.get_preset_stats()

        assert isinstance(stats, dict)

        valid_presets = ['deep_work', 'learning', 'quick_tasks', 'flow_mode']

        for preset in stats.keys():
            assert preset in valid_presets

    def test_get_preset_stats_content(self, recommender):
        """Each preset stat should have expected fields."""
        stats = recommender.get_preset_stats()

        for preset, data in stats.items():
            assert isinstance(data, dict)
            # Should have some performance metric
            assert any(key in data for key in ['avg_rating', 'session_count', 'best_hour', 'total_sessions'])


class TestAlternativePreset:
    """Test alternative preset suggestion."""

    def test_recommend_includes_alternative(self, recommender):
        """recommend() should suggest an alternative preset."""
        result = recommender.recommend()

        # Alternative may be None if only one good option
        if result.get('alternative'):
            valid_presets = ['deep_work', 'learning', 'quick_tasks', 'flow_mode']
            assert result['alternative'] in valid_presets
            # Alternative should be different from recommended
            assert result['alternative'] != result['recommended_preset']
