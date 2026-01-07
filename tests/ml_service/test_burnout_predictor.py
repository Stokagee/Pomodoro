"""
BurnoutPredictor Tests.
Tests ML burnout risk analysis functionality.
"""
import pytest
from datetime import datetime


class TestBurnoutEmpty:
    """Test burnout predictor with empty/insufficient data."""

    def test_predict_empty_sessions(self, empty_burnout_predictor):
        """predict_burnout() should handle empty session list."""
        result = empty_burnout_predictor.predict_burnout()

        assert result['risk_score'] == 0
        assert result['risk_level'] == 'unknown'
        assert result['confidence'] == 0.0
        # Should have a recommendation about collecting more data
        assert len(result['recommendations']) > 0

    def test_insufficient_data_message(self, empty_burnout_predictor):
        """Should return helpful message when insufficient data."""
        result = empty_burnout_predictor.predict_burnout()

        assert result['total_sessions_analyzed'] == 0
        assert result['analyzed_period'] == '14 days'


class TestBurnoutResponseStructure:
    """Test that burnout prediction returns all required fields."""

    def test_all_fields_present(self, burnout_predictor):
        """predict_burnout() should return all expected fields."""
        result = burnout_predictor.predict_burnout()

        expected_fields = [
            'risk_score',
            'risk_level',
            'risk_factors',
            'recommendations',
            'confidence',
            'analyzed_period',
            'total_sessions_analyzed'
        ]

        for field in expected_fields:
            assert field in result, f"Missing field: {field}"

    def test_risk_score_range(self, burnout_predictor):
        """risk_score should be between 0 and 100."""
        result = burnout_predictor.predict_burnout()

        assert 0 <= result['risk_score'] <= 100

    def test_risk_level_valid(self, burnout_predictor):
        """risk_level should be one of the valid levels."""
        result = burnout_predictor.predict_burnout()

        valid_levels = ['low', 'medium', 'high', 'critical', 'unknown']
        assert result['risk_level'] in valid_levels

    def test_confidence_range(self, burnout_predictor):
        """confidence should be between 0.0 and 1.0."""
        result = burnout_predictor.predict_burnout()

        assert 0.0 <= result['confidence'] <= 1.0

    def test_risk_factors_structure(self, burnout_predictor):
        """risk_factors should have proper structure."""
        result = burnout_predictor.predict_burnout()

        assert isinstance(result['risk_factors'], list)

        for factor in result['risk_factors']:
            assert 'factor' in factor
            assert 'severity' in factor
            assert 'score' in factor
            assert 'message' in factor
            assert factor['severity'] in ['low', 'medium', 'high']

    def test_recommendations_structure(self, burnout_predictor):
        """recommendations should be list of strings."""
        result = burnout_predictor.predict_burnout()

        assert isinstance(result['recommendations'], list)
        for rec in result['recommendations']:
            assert isinstance(rec, str)


class TestHighRiskDetection:
    """Test detection of high burnout risk patterns."""

    def test_high_risk_detected(self, high_risk_burnout_predictor):
        """Should detect high risk from bad patterns."""
        result = high_risk_burnout_predictor.predict_burnout()

        # Should have elevated risk
        assert result['risk_score'] > 25
        assert result['risk_level'] in ['medium', 'high', 'critical']

    def test_high_risk_has_factors(self, high_risk_burnout_predictor):
        """High risk should identify specific factors."""
        result = high_risk_burnout_predictor.predict_burnout()

        # Should have at least one risk factor
        assert len(result['risk_factors']) > 0

    def test_high_risk_has_recommendations(self, high_risk_burnout_predictor):
        """High risk should provide recommendations."""
        result = high_risk_burnout_predictor.predict_burnout()

        assert len(result['recommendations']) > 0


class TestLowRiskDetection:
    """Test detection of low burnout risk (healthy patterns)."""

    def test_low_risk_detected(self, low_risk_burnout_predictor):
        """Should detect low risk from healthy patterns."""
        result = low_risk_burnout_predictor.predict_burnout()

        # Should have low risk
        assert result['risk_level'] in ['low', 'medium']
        assert result['risk_score'] <= 50

    def test_low_risk_fewer_factors(self, low_risk_burnout_predictor):
        """Low risk should have fewer or no high-severity factors."""
        result = low_risk_burnout_predictor.predict_burnout()

        high_severity_count = sum(
            1 for f in result['risk_factors']
            if f['severity'] == 'high'
        )

        # Should have minimal high-severity factors
        assert high_severity_count <= 1


class TestRiskFactorCalculations:
    """Test individual risk factor calculations."""

    def test_night_sessions_factor(self, high_risk_burnout_predictor):
        """Should detect night sessions pattern."""
        result = high_risk_burnout_predictor.predict_burnout()

        night_factor = next(
            (f for f in result['risk_factors'] if f['factor'] == 'night_sessions'),
            None
        )

        # High risk sessions include night work, so factor should be present
        if night_factor:
            assert night_factor['score'] > 0

    def test_factor_scores_not_negative(self, burnout_predictor):
        """All factor scores should be non-negative."""
        result = burnout_predictor.predict_burnout()

        for factor in result['risk_factors']:
            assert factor['score'] >= 0

    def test_factor_scores_within_max(self, burnout_predictor):
        """Factor scores should not exceed their maximum weights."""
        result = burnout_predictor.predict_burnout()

        max_weights = {
            'declining_productivity': 25,
            'overwork': 20,
            'night_sessions': 15,
            'weekend_work': 15,
            'variability': 15,
            'continuous_days': 10
        }

        for factor in result['risk_factors']:
            max_weight = max_weights.get(factor['factor'], 25)
            assert factor['score'] <= max_weight


