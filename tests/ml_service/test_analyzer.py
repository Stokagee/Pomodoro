"""
ProductivityAnalyzer Tests.
Tests ML analysis functionality.
"""
import pytest
from datetime import datetime


class TestAnalyzeEmpty:
    """Test analyzer with empty data."""

    def test_analyze_empty_sessions(self, empty_analyzer):
        """analyze() should handle empty session list."""
        result = empty_analyzer.analyze()

        assert result['total_sessions_analyzed'] == 0
        assert result['best_hours'] == []
        assert result['trend'] == 'stable'


class TestBestHours:
    """Test best hours calculation."""

    def test_get_best_hours_returns_top3(self, analyzer):
        """_get_best_hours() should return top 3 most productive hours."""
        result = analyzer.analyze()

        best_hours = result.get('best_hours', [])

        # Should return list of hours
        assert isinstance(best_hours, list)

        # Should have at most 3 hours
        assert len(best_hours) <= 3

        # Hours should be valid (0-23)
        for hour in best_hours:
            assert 0 <= hour <= 23

    def test_get_worst_hours_returns_bottom3(self, analyzer):
        """_get_worst_hours() should return 3 least productive hours."""
        result = analyzer.analyze()

        worst_hours = result.get('worst_hours', [])

        assert isinstance(worst_hours, list)
        assert len(worst_hours) <= 3

        for hour in worst_hours:
            assert 0 <= hour <= 23


class TestBestDay:
    """Test best day calculation."""

    def test_get_best_day_calculation(self, analyzer):
        """_get_best_day() should return the most productive day."""
        result = analyzer.analyze()

        best_day = result.get('best_day')

        # Should be a day name or None
        valid_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday', None]
        assert best_day in valid_days


class TestProductivityByCategory:
    """Test category productivity analysis."""

    def test_productivity_by_category(self, analyzer):
        """analyze() should calculate productivity by category."""
        result = analyzer.analyze()

        by_category = result.get('productivity_by_category', {})

        assert isinstance(by_category, dict)

        # Each category should have avg_rating and session_count
        for category, data in by_category.items():
            assert 'avg_rating' in data or isinstance(data, (int, float))
            if isinstance(data, dict):
                assert 'session_count' in data


class TestProductivityByPreset:
    """Test preset productivity analysis."""

    def test_productivity_by_preset(self, analyzer):
        """analyze() should calculate productivity by preset."""
        result = analyzer.analyze()

        by_preset = result.get('productivity_by_preset', {})

        assert isinstance(by_preset, dict)

        # Valid preset names
        valid_presets = ['deep_work', 'learning', 'quick_tasks', 'flow_mode']

        for preset in by_preset.keys():
            assert preset in valid_presets


class TestTrendDetection:
    """Test productivity trend detection."""

    def test_trend_returns_valid_value(self, analyzer):
        """_get_trend() should return up, down, or stable."""
        result = analyzer.analyze()

        trend = result.get('trend')

        assert trend in ['up', 'down', 'stable']

    def test_trend_stable_with_insufficient_data(self, empty_analyzer):
        """Trend should be stable with insufficient data."""
        result = empty_analyzer.analyze()

        assert result['trend'] == 'stable'


class TestHourlyHeatmap:
    """Test hourly heatmap generation."""

    def test_hourly_heatmap_structure(self, analyzer):
        """get_hourly_heatmap() should return 24x7 structure."""
        heatmap = analyzer.get_hourly_heatmap()

        assert isinstance(heatmap, dict)

        # Should have 7 days
        valid_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        for day in valid_days:
            if day in heatmap:
                assert isinstance(heatmap[day], dict)

                # Each hour should have sessions and avg_rating
                for hour_str, data in heatmap[day].items():
                    assert isinstance(data, dict)
                    assert 'sessions' in data or 'avg_rating' in data


class TestAnalysisCompleteness:
    """Test that analysis returns all expected fields."""

    def test_analysis_has_all_fields(self, analyzer):
        """analyze() should return all expected fields."""
        result = analyzer.analyze()

        expected_fields = [
            'best_hours',
            'worst_hours',
            'best_day',
            'productivity_by_hour',
            'productivity_by_day',
            'productivity_by_category',
            'productivity_by_preset',
            'trend',
            'total_sessions_analyzed'
        ]

        for field in expected_fields:
            assert field in result, f"Missing field: {field}"

    def test_productivity_by_hour_range(self, analyzer):
        """productivity_by_hour should have valid hour keys."""
        result = analyzer.analyze()

        by_hour = result.get('productivity_by_hour', {})

        for hour_key in by_hour.keys():
            hour = int(hour_key) if isinstance(hour_key, str) else hour_key
            assert 0 <= hour <= 23

    def test_rating_values_in_range(self, analyzer):
        """All ratings should be between 0 and 5."""
        result = analyzer.analyze()

        # Check category ratings
        for category, data in result.get('productivity_by_category', {}).items():
            if isinstance(data, dict) and 'avg_rating' in data:
                assert 0 <= data['avg_rating'] <= 5

        # Check preset ratings
        for preset, data in result.get('productivity_by_preset', {}).items():
            if isinstance(data, dict) and 'avg_rating' in data:
                assert 0 <= data['avg_rating'] <= 5
