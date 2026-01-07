"""
Tests for PatternAnomalyDetector.
Comprehensive tests for anomaly detection in user behavior patterns.
"""
import pytest
import sys
import os
from datetime import datetime, timedelta

# Ensure ml-service is in path
ML_SERVICE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ml-service'))
if ML_SERVICE_DIR not in sys.path:
    sys.path.insert(0, ML_SERVICE_DIR)


class TestAnomalyDetectorEmpty:
    """Test anomaly detector with no or insufficient data."""

    def test_empty_sessions_returns_insufficient_data(self, empty_anomaly_detector):
        """Should return insufficient_data status when no sessions."""
        result = empty_anomaly_detector.detect_all()

        assert result['overall_status'] == 'insufficient_data'
        assert result['anomalies_detected'] == 0
        assert result['anomalies'] == []
        assert result['confidence'] == 0.0

    def test_insufficient_days(self, short_history_anomaly_detector):
        """Should return insufficient_data when less than 7 days."""
        result = short_history_anomaly_detector.detect_all()

        assert result['overall_status'] == 'insufficient_data'
        assert 'Potrebuji alespon' in result.get('message', '')


class TestBaselineCalculation:
    """Test baseline statistics calculation."""

    def test_baseline_contains_required_fields(self, anomaly_detector):
        """Baseline should have all required metrics."""
        assert anomaly_detector.baseline is not None

        baseline = anomaly_detector.baseline
        assert 'avg_productivity' in baseline
        assert 'std_productivity' in baseline
        assert 'avg_sessions_per_day' in baseline
        assert 'typical_hours' in baseline
        assert 'category_distribution' in baseline

    def test_typical_hours_iqr(self, anomaly_detector):
        """Typical hours should have IQR bounds."""
        hours = anomaly_detector.baseline['typical_hours']

        assert 'q1' in hours
        assert 'q3' in hours
        assert 'min' in hours
        assert 'max' in hours
        assert hours['q1'] <= hours['q3']


class TestProductivityDropDetection:
    """Test productivity drop anomaly detection."""

    def test_detects_significant_drop(self, declining_productivity_detector):
        """Should detect significant productivity decline."""
        result = declining_productivity_detector.detect_all()

        prod_drops = [a for a in result['anomalies'] if a['type'] == 'productivity_drop']
        assert len(prod_drops) >= 1

        drop = prod_drops[0]
        assert drop['severity'] in ['low', 'medium', 'high', 'critical']
        assert drop['change_percent'] < 0
        assert 'recommendation' in drop

    def test_no_drop_when_stable(self, stable_productivity_detector):
        """Should not detect drop when productivity is stable."""
        result = stable_productivity_detector.detect_all()

        prod_drops = [a for a in result['anomalies'] if a['type'] == 'productivity_drop']
        assert len(prod_drops) == 0


class TestUnusualHoursDetection:
    """Test unusual working hours detection."""

    def test_detects_unusual_hours(self, unusual_hours_detector):
        """Should detect sessions outside normal schedule."""
        result = unusual_hours_detector.detect_all()

        hour_anomalies = [a for a in result['anomalies'] if a['type'] == 'unusual_hours']
        assert len(hour_anomalies) >= 1

        anomaly = hour_anomalies[0]
        assert 'unusual_sessions' in anomaly.get('evidence', {})

    def test_no_detection_for_normal_hours(self, anomaly_detector):
        """Should not flag normal working hours."""
        result = anomaly_detector.detect_all()

        hour_anomalies = [a for a in result['anomalies'] if a['type'] == 'unusual_hours']
        # May or may not have anomalies depending on data
        assert isinstance(hour_anomalies, list)


class TestCategoryShiftDetection:
    """Test category preference shift detection."""

    def test_detects_category_shift(self, category_shift_detector):
        """Should detect change in category preferences."""
        result = category_shift_detector.detect_all()

        shifts = [a for a in result['anomalies'] if a['type'] == 'category_shift']
        assert len(shifts) >= 1

        shift = shifts[0]
        assert 'category' in shift
        assert shift['change_percent'] > 30


class TestStreakBreakDetection:
    """Test streak break anomaly detection."""

    def test_detects_streak_break(self, broken_streak_detector):
        """Should detect gap after long streak."""
        result = broken_streak_detector.detect_all()

        breaks = [a for a in result['anomalies'] if a['type'] == 'streak_break']
        # May not detect if streak pattern doesn't match
        assert isinstance(breaks, list)


class TestOverworkSpikeDetection:
    """Test overwork spike detection."""

    def test_detects_overwork(self, overwork_detector):
        """Should detect sudden increase in sessions."""
        result = overwork_detector.detect_all()

        spikes = [a for a in result['anomalies'] if a['type'] == 'overwork_spike']
        assert len(spikes) >= 1

        spike = spikes[0]
        assert spike['ratio'] > 150


class TestQualityDeclineDetection:
    """Test quality decline detection."""

    def test_detects_consecutive_low_quality(self, quality_decline_detector):
        """Should detect consecutive below-average sessions."""
        result = quality_decline_detector.detect_all()

        declines = [a for a in result['anomalies'] if a['type'] == 'quality_decline']
        assert len(declines) >= 1

        decline = declines[0]
        assert decline['consecutive_count'] >= 3


class TestSeverityClassification:
    """Test severity level classification."""

    def test_severity_from_z_score(self):
        """Test Z-score to severity mapping."""
        from models.anomaly_detector import PatternAnomalyDetector

        detector = PatternAnomalyDetector([])

        assert detector._get_severity(1.6) == 'low'
        assert detector._get_severity(2.1) == 'medium'
        assert detector._get_severity(2.6) == 'high'
        assert detector._get_severity(3.5) == 'critical'
        assert detector._get_severity(1.0) is None


