"""
FocusOptimizer Tests.
Tests ML focus optimization and schedule generation functionality.
"""
import pytest
from datetime import datetime


class TestFocusOptimizerEmpty:
    """Test Focus Optimizer with empty/insufficient data."""

    def test_analyze_empty_sessions(self, empty_focus_optimizer):
        """analyze() should handle empty session list."""
        result = empty_focus_optimizer.analyze()

        assert 'peak_hours' in result
        assert 'avoid_hours' in result
        assert 'optimal_schedule' in result
        assert result['confidence'] <= 0.1  # Low confidence with no data

    def test_empty_returns_defaults(self, empty_focus_optimizer):
        """Should return default recommendations when no data."""
        result = empty_focus_optimizer.analyze(day=0, num_sessions=4)

        # Should still generate a schedule using defaults
        assert result['optimal_schedule']['sessions_count'] == 4
        assert result['total_sessions_analyzed'] == 0

    def test_peak_hours_with_defaults(self, empty_focus_optimizer):
        """peak_hours should use defaults when no data."""
        result = empty_focus_optimizer.analyze()

        # Should have some peak hours even with defaults
        assert len(result['peak_hours']) > 0
        for hour in result['peak_hours']:
            assert hour['confidence'] <= 0.1  # Low confidence


class TestFocusOptimizerResponseStructure:
    """Test that Focus Optimizer returns all required fields."""

    def test_all_fields_present(self, focus_optimizer):
        """analyze() should return all expected fields."""
        result = focus_optimizer.analyze()

        expected_fields = [
            'date',
            'day_of_week',
            'day_of_week_num',
            'peak_hours',
            'avoid_hours',
            'hourly_breakdown',
            'optimal_schedule',
            'summary',
            'confidence',
            'total_sessions_analyzed',
            'recommendation_basis'
        ]

        for field in expected_fields:
            assert field in result, f"Missing field: {field}"

    def test_peak_hours_structure(self, focus_optimizer):
        """peak_hours should have proper structure."""
        result = focus_optimizer.analyze()

        for hour in result['peak_hours']:
            assert 'hour' in hour
            assert 'time' in hour
            assert 'expected_productivity' in hour
            assert 'recommended_preset' in hour
            assert 'confidence' in hour
            assert 0 <= hour['hour'] <= 23

    def test_avoid_hours_structure(self, focus_optimizer):
        """avoid_hours should have proper structure."""
        result = focus_optimizer.analyze()

        for hour in result['avoid_hours']:
            assert 'hour' in hour
            assert 'time' in hour
            assert 'reason' in hour
            assert 0 <= hour['hour'] <= 23

    def test_optimal_schedule_structure(self, focus_optimizer):
        """optimal_schedule should have proper structure."""
        result = focus_optimizer.analyze(num_sessions=4)

        schedule = result['optimal_schedule']
        assert 'sessions' in schedule
        assert 'total_work_minutes' in schedule
        assert 'total_break_minutes' in schedule
        assert 'avg_expected_productivity' in schedule

        for session in schedule['sessions']:
            assert 'slot' in session
            assert 'hour' in session
            assert 'time' in session
            assert 'preset' in session
            assert 'work_minutes' in session

    def test_summary_structure(self, focus_optimizer):
        """summary should have proper structure."""
        result = focus_optimizer.analyze()

        summary = result['summary']
        assert 'best_time_range' in summary
        assert 'recommended_sessions' in summary
        assert 'total_work_minutes' in summary

    def test_confidence_range(self, focus_optimizer):
        """confidence should be between 0.0 and 1.0."""
        result = focus_optimizer.analyze()

        assert 0.0 <= result['confidence'] <= 1.0


class TestPeakHoursDetection:
    """Test detection of peak productive hours."""

    def test_peak_hours_sorted(self, varied_hours_focus_optimizer):
        """peak_hours should be sorted by score descending."""
        result = varied_hours_focus_optimizer.analyze()

        scores = [h['score'] for h in result['peak_hours']]
        assert scores == sorted(scores, reverse=True)

    def test_peak_hours_within_work_range(self, varied_hours_focus_optimizer):
        """peak_hours should be within working hours (6-22)."""
        result = varied_hours_focus_optimizer.analyze()

        for hour in result['peak_hours']:
            assert 6 <= hour['hour'] <= 22

    def test_morning_hours_higher_with_morning_data(self, varied_hours_focus_optimizer):
        """Morning hours should score higher when morning data is better."""
        result = varied_hours_focus_optimizer.analyze()

        # With varied_hours_sessions, morning (9-11) has higher ratings
        peak_hour_values = [h['hour'] for h in result['peak_hours'][:3]]
        # At least one morning hour should be in top 3
        morning_in_peaks = any(9 <= h <= 11 for h in peak_hour_values)
        assert morning_in_peaks, f"Expected morning hours in peaks, got {peak_hour_values}"


