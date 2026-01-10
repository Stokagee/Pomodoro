"""
ML Service specific pytest fixtures.
Provides Flask app and test client with mocked PostgreSQL.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Get absolute path and add to sys.path for imports
ML_SERVICE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'ml-service')
ML_SERVICE_DIR = os.path.abspath(ML_SERVICE_DIR)

# Ensure ml-service directory is first in path for these tests
if ML_SERVICE_DIR not in sys.path:
    sys.path.insert(0, ML_SERVICE_DIR)


def _add_ml_to_path():
    """Helper to ensure ml-service directory is in path."""
    if ML_SERVICE_DIR not in sys.path:
        sys.path.insert(0, ML_SERVICE_DIR)
    # Remove web if present to avoid conflicts
    web_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'web'))
    if web_dir in sys.path:
        sys.path.remove(web_dir)


@pytest.fixture
def ml_app(mock_db_data, monkeypatch):
    """Create ML Flask app with mocked PostgreSQL."""
    _add_ml_to_path()

    # Mock psycopg2 imports
    mock_psycopg2 = MagicMock()
    monkeypatch.setitem(sys.modules, 'psycopg2', mock_psycopg2)
    monkeypatch.setitem(sys.modules, 'psycopg2.pool', mock_psycopg2.pool)
    monkeypatch.setitem(sys.modules, 'psycopg2.sql', MagicMock())
    monkeypatch.setitem(sys.modules, 'psycopg2.extras', MagicMock())

    # Mock pgvector
    mock_pgvector = MagicMock()
    monkeypatch.setitem(sys.modules, 'pgvector', mock_pgvector)
    monkeypatch.setitem(sys.modules, 'pgvector.psycopg2', mock_pgvector.psycopg2)

    # Import app after patching
    import app as ml_app_module

    ml_app_module.app.config['TESTING'] = True

    return ml_app_module.app


@pytest.fixture
def ml_client(ml_app):
    """Create test client for ML service."""
    return ml_app.test_client()


@pytest.fixture
def analyzer(sample_sessions_data):
    """Create ProductivityAnalyzer with sample data (list of sessions)."""
    _add_ml_to_path()
    from models.productivity_analyzer import ProductivityAnalyzer
    return ProductivityAnalyzer(sample_sessions_data)


@pytest.fixture
def recommender(sample_sessions_data):
    """Create PresetRecommender with sample data (list of sessions)."""
    _add_ml_to_path()
    from models.preset_recommender import PresetRecommender
    return PresetRecommender(sample_sessions_data)


@pytest.fixture
def predictor(sample_sessions_data):
    """Create SessionPredictor with sample data (list of sessions)."""
    _add_ml_to_path()
    from models.session_predictor import SessionPredictor
    return SessionPredictor(sample_sessions_data)


@pytest.fixture
def empty_analyzer():
    """Create ProductivityAnalyzer with empty session list."""
    _add_ml_to_path()
    from models.productivity_analyzer import ProductivityAnalyzer
    return ProductivityAnalyzer([])


@pytest.fixture
def empty_recommender():
    """Create PresetRecommender with empty session list."""
    _add_ml_to_path()
    from models.preset_recommender import PresetRecommender
    return PresetRecommender([])


@pytest.fixture
def empty_predictor():
    """Create SessionPredictor with empty session list."""
    _add_ml_to_path()
    from models.session_predictor import SessionPredictor
    return SessionPredictor([])


@pytest.fixture
def burnout_predictor(sample_sessions_data):
    """Create BurnoutPredictor with sample data."""
    _add_ml_to_path()
    from models.burnout_predictor import BurnoutPredictor
    return BurnoutPredictor(sample_sessions_data)


@pytest.fixture
def empty_burnout_predictor():
    """Create BurnoutPredictor with empty session list."""
    _add_ml_to_path()
    from models.burnout_predictor import BurnoutPredictor
    return BurnoutPredictor([])


@pytest.fixture
def high_risk_sessions():
    """Create sessions that simulate high burnout risk."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    # Create 14 days of high-risk patterns
    for day in range(14):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        # Many sessions per day (overwork)
        for hour in range(8):
            # Include night sessions (after 21:00)
            session_hour = 22 if hour > 5 else 9 + hour
            sessions.append({
                'date': date_str,
                'hour': session_hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 30 - (day * 2),  # Declining productivity
                'timestamp': date.replace(hour=session_hour).isoformat()
            })

    return sessions


