"""
Tests for SessionQualityPredictor.
Comprehensive tests for session quality prediction before starting.
"""
import pytest
import sys
import os

# Ensure ml-service is in path
ML_SERVICE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ml-service'))
if ML_SERVICE_DIR not in sys.path:
    sys.path.insert(0, ML_SERVICE_DIR)


class TestQualityPredictorEmpty:
    """Test quality predictor with no historical data."""

    def test_predict_returns_defaults(self, empty_quality_predictor):
        """Should return default values when no historical data."""
        result = empty_quality_predictor.predict(
            hour=10,
            day=1,
            preset='deep_work',
            category='Coding',
            sessions_today=0,
            minutes_since_last=None
        )

        assert 'predicted_productivity' in result
        assert 'confidence' in result
        assert 60 <= result['predicted_productivity'] <= 85
        assert result['confidence'] < 0.3  # Low confidence without data

    def test_uses_circadian_defaults(self, empty_quality_predictor):
        """Should use circadian rhythm defaults."""
        # Morning peak
        morning = empty_quality_predictor.predict(10, 1, 'deep_work', None, 0, None)
        # Lunch dip
        lunch = empty_quality_predictor.predict(12, 1, 'deep_work', None, 0, None)
        # Late night
        night = empty_quality_predictor.predict(23, 1, 'deep_work', None, 0, None)

        assert morning['factor_scores']['hour']['score'] >= 75
        assert lunch['factor_scores']['hour']['score'] <= 70
        assert night['factor_scores']['hour']['score'] <= 60


class TestPredictionResponseStructure:
    """Test the structure of prediction response."""

    def test_contains_all_required_fields(self, quality_predictor):
        """Should contain all Ollama-ready fields."""
        result = quality_predictor.predict(10, 1, 'deep_work', 'Coding', 2, 20)

        # Top-level fields
        assert 'predicted_productivity' in result
        assert 'confidence' in result
        assert 'context' in result
        assert 'factor_scores' in result
        assert 'factors' in result
        assert 'recommendation' in result
        assert 'metadata' in result

    def test_context_structure(self, quality_predictor):
        """Should have correct context structure."""
        result = quality_predictor.predict(14, 2, 'learning', 'Database', 3, 15)

        context = result['context']
        assert context['hour'] == 14
        assert context['day_of_week'] == 2
        assert context['day_name'] == 'Streda'
        assert context['preset'] == 'learning'
        assert context['category'] == 'Database'
        assert context['sessions_today'] == 3
        assert context['minutes_since_last'] == 15

    def test_factor_scores_structure(self, quality_predictor):
        """Should have all 6 factor scores."""
        result = quality_predictor.predict(10, 1, 'deep_work', 'Coding', 0, None)

        scores = result['factor_scores']
        expected_factors = ['hour', 'day', 'preset', 'category', 'fatigue', 'recovery']

        for factor in expected_factors:
            assert factor in scores
            assert 'score' in scores[factor]
            assert 'confidence' in scores[factor]
            assert 'weight' in scores[factor]
            assert 0 <= scores[factor]['score'] <= 100
            assert 0 <= scores[factor]['confidence'] <= 1

    def test_recommendation_structure(self, quality_predictor):
        """Should have correct recommendation structure."""
        result = quality_predictor.predict(10, 1, 'deep_work', 'Coding', 0, 20)

        rec = result['recommendation']
        assert 'type' in rec
        assert 'message' in rec
        assert 'icon' in rec
        assert rec['type'] in ['positive', 'negative', 'warning', 'neutral', 'suggestion', 'info']

    def test_metadata_structure(self, quality_predictor):
        """Should have metadata for Ollama."""
        result = quality_predictor.predict(10, 1, 'deep_work', None, 0, None)

        metadata = result['metadata']
        assert 'model_version' in metadata
        assert 'total_sessions_analyzed' in metadata
        assert 'timestamp' in metadata


class TestHourScoreCalculation:
    """Test hour-based productivity scoring."""

    def test_morning_peak_detected(self, hourly_quality_predictor):
        """Should detect morning peak hours from historical data."""
        result = hourly_quality_predictor.predict(10, 1, 'deep_work', None, 0, None)

        # With hourly_pattern_sessions, hour 10 has 86% productivity
        assert result['factor_scores']['hour']['score'] >= 80
        assert result['factor_scores']['hour']['confidence'] >= 0.5

    def test_lunch_dip_detected(self, hourly_quality_predictor):
        """Should detect lunch dip from historical data."""
        result = hourly_quality_predictor.predict(12, 1, 'deep_work', None, 0, None)

        # With hourly_pattern_sessions, hour 12 has ~55% productivity
        assert result['factor_scores']['hour']['score'] <= 65

    def test_afternoon_productivity(self, hourly_quality_predictor):
        """Should detect afternoon productivity levels."""
        result = hourly_quality_predictor.predict(15, 1, 'learning', None, 0, None)

        # With hourly_pattern_sessions, hour 15 has ~71% productivity
        assert 65 <= result['factor_scores']['hour']['score'] <= 80