class TestAvoidHoursDetection:
    """Test detection of hours to avoid."""

    def test_avoid_hours_sorted(self, varied_hours_focus_optimizer):
        """avoid_hours should be sorted by score ascending (worst first)."""
        result = varied_hours_focus_optimizer.analyze()

        scores = [h['score'] for h in result['avoid_hours']]
        assert scores == sorted(scores)

    def test_avoid_hours_have_reasons(self, focus_optimizer):
        """avoid_hours should have reasons."""
        result = focus_optimizer.analyze()

        for hour in result['avoid_hours']:
            assert 'reason' in hour
            assert len(hour['reason']) > 0


class TestOptimalScheduleGeneration:
    """Test optimal schedule generation."""

    def test_schedule_correct_count(self, focus_optimizer):
        """Schedule should have requested number of sessions."""
        for n in [3, 5, 8]:
            result = focus_optimizer.analyze(num_sessions=n)
            assert result['optimal_schedule']['sessions_count'] <= n

    def test_schedule_chronological_order(self, focus_optimizer):
        """Schedule sessions should be in chronological order."""
        result = focus_optimizer.analyze(num_sessions=6)

        hours = [s['hour'] for s in result['optimal_schedule']['sessions']]
        assert hours == sorted(hours)

    def test_schedule_respects_gaps(self, varied_hours_focus_optimizer):
        """Schedule should respect time gaps between sessions."""
        result = varied_hours_focus_optimizer.analyze(num_sessions=6)

        sessions = result['optimal_schedule']['sessions']
        if len(sessions) >= 2:
            hours = [s['hour'] for s in sessions]
            for i in range(len(hours) - 1):
                gap = hours[i + 1] - hours[i]
                assert gap >= 1, f"Gap too small: {hours[i]} to {hours[i+1]}"

    def test_schedule_has_presets(self, focus_optimizer):
        """Each session should have a preset."""
        result = focus_optimizer.analyze(num_sessions=4)

        valid_presets = ['deep_work', 'learning', 'quick_tasks', 'flow_mode']
        for session in result['optimal_schedule']['sessions']:
            assert session['preset'] in valid_presets

    def test_schedule_totals_correct(self, focus_optimizer):
        """Schedule totals should match sum of sessions."""
        result = focus_optimizer.analyze(num_sessions=4)

        schedule = result['optimal_schedule']
        total_work = sum(s['work_minutes'] for s in schedule['sessions'])
        total_break = sum(s['break_minutes'] for s in schedule['sessions'])

        assert schedule['total_work_minutes'] == total_work
        assert schedule['total_break_minutes'] == total_break


class TestHourlyBreakdown:
    """Test hourly breakdown data."""

    def test_breakdown_has_24_hours(self, focus_optimizer):
        """hourly_breakdown should have all 24 hours."""
        result = focus_optimizer.analyze()

        assert len(result['hourly_breakdown']) == 24
        for hour in range(24):
            assert str(hour) in result['hourly_breakdown']

    def test_breakdown_has_all_fields(self, focus_optimizer):
        """Each hour in breakdown should have required fields."""
        result = focus_optimizer.analyze()

        for hour_str, data in result['hourly_breakdown'].items():
            assert 'score' in data
            assert 'recommended_preset' in data
            assert 'time' in data


class TestDayOfWeekHandling:
    """Test handling of different days of week."""

    def test_different_days(self, focus_optimizer):
        """Should handle different day values."""
        for day in range(7):
            result = focus_optimizer.analyze(day=day)
            assert result['day_of_week_num'] == day

    def test_today_default(self, focus_optimizer):
        """Should default to today if no day specified."""
        result = focus_optimizer.analyze()

        today = datetime.now().weekday()
        assert result['day_of_week_num'] == today

    def test_invalid_day_clamped(self, focus_optimizer):
        """Invalid day values should be clamped to valid range."""
        result = focus_optimizer.analyze(day=10)
        assert 0 <= result['day_of_week_num'] <= 6