@pytest.fixture
def high_risk_burnout_predictor(high_risk_sessions):
    """Create BurnoutPredictor with high-risk session patterns."""
    _add_ml_to_path()
    from models.burnout_predictor import BurnoutPredictor
    return BurnoutPredictor(high_risk_sessions)


@pytest.fixture
def low_risk_sessions():
    """Create sessions that simulate low burnout risk (healthy patterns)."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    # Create 14 days of healthy patterns
    for day in range(14):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        # Skip weekends (healthy work-life balance)
        if date.weekday() >= 5:
            continue

        # 4-5 sessions during reasonable hours
        for hour in [9, 10, 14, 15]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 75 + (day % 10),  # Stable/improving productivity
                'timestamp': date.replace(hour=hour).isoformat()
            })

    return sessions


@pytest.fixture
def low_risk_burnout_predictor(low_risk_sessions):
    """Create BurnoutPredictor with low-risk (healthy) session patterns."""
    _add_ml_to_path()
    from models.burnout_predictor import BurnoutPredictor
    return BurnoutPredictor(low_risk_sessions)


# === Focus Optimizer Fixtures ===

@pytest.fixture
def focus_optimizer(sample_sessions_data):
    """Create FocusOptimizer with sample data."""
    _add_ml_to_path()
    from models.focus_optimizer import FocusOptimizer
    return FocusOptimizer(sample_sessions_data)


@pytest.fixture
def empty_focus_optimizer():
    """Create FocusOptimizer with empty session list."""
    _add_ml_to_path()
    from models.focus_optimizer import FocusOptimizer
    return FocusOptimizer([])


@pytest.fixture
def varied_hours_sessions():
    """Create sessions with varied hours to test time patterns."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    # Create sessions across different hours and days
    for day in range(7):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        # Morning sessions (high productivity)
        for hour in [9, 10, 11]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 85 + (5 - day),
            })

        # Afternoon sessions (medium productivity)
        for hour in [14, 15, 16]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'learning',
                'category': 'Learning',
                'duration_minutes': 45,
                'completed': True,
                'productivity_rating': 65 + (5 - day),
            })

        # Evening sessions (lower productivity)
        for hour in [19, 20]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'quick_tasks',
                'category': 'Other',
                'duration_minutes': 25,
                'completed': True,
                'productivity_rating': 55 + (5 - day),
            })

    return sessions


@pytest.fixture
def varied_hours_focus_optimizer(varied_hours_sessions):
    """Create FocusOptimizer with varied hours pattern data."""
    _add_ml_to_path()
    from models.focus_optimizer import FocusOptimizer
    return FocusOptimizer(varied_hours_sessions)


# === Session Quality Predictor Fixtures ===

@pytest.fixture
def quality_predictor(sample_sessions_data):
    """Create SessionQualityPredictor with sample data."""
    _add_ml_to_path()
    from models.quality_predictor import SessionQualityPredictor
    return SessionQualityPredictor(sample_sessions_data)


@pytest.fixture
def empty_quality_predictor():
    """Create SessionQualityPredictor with empty session list."""
    _add_ml_to_path()
    from models.quality_predictor import SessionQualityPredictor
    return SessionQualityPredictor([])