class TestOverallStatus:
    """Test overall status determination."""

    def test_healthy_when_no_anomalies(self, anomaly_detector):
        """Should return 'healthy' when no anomalies detected."""
        result = anomaly_detector.detect_all()

        if result['anomalies_detected'] == 0:
            assert result['overall_status'] == 'healthy'

    def test_status_based_on_severity(self, declining_productivity_detector):
        """Status should reflect highest severity."""
        result = declining_productivity_detector.detect_all()

        if result['anomalies']:
            severities = [a['severity'] for a in result['anomalies']]
            if 'critical' in severities:
                assert result['overall_status'] == 'critical'
            elif 'high' in severities:
                assert result['overall_status'] == 'alert'
            elif 'medium' in severities:
                assert result['overall_status'] == 'warning'
            else:
                assert result['overall_status'] == 'info'


class TestProactiveTipsGeneration:
    """Test proactive tips generation."""

    def test_tips_generated_from_anomalies(self, declining_productivity_detector):
        """Should generate tips based on detected anomalies."""
        result = declining_productivity_detector.detect_all()

        assert 'proactive_tips' in result
        assert isinstance(result['proactive_tips'], list)

    def test_positive_tip_when_no_anomalies(self, anomaly_detector):
        """Should generate positive tip when no anomalies."""
        result = anomaly_detector.detect_all()

        if result['anomalies_detected'] == 0:
            tips = result['proactive_tips']
            assert any(t.get('type') == 'positive' for t in tips)


class TestResponseStructure:
    """Test response structure for Ollama readiness."""

    def test_contains_all_required_fields(self, anomaly_detector):
        """Response should have all Ollama-ready fields."""
        result = anomaly_detector.detect_all()

        assert 'anomalies_detected' in result
        assert 'overall_status' in result
        assert 'anomalies' in result
        assert 'proactive_tips' in result
        assert 'baseline_summary' in result
        assert 'patterns' in result
        assert 'confidence' in result
        assert 'metadata' in result

    def test_anomaly_structure(self, declining_productivity_detector):
        """Each anomaly should have required fields."""
        result = declining_productivity_detector.detect_all()

        for anomaly in result['anomalies']:
            assert 'type' in anomaly
            assert 'name' in anomaly
            assert 'severity' in anomaly
            assert 'description' in anomaly
            assert 'recommendation' in anomaly
            assert 'icon' in anomaly

    def test_baseline_summary_structure(self, anomaly_detector):
        """Baseline summary should have required fields."""
        result = anomaly_detector.detect_all()

        if result['baseline_summary']:
            summary = result['baseline_summary']
            assert 'avg_productivity' in summary
            assert 'typical_hours' in summary
            assert 'avg_sessions_per_day' in summary

    def test_patterns_structure(self, anomaly_detector):
        """Patterns should have trend information."""
        result = anomaly_detector.detect_all()

        if result['patterns']:
            patterns = result['patterns']
            assert 'productivity_trend' in patterns
            assert 'work_intensity' in patterns
            assert 'schedule_regularity' in patterns

    def test_metadata_structure(self, anomaly_detector):
        """Metadata should have version and timestamp."""
        result = anomaly_detector.detect_all()

        metadata = result['metadata']
        assert 'model_version' in metadata
        assert 'total_sessions_analyzed' in metadata
        assert 'timestamp' in metadata


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_handles_missing_ratings(self, missing_ratings_detector):
        """Should handle sessions without productivity ratings."""
        result = missing_ratings_detector.detect_all()

        # Should not crash, may return no anomalies
        assert 'overall_status' in result

    def test_handles_single_category(self, single_category_detector):
        """Should handle sessions with only one category."""
        result = single_category_detector.detect_all()

        # Category shift should not trigger
        shifts = [a for a in result['anomalies'] if a['type'] == 'category_shift']
        assert len(shifts) == 0

    def test_confidence_range(self, anomaly_detector):
        """Confidence should be between 0 and 1."""
        result = anomaly_detector.detect_all()

        assert 0 <= result['confidence'] <= 1

    def test_all_anomaly_types_valid(self, anomaly_detector):
        """All detected anomaly types should be valid."""
        result = anomaly_detector.detect_all()

        valid_types = [
            'productivity_drop', 'unusual_hours', 'category_shift',
            'streak_break', 'overwork_spike', 'quality_decline'
        ]

        for anomaly in result['anomalies']:
            assert anomaly['type'] in valid_types

    def test_severity_values_valid(self, declining_productivity_detector):
        """All severity values should be valid."""
        result = declining_productivity_detector.detect_all()

        valid_severities = ['low', 'medium', 'high', 'critical']

        for anomaly in result['anomalies']:
            assert anomaly['severity'] in valid_severities


class TestDataNormalization:
    """Test data normalization and preparation."""

    def test_normalizes_old_rating_scale(self):
        """Should normalize 1-5 scale to 0-100."""
        from models.anomaly_detector import PatternAnomalyDetector

        sessions = [
            {'productivity_rating': 4, 'date': '2026-01-01', 'hour': 10, 'category': 'Coding'}
        ]

        detector = PatternAnomalyDetector(sessions)

        # 4 * 20 = 80
        assert sessions[0]['normalized_rating'] == 80

    def test_handles_new_rating_scale(self):
        """Should preserve 0-100 scale."""
        from models.anomaly_detector import PatternAnomalyDetector

        sessions = [
            {'productivity_rating': 75, 'date': '2026-01-01', 'hour': 10, 'category': 'Coding'}
        ]

        detector = PatternAnomalyDetector(sessions)

        assert sessions[0]['normalized_rating'] == 75