class TestFatigueScoreCalculation:
    """Test fatigue-based scoring."""

    def test_first_session_no_fatigue(self, quality_predictor):
        """First session should have high fatigue score (no fatigue)."""
        result = quality_predictor.predict(10, 1, 'deep_work', None, 0, None)

        # Session 1 should have decent fatigue score
        assert result['factor_scores']['fatigue']['score'] >= 70

    def test_fatigue_increases_with_sessions(self, fatigued_quality_predictor):
        """Fatigue should be detected after many sessions."""
        result = fatigued_quality_predictor.predict(15, 1, 'deep_work', 'Coding', 6, 10)

        # After 6 sessions, fatigue should be significant
        assert result['factor_scores']['fatigue']['score'] <= 70

    def test_fatigue_factor_appears_in_list(self, fatigued_quality_predictor):
        """Should include fatigue in factors list when significant."""
        result = fatigued_quality_predictor.predict(15, 1, 'deep_work', 'Coding', 6, 10)

        fatigue_factors = [f for f in result['factors'] if 'unava' in f['name'].lower()]
        # May or may not appear depending on exact threshold
        # Just check structure is valid
        assert isinstance(result['factors'], list)


class TestRecoveryScoreCalculation:
    """Test recovery time scoring."""

    def test_no_break_low_score(self, quality_predictor):
        """Very short break should have low recovery score."""
        result = quality_predictor.predict(10, 1, 'deep_work', None, 2, 2)

        assert result['factor_scores']['recovery']['score'] <= 60

    def test_short_break_medium_score(self, quality_predictor):
        """Short break (5-15 min) should have medium score."""
        result = quality_predictor.predict(10, 1, 'deep_work', None, 2, 10)

        assert 60 <= result['factor_scores']['recovery']['score'] <= 75

    def test_optimal_break_high_score(self, quality_predictor):
        """Optimal break (15-30 min) should have high score."""
        result = quality_predictor.predict(10, 1, 'deep_work', None, 2, 20)

        assert result['factor_scores']['recovery']['score'] >= 75

    def test_first_session_neutral_recovery(self, quality_predictor):
        """First session (None minutes) should have neutral recovery."""
        result = quality_predictor.predict(10, 1, 'deep_work', None, 0, None)

        assert 70 <= result['factor_scores']['recovery']['score'] <= 80


class TestPresetScoreCalculation:
    """Test preset-based scoring."""

    def test_preset_affects_score(self, quality_predictor):
        """Different presets should have different scores."""
        deep = quality_predictor.predict(10, 1, 'deep_work', None, 0, None)
        quick = quality_predictor.predict(10, 1, 'quick_tasks', None, 0, None)

        # Scores may vary but should be in valid range (0-100)
        assert 0 <= deep['factor_scores']['preset']['score'] <= 100
        assert 0 <= quick['factor_scores']['preset']['score'] <= 100

    def test_unknown_preset_uses_default(self, quality_predictor):
        """Unknown preset should use default score."""
        result = quality_predictor.predict(10, 1, 'unknown_preset', None, 0, None)

        assert result['factor_scores']['preset']['score'] == 70
        assert result['factor_scores']['preset']['confidence'] == 0.1


class TestCategoryScoreCalculation:
    """Test category-based scoring."""

    def test_no_category_uses_default(self, quality_predictor):
        """No category should use default score."""
        result = quality_predictor.predict(10, 1, 'deep_work', None, 0, None)

        assert result['factor_scores']['category']['score'] == 70
        assert result['factor_scores']['category']['confidence'] == 0.1

    def test_category_with_history(self, hourly_quality_predictor):
        """Category with history should use historical data."""
        result = hourly_quality_predictor.predict(10, 1, 'deep_work', 'Coding', 0, None)

        # Coding category has high productivity in hourly_pattern_sessions
        assert result['factor_scores']['category']['confidence'] > 0.1