@pytest.fixture
def fatigued_sessions():
    """Create sessions simulating fatigue pattern (many sessions in one day)."""
    from datetime import datetime

    today = datetime.now()
    date_str = today.strftime('%Y-%m-%d')

    sessions = []
    # 6 sessions already completed today with declining productivity
    for i in range(6):
        sessions.append({
            'date': date_str,
            'hour': 9 + i,
            'day_of_week': today.weekday(),
            'preset': 'deep_work',
            'category': 'Coding',
            'duration_minutes': 52,
            'completed': True,
            'productivity_rating': 85 - (i * 8),  # Declining: 85, 77, 69, 61, 53, 45
            'timestamp': today.replace(hour=9 + i).isoformat()
        })

    return sessions


@pytest.fixture
def fatigued_quality_predictor(fatigued_sessions):
    """Create SessionQualityPredictor with fatigued session pattern."""
    _add_ml_to_path()
    from models.quality_predictor import SessionQualityPredictor
    return SessionQualityPredictor(fatigued_sessions)


@pytest.fixture
def hourly_pattern_sessions():
    """Create sessions with clear hourly productivity patterns."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    # Create 10 days of sessions with clear hour patterns
    for day in range(10):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        # Morning peak (9-11): 85-90%
        for hour in [9, 10, 11]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 85 + (hour - 9),
            })

        # Lunch dip (12-13): 55-60%
        for hour in [12, 13]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'quick_tasks',
                'category': 'Other',
                'duration_minutes': 25,
                'completed': True,
                'productivity_rating': 55 + (hour - 12) * 5,
            })

        # Afternoon (14-16): 70-75%
        for hour in [14, 15, 16]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'learning',
                'category': 'Learning',
                'duration_minutes': 45,
                'completed': True,
                'productivity_rating': 70 + (16 - hour),
            })

    return sessions


@pytest.fixture
def hourly_quality_predictor(hourly_pattern_sessions):
    """Create SessionQualityPredictor with clear hourly patterns."""
    _add_ml_to_path()
    from models.quality_predictor import SessionQualityPredictor
    return SessionQualityPredictor(hourly_pattern_sessions)


# === Pattern Anomaly Detector Fixtures ===

@pytest.fixture
def empty_anomaly_detector():
    """Create PatternAnomalyDetector with empty session list."""
    _add_ml_to_path()
    from models.anomaly_detector import PatternAnomalyDetector
    return PatternAnomalyDetector([])


@pytest.fixture
def short_history_sessions():
    """Create sessions with only 5 days of history (less than min 7 days)."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    # Only 5 days of data
    for day in range(5):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        for hour in [9, 10, 14, 15]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 75,
                'timestamp': date.replace(hour=hour).isoformat()
            })

    return sessions


@pytest.fixture
def short_history_anomaly_detector(short_history_sessions):
    """Create PatternAnomalyDetector with insufficient history."""
    _add_ml_to_path()
    from models.anomaly_detector import PatternAnomalyDetector
    return PatternAnomalyDetector(short_history_sessions)


@pytest.fixture
def normal_pattern_sessions():
    """Create sessions with normal, stable patterns over 14 days."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    # 14 days of stable patterns
    for day in range(14):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        # Skip weekends
        if date.weekday() >= 5:
            continue

        # 4 sessions per day at normal hours
        for hour in [9, 10, 14, 15]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 75 + (day % 5),  # Stable 75-80
                'timestamp': date.replace(hour=hour).isoformat()
            })

    return sessions


@pytest.fixture
def anomaly_detector(normal_pattern_sessions):
    """Create PatternAnomalyDetector with normal stable patterns."""
    _add_ml_to_path()
    from models.anomaly_detector import PatternAnomalyDetector
    return PatternAnomalyDetector(normal_pattern_sessions)


@pytest.fixture
def declining_productivity_sessions():
    """Create sessions with declining productivity in recent days."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    # Days 4-14: High productivity baseline
    for day in range(4, 15):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        for hour in [9, 10, 14, 15]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 82,  # High baseline
                'timestamp': date.replace(hour=hour).isoformat()
            })

    # Days 0-3: Significant drop
    for day in range(4):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        for hour in [9, 10, 14, 15]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 45,  # Significant drop
                'timestamp': date.replace(hour=hour).isoformat()
            })

    return sessions


