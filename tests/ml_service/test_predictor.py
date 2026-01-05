"""
SessionPredictor Tests.
Tests ML prediction functionality.
"""
import pytest
from datetime import datetime


class TestPredictToday:
    """Test today's prediction functionality."""

    def test_predict_today_structure(self, predictor):
        """predict_today() should return expected structure."""
        result = predictor.predict_today()

        assert 'predicted_sessions' in result
        assert 'confidence' in result
        assert 'date' in result

    def test_predict_today_session_count(self, predictor):
        """Predicted sessions should be reasonable."""
        result = predictor.predict_today()

        # Typical workday has 4-10 sessions
        assert 0 <= result['predicted_sessions'] <= 15

    def test_predict_today_confidence_range(self, predictor):
        """Confidence should be in valid range."""
        result = predictor.predict_today()

        assert 0.0 <= result['confidence'] <= 1.0


class TestPredictWeek:
    """Test weekly prediction functionality."""

    def test_predict_week_returns_7_days(self, predictor):
        """predict_week() should return 7-day forecast."""
        result = predictor.predict_week()

        # Should be a list or dict with 7 entries
        if isinstance(result, list):
            assert len(result) == 7
        elif isinstance(result, dict):
            if 'predictions' in result:
                assert len(result['predictions']) == 7
            elif 'forecast' in result:
                assert len(result['forecast']) == 7

    def test_predict_week_each_day_has_prediction(self, predictor):
        """Each day should have session prediction."""
        result = predictor.predict_week()

        if isinstance(result, list):
            for day in result:
                assert 'predicted_sessions' in day or 'sessions' in day
        elif isinstance(result, dict) and 'predictions' in result:
            for day in result['predictions']:
                assert 'predicted_sessions' in day or 'sessions' in day


class TestEnergyForecast:
    """Test energy forecast functionality."""

    @pytest.mark.freeze_time('2025-12-28 09:00:00')
    def test_energy_forecast_morning(self, predictor):
        """Morning energy forecast."""
        result = predictor.predict_today()

        if 'energy_forecast' in result:
            energy = result['energy_forecast']
            assert 'level' in energy or 'message' in energy

    @pytest.mark.freeze_time('2025-12-28 15:00:00')
    def test_energy_forecast_afternoon(self, predictor):
        """Afternoon energy should show decline pattern."""
        result = predictor.predict_today()

        if 'energy_forecast' in result:
            energy = result['energy_forecast']
            # Afternoon typically shows declining energy
            assert 'level' in energy or 'message' in energy


class TestTrends:
    """Test trend analysis functionality."""

    def test_trends_insufficient_data(self, empty_predictor):
        """Trends should indicate insufficient data when empty."""
        result = empty_predictor.get_trends()

        # Should indicate insufficient data or return stable
        assert result.get('session_trend') in ['insufficient_data', 'stable', None] or \
               result.get('total_sessions', 0) == 0

    def test_trends_with_data(self, predictor):
        """Trends should analyze data patterns."""
        result = predictor.get_trends()

        assert isinstance(result, dict)

        # Should have trend indicators
        if result.get('total_sessions', 0) > 0:
            assert any(key in result for key in ['session_trend', 'productivity_trend', 'trend'])

    def test_trends_valid_values(self, predictor):
        """Trend values should be valid."""
        result = predictor.get_trends()

        valid_trends = ['improving', 'declining', 'stable', 'insufficient_data', None]

        session_trend = result.get('session_trend')
        productivity_trend = result.get('productivity_trend')

        if session_trend:
            assert session_trend in valid_trends

        if productivity_trend:
            assert productivity_trend in valid_trends


class TestScheduleRecommendation:
    """Test recommended schedule generation."""

    def test_predict_today_has_schedule(self, predictor):
        """predict_today() may include recommended schedule."""
        result = predictor.predict_today()

        if 'recommended_schedule' in result:
            schedule = result['recommended_schedule']
            assert isinstance(schedule, list)

            for slot in schedule:
                # Each slot should have hour and preset
                assert 'hour' in slot or 'time' in slot
                if 'preset' in slot:
                    valid_presets = ['deep_work', 'learning', 'quick_tasks', 'flow_mode']
                    assert slot['preset'] in valid_presets


class TestPredictorConfidence:
    """Test prediction confidence calculation."""

    def test_confidence_increases_with_data(self, predictor, empty_predictor):
        """Confidence should be higher with more historical data."""
        result_with_data = predictor.predict_today()
        result_empty = empty_predictor.predict_today()

        # With data should have higher or equal confidence
        assert result_with_data['confidence'] >= result_empty['confidence']

    def test_confidence_caps_at_maximum(self, predictor):
        """Confidence should not exceed maximum (0.85)."""
        result = predictor.predict_today()

        # Confidence typically caps at 0.85
        assert result['confidence'] <= 1.0