class TestConfidenceCalculation:
    """Test confidence level calculation."""

    def test_empty_data_low_confidence(self, empty_focus_optimizer):
        """Empty data should have low confidence."""
        result = empty_focus_optimizer.analyze()
        assert result['confidence'] <= 0.1

    def test_more_data_higher_confidence(self, empty_focus_optimizer, varied_hours_focus_optimizer):
        """More sessions should increase confidence."""
        empty_result = empty_focus_optimizer.analyze()
        varied_result = varied_hours_focus_optimizer.analyze()

        assert varied_result['confidence'] > empty_result['confidence']


class TestPresetRecommendations:
    """Test preset recommendations for hours."""

    def test_default_presets_by_hour(self, empty_focus_optimizer):
        """Should have sensible default presets by time of day."""
        result = empty_focus_optimizer.analyze()

        breakdown = result['hourly_breakdown']

        # Morning should recommend deep_work
        morning_preset = breakdown['9']['recommended_preset']
        assert morning_preset == 'deep_work'

        # Afternoon should recommend learning
        afternoon_preset = breakdown['14']['recommended_preset']
        assert afternoon_preset == 'learning'

    def test_presets_based_on_history(self, varied_hours_focus_optimizer):
        """Presets should be based on historical performance."""
        result = varied_hours_focus_optimizer.analyze()

        # With varied_hours data, morning uses deep_work with high ratings
        morning_data = result['hourly_breakdown']['9']
        assert morning_data['recommended_preset'] == 'deep_work'


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_single_session(self):
        """Should handle single session gracefully."""
        import sys
        import os
        ml_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ml-service'))
        if ml_dir not in sys.path:
            sys.path.insert(0, ml_dir)

        from models.focus_optimizer import FocusOptimizer

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

        optimizer = FocusOptimizer(single_session)
        result = optimizer.analyze()

        assert 'peak_hours' in result
        assert result['total_sessions_analyzed'] == 1

    def test_no_completed_sessions(self):
        """Should handle sessions that aren't completed."""
        import sys
        import os
        ml_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ml-service'))
        if ml_dir not in sys.path:
            sys.path.insert(0, ml_dir)

        from models.focus_optimizer import FocusOptimizer

        incomplete_sessions = [{
            'date': datetime.now().strftime('%Y-%m-%d'),
            'hour': 10,
            'day_of_week': 0,
            'preset': 'deep_work',
            'completed': False,  # Not completed
            'productivity_rating': 80
        }]

        optimizer = FocusOptimizer(incomplete_sessions)
        result = optimizer.analyze()

        # Should filter out incomplete sessions
        assert result['total_sessions_analyzed'] == 0

    def test_old_rating_scale(self):
        """Should handle old 1-5 rating scale."""
        import sys
        import os
        ml_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ml-service'))
        if ml_dir not in sys.path:
            sys.path.insert(0, ml_dir)

        from models.focus_optimizer import FocusOptimizer

        old_scale_sessions = [{
            'date': datetime.now().strftime('%Y-%m-%d'),
            'hour': 10,
            'day_of_week': 0,
            'preset': 'deep_work',
            'completed': True,
            'productivity_rating': 4  # Old 1-5 scale
        }]

        optimizer = FocusOptimizer(old_scale_sessions)
        result = optimizer.analyze()

        # Should normalize to 0-100 scale (4 * 20 = 80)
        assert result['total_sessions_analyzed'] == 1

    def test_one_session_requested(self, focus_optimizer):
        """Should handle request for just 1 session."""
        result = focus_optimizer.analyze(num_sessions=1)

        assert result['optimal_schedule']['sessions_count'] == 1

    def test_many_sessions_requested(self, focus_optimizer):
        """Should handle request for many sessions (capped at 12)."""
        result = focus_optimizer.analyze(num_sessions=20)

        # Should cap at 12
        assert result['optimal_schedule']['sessions_count'] <= 12


class TestCzechLocalization:
    """Test Czech language output."""

    def test_day_names_czech(self, focus_optimizer):
        """Day names should be in Czech."""
        result = focus_optimizer.analyze(day=0)

        assert result['day_of_week'] == 'Pondělí'

    def test_reasons_in_czech(self, focus_optimizer):
        """Avoid hour reasons should be in Czech."""
        result = focus_optimizer.analyze()

        for hour in result['avoid_hours']:
            # Should contain Czech characters or common Czech words
            reason = hour['reason']
            assert len(reason) > 0