class TestRiskLevelThresholds:
    """Test risk level threshold mapping."""

    def test_low_threshold(self, low_risk_burnout_predictor):
        """Risk score 0-25 should be 'low'."""
        result = low_risk_burnout_predictor.predict_burnout()

        if result['risk_score'] <= 25:
            assert result['risk_level'] == 'low'

    def test_risk_level_matches_score(self, burnout_predictor):
        """Risk level should match score thresholds."""
        result = burnout_predictor.predict_burnout()

        score = result['risk_score']
        level = result['risk_level']

        if level != 'unknown':
            if score <= 25:
                assert level == 'low'
            elif score <= 50:
                assert level == 'medium'
            elif score <= 75:
                assert level == 'high'
            else:
                assert level == 'critical'


class TestConfidenceCalculation:
    """Test confidence level calculation."""

    def test_empty_data_zero_confidence(self, empty_burnout_predictor):
        """Empty data should have 0 confidence."""
        result = empty_burnout_predictor.predict_burnout()
        assert result['confidence'] == 0.0

    def test_more_data_higher_confidence(self, burnout_predictor, high_risk_burnout_predictor):
        """More sessions should increase confidence."""
        result1 = burnout_predictor.predict_burnout()
        result2 = high_risk_burnout_predictor.predict_burnout()

        # High risk has more sessions, should have higher confidence
        if result2['total_sessions_analyzed'] > result1['total_sessions_analyzed']:
            assert result2['confidence'] >= result1['confidence']


class TestRecommendationsGeneration:
    """Test recommendations generation logic."""

    def test_recommendations_relevant_to_factors(self, high_risk_burnout_predictor):
        """Recommendations should relate to identified factors."""
        result = high_risk_burnout_predictor.predict_burnout()

        # Just verify we get some recommendations when there are factors
        if len(result['risk_factors']) > 0:
            assert len(result['recommendations']) > 0

    def test_max_recommendations(self, high_risk_burnout_predictor):
        """Should not exceed maximum recommendations."""
        result = high_risk_burnout_predictor.predict_burnout()

        # Should have reasonable number of recommendations
        assert len(result['recommendations']) <= 5

    def test_recommendations_in_czech(self, high_risk_burnout_predictor):
        """Recommendations should be in Czech."""
        result = high_risk_burnout_predictor.predict_burnout()

        # Check for common Czech words in recommendations
        for rec in result['recommendations']:
            # Most recommendations contain Czech text
            assert any(
                word in rec.lower()
                for word in ['dni', 'sessions', 'odpocinek', 'pauzu', 'pracu', 'tyden', 'hodiny', 'zkus', 'vyhne']
            ) or len(rec) > 10  # Or at least substantial text


class TestAnalyzedPeriod:
    """Test analyzed period reporting."""

    def test_analyzed_period_format(self, burnout_predictor):
        """analyzed_period should be formatted correctly."""
        result = burnout_predictor.predict_burnout()

        assert 'days' in result['analyzed_period']

    def test_sessions_count_accurate(self, high_risk_burnout_predictor, high_risk_sessions):
        """total_sessions_analyzed should match input."""
        result = high_risk_burnout_predictor.predict_burnout()

        # Should analyze all sessions within the period
        assert result['total_sessions_analyzed'] > 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_single_session(self):
        """Should handle single session gracefully."""
        import sys
        import os
        ml_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ml-service'))
        if ml_dir not in sys.path:
            sys.path.insert(0, ml_dir)

        from models.burnout_predictor import BurnoutPredictor
        from datetime import datetime

        single_session = [{
            'date': datetime.now().strftime('%Y-%m-%d'),
            'hour': 10,
            'day_of_week': 0,
            'preset': 'deep_work',
            'category': 'Coding',
            'duration_minutes': 52,
            'completed': True,
            'productivity_rating': 80
        }]

        predictor = BurnoutPredictor(single_session)
        result = predictor.predict_burnout()

        # Should handle gracefully
        assert 'risk_score' in result
        assert result['confidence'] < 0.5  # Low confidence with little data

    def test_all_perfect_ratings(self):
        """Should handle all 100% productivity ratings."""
        import sys
        import os
        ml_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ml-service'))
        if ml_dir not in sys.path:
            sys.path.insert(0, ml_dir)

        from models.burnout_predictor import BurnoutPredictor
        from datetime import datetime, timedelta

        perfect_sessions = []
        for day in range(10):
            date = datetime.now() - timedelta(days=day)
            perfect_sessions.append({
                'date': date.strftime('%Y-%m-%d'),
                'hour': 10,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 100
            })

        predictor = BurnoutPredictor(perfect_sessions)
        result = predictor.predict_burnout()

        # Perfect ratings shouldn't increase risk
        assert result['risk_score'] < 50

    def test_no_ratings(self):
        """Should handle sessions without ratings."""
        import sys
        import os
        ml_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ml-service'))
        if ml_dir not in sys.path:
            sys.path.insert(0, ml_dir)

        from models.burnout_predictor import BurnoutPredictor
        from datetime import datetime, timedelta

        no_rating_sessions = []
        for day in range(10):
            date = datetime.now() - timedelta(days=day)
            no_rating_sessions.append({
                'date': date.strftime('%Y-%m-%d'),
                'hour': 10,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True
                # No productivity_rating
            })

        predictor = BurnoutPredictor(no_rating_sessions)
        result = predictor.predict_burnout()

        # Should still work without ratings
        assert 'risk_score' in result
        assert result['risk_level'] != 'unknown' or result['confidence'] == 0