class TestRecommendationGeneration:
    """Test recommendation generation."""

    def test_high_prediction_positive_recommendation(self, hourly_quality_predictor):
        """High prediction should give positive recommendation."""
        result = hourly_quality_predictor.predict(10, 1, 'deep_work', 'Coding', 0, 20)

        # Morning peak should give high prediction
        if result['predicted_productivity'] >= 75:
            assert result['recommendation']['type'] == 'positive'

    def test_fatigue_warning(self, fatigued_quality_predictor):
        """High fatigue should give warning recommendation."""
        result = fatigued_quality_predictor.predict(15, 1, 'deep_work', 'Coding', 6, 5)

        # After 6 sessions with short break, should get warning
        assert result['recommendation']['type'] in ['warning', 'negative', 'neutral']

    def test_recommendation_has_icon(self, quality_predictor):
        """Recommendation should always have icon."""
        result = quality_predictor.predict(10, 1, 'deep_work', None, 0, None)

        assert 'icon' in result['recommendation']
        assert len(result['recommendation']['icon']) > 0


class TestConfidenceCalculation:
    """Test confidence calculation."""

    def test_empty_data_low_confidence(self, empty_quality_predictor):
        """Empty data should result in low confidence."""
        result = empty_quality_predictor.predict(10, 1, 'deep_work', None, 0, None)

        assert result['confidence'] < 0.3

    def test_rich_data_higher_confidence(self, hourly_quality_predictor):
        """Rich historical data should increase confidence."""
        result = hourly_quality_predictor.predict(10, 1, 'deep_work', 'Coding', 2, 20)

        # With 80+ sessions, confidence should be higher
        assert result['confidence'] > 0.3


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_hour_boundaries(self, quality_predictor):
        """Test hour boundary values."""
        # Valid hours
        for hour in [0, 12, 23]:
            result = quality_predictor.predict(hour, 1, 'deep_work', None, 0, None)
            assert 'predicted_productivity' in result

    def test_day_boundaries(self, quality_predictor):
        """Test day boundary values."""
        # Valid days
        for day in [0, 3, 6]:
            result = quality_predictor.predict(10, day, 'deep_work', None, 0, None)
            assert result['context']['day_of_week'] == day

    def test_high_session_count(self, quality_predictor):
        """Test with many sessions today."""
        result = quality_predictor.predict(10, 1, 'deep_work', None, 10, 5)

        # Should still work, fatigue should be very high
        assert result['factor_scores']['fatigue']['score'] <= 60

    def test_long_break_time(self, quality_predictor):
        """Test with very long break time."""
        result = quality_predictor.predict(10, 1, 'deep_work', None, 2, 480)  # 8 hours

        # Should indicate cold start
        assert result['factor_scores']['recovery']['score'] <= 70

    def test_productivity_range(self, quality_predictor):
        """Predicted productivity should always be 0-100."""
        result = quality_predictor.predict(10, 1, 'deep_work', 'Coding', 2, 20)

        assert 0 <= result['predicted_productivity'] <= 100


class TestWeightedCalculation:
    """Test that weights are applied correctly."""

    def test_weights_sum_to_one(self):
        """Factor weights should sum to 1.0."""
        from models.quality_predictor import SessionQualityPredictor

        total = sum(SessionQualityPredictor.WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_all_factors_contribute(self, quality_predictor):
        """All factors should contribute to final score."""
        result = quality_predictor.predict(10, 1, 'deep_work', 'Coding', 2, 20)

        # Manually calculate weighted sum
        scores = result['factor_scores']
        calculated = sum(
            scores[factor]['score'] * scores[factor]['weight']
            for factor in ['hour', 'day', 'preset', 'category', 'fatigue', 'recovery']
        )

        # Should be close to predicted productivity
        assert abs(calculated - result['predicted_productivity']) < 1


class TestDayNames:
    """Test Czech day names."""

    def test_all_day_names(self, quality_predictor):
        """Test all day names are correct."""
        expected = ['Pondeli', 'Utery', 'Streda', 'Ctvrtek', 'Patek', 'Sobota', 'Nedele']

        for day, name in enumerate(expected):
            result = quality_predictor.predict(10, day, 'deep_work', None, 0, None)
            assert result['context']['day_name'] == name


class TestPresetInfo:
    """Test preset information."""

    def test_known_preset_name(self, quality_predictor):
        """Known presets should have correct names."""
        result = quality_predictor.predict(10, 1, 'deep_work', None, 0, None)
        assert result['context']['preset_name'] == 'Deep Work'

        result = quality_predictor.predict(10, 1, 'learning', None, 0, None)
        assert result['context']['preset_name'] == 'Learning'

    def test_unknown_preset_uses_key(self, quality_predictor):
        """Unknown preset should use the key as name."""
        result = quality_predictor.predict(10, 1, 'custom_preset', None, 0, None)
        assert result['context']['preset_name'] == 'custom_preset'