@pytest.fixture
def declining_productivity_detector(declining_productivity_sessions):
    """Create PatternAnomalyDetector with declining productivity pattern."""
    _add_ml_to_path()
    from models.anomaly_detector import PatternAnomalyDetector
    return PatternAnomalyDetector(declining_productivity_sessions)


@pytest.fixture
def stable_productivity_sessions():
    """Create sessions with very stable productivity."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    for day in range(14):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        for hour in [9, 10, 14, 15]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 75,  # Constant
                'timestamp': date.replace(hour=hour).isoformat()
            })

    return sessions


@pytest.fixture
def stable_productivity_detector(stable_productivity_sessions):
    """Create PatternAnomalyDetector with stable productivity."""
    _add_ml_to_path()
    from models.anomaly_detector import PatternAnomalyDetector
    return PatternAnomalyDetector(stable_productivity_sessions)


@pytest.fixture
def unusual_hours_sessions():
    """Create sessions with unusual working hours in recent days."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    # Heavy baseline: Very concentrated normal hours (9-11) - many sessions
    for day in range(4, 20):  # 16 days of baseline
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        # 6 sessions per day at concentrated normal hours
        for hour in [9, 9, 10, 10, 11, 11]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 75,
                'timestamp': date.replace(hour=hour).isoformat()
            })

    # Recent days: Unusual very early morning sessions (well outside IQR)
    for day in range(3):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        # Very early morning sessions - 3 AM, 4 AM, 5 AM
        for hour in [3, 4, 5]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 60,
                'timestamp': date.replace(hour=hour).isoformat()
            })

    return sessions


@pytest.fixture
def unusual_hours_detector(unusual_hours_sessions):
    """Create PatternAnomalyDetector with unusual hours pattern."""
    _add_ml_to_path()
    from models.anomaly_detector import PatternAnomalyDetector
    return PatternAnomalyDetector(unusual_hours_sessions)


@pytest.fixture
def category_shift_sessions():
    """Create sessions with significant category shift."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    # Heavy baseline: 100% Coding for 16+ days (to dominate the distribution)
    for day in range(8, 25):  # Days 8-24 (17 days of pure Coding)
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        # 5 Coding sessions per day
        for hour in [9, 10, 11, 14, 15]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 75,
                'timestamp': date.replace(hour=hour).isoformat()
            })

    # Recent 7 days: Complete shift to Learning (100%)
    for day in range(7):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        # 5 Learning sessions per day (no Coding at all)
        for hour in [9, 10, 11, 14, 15]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'learning',
                'category': 'Learning',
                'duration_minutes': 45,
                'completed': True,
                'productivity_rating': 75,
                'timestamp': date.replace(hour=hour).isoformat()
            })

    return sessions


@pytest.fixture
def category_shift_detector(category_shift_sessions):
    """Create PatternAnomalyDetector with category shift pattern."""
    _add_ml_to_path()
    from models.anomaly_detector import PatternAnomalyDetector
    return PatternAnomalyDetector(category_shift_sessions)


@pytest.fixture
def broken_streak_sessions():
    """Create sessions with a broken streak pattern."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    # Recent 3 days: No sessions (gap)
    # This creates a streak break after the previous continuous streak

    # Days 4-14: Continuous streak
    for day in range(4, 15):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        for hour in [9, 10, 14, 15]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 75,
                'timestamp': date.replace(hour=hour).isoformat()
            })

    return sessions


@pytest.fixture
def broken_streak_detector(broken_streak_sessions):
    """Create PatternAnomalyDetector with broken streak pattern."""
    _add_ml_to_path()
    from models.anomaly_detector import PatternAnomalyDetector
    return PatternAnomalyDetector(broken_streak_sessions)


@pytest.fixture
def overwork_sessions():
    """Create sessions with overwork spike in recent days."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    # Baseline: 4 sessions per day
    for day in range(4, 15):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        for hour in [9, 10, 14, 15]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 75,
                'timestamp': date.replace(hour=hour).isoformat()
            })

    # Recent days: 10+ sessions per day (overwork)
    for day in range(3):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        for hour in range(8, 22):  # 14 sessions
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 65 - (hour - 8) * 2,  # Declining
                'timestamp': date.replace(hour=hour).isoformat()
            })

    return sessions


@pytest.fixture
def overwork_detector(overwork_sessions):
    """Create PatternAnomalyDetector with overwork pattern."""
    _add_ml_to_path()
    from models.anomaly_detector import PatternAnomalyDetector
    return PatternAnomalyDetector(overwork_sessions)


@pytest.fixture
def quality_decline_sessions():
    """Create sessions with consecutive quality decline."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    # Baseline: Good quality
    for day in range(5, 15):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        for hour in [9, 10, 14, 15]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 78,
                'timestamp': date.replace(hour=hour).isoformat()
            })

    # Recent days: 5 consecutive below-average sessions
    for day in range(5):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        for hour in [9, 10, 14, 15]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 55 - (day * 3),  # Declining: 55, 52, 49, 46, 43
                'timestamp': date.replace(hour=hour).isoformat()
            })

    return sessions


@pytest.fixture
def quality_decline_detector(quality_decline_sessions):
    """Create PatternAnomalyDetector with quality decline pattern."""
    _add_ml_to_path()
    from models.anomaly_detector import PatternAnomalyDetector
    return PatternAnomalyDetector(quality_decline_sessions)


@pytest.fixture
def missing_ratings_sessions():
    """Create sessions with some missing productivity ratings."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    for day in range(14):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        for hour in [9, 10, 14, 15]:
            session = {
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',
                'duration_minutes': 52,
                'completed': True,
                'timestamp': date.replace(hour=hour).isoformat()
            }
            # Only add rating for half the sessions
            if hour in [9, 14]:
                session['productivity_rating'] = 75
            sessions.append(session)

    return sessions


@pytest.fixture
def missing_ratings_detector(missing_ratings_sessions):
    """Create PatternAnomalyDetector with missing ratings."""
    _add_ml_to_path()
    from models.anomaly_detector import PatternAnomalyDetector
    return PatternAnomalyDetector(missing_ratings_sessions)


@pytest.fixture
def single_category_sessions():
    """Create sessions with only one category."""
    from datetime import datetime, timedelta

    sessions = []
    base_date = datetime.now()

    for day in range(14):
        date = base_date - timedelta(days=day)
        date_str = date.strftime('%Y-%m-%d')

        for hour in [9, 10, 14, 15]:
            sessions.append({
                'date': date_str,
                'hour': hour,
                'day_of_week': date.weekday(),
                'preset': 'deep_work',
                'category': 'Coding',  # All same category
                'duration_minutes': 52,
                'completed': True,
                'productivity_rating': 75,
                'timestamp': date.replace(hour=hour).isoformat()
            })

    return sessions


@pytest.fixture
def single_category_detector(single_category_sessions):
    """Create PatternAnomalyDetector with single category."""
    _add_ml_to_path()
    from models.anomaly_detector import PatternAnomalyDetector
    return PatternAnomalyDetector(single_category_sessions)


# === API Test Fixtures (mock database module functions) ===

@pytest.fixture
def mock_db(monkeypatch, sample_sessions_data):
    """Mock database functions for ML service API tests.

    Patches app.get_sessions() and app.db_connected to provide test data.
    This replaces the old MongoDB-style mock that tried to set app.db.
    """
    _add_ml_to_path()
    import app as ml_app

    monkeypatch.setattr(ml_app, 'db_connected', True)
    monkeypatch.setattr(ml_app, 'get_sessions', lambda: sample_sessions_data)

    return sample_sessions_data


@pytest.fixture
def mock_db_empty(monkeypatch):
    """Mock database to return empty results."""
    _add_ml_to_path()
    import app as ml_app

    monkeypatch.setattr(ml_app, 'db_connected', True)
    monkeypatch.setattr(ml_app, 'get_sessions', lambda: [])

    return []
