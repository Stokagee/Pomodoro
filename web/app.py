"""
Pomodoro Timer - Flask Web Application v2.0
Optimized for IT professionals with 52/17 Deep Work mode
Docker + MongoDB + ML Integration
"""

# Eventlet monkey patching MUST be first before any other imports
import eventlet
eventlet.monkey_patch()

import os
import io
import csv
import json
import requests
from flask import Flask, render_template, jsonify, request, Response
from flask_socketio import SocketIO, emit
from pathlib import Path
from dotenv import load_dotenv
from prometheus_flask_exporter import PrometheusMetrics

# Structured logging for Loki
from utils.logger import logger
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
import time

# Load environment variables
load_dotenv()

# Import database module
from models.database import (
    init_db, log_session, get_today_stats, get_weekly_stats,
    get_history, get_all_sessions, get_streak_stats, clear_all_sessions,
    # Calendar & Daily Focus
    get_daily_focus, set_daily_focus, update_daily_focus_stats,
    get_calendar_month, get_calendar_week,
    # Weekly Planning
    get_weekly_plan, save_weekly_plan,
    # Weekly Review
    get_weekly_review, generate_weekly_stats, save_weekly_review,
    get_latest_weekly_review, get_theme_analytics,
    # Achievements
    init_achievements, get_all_achievements, check_and_unlock_achievements,
    get_achievements_summary, ACHIEVEMENTS_DEFINITIONS,
    # XP/Leveling System
    get_user_profile, add_xp, calculate_level_from_xp, fix_user_profile_data,
    # Streak Protection
    use_streak_freeze, toggle_vacation_mode, check_streak_with_protection,
    # Category Skills
    update_category_skill, get_category_skills,
    # Daily Challenges
    get_or_create_daily_challenge, update_daily_challenge_progress,
    # Weekly Quests
    get_or_create_weekly_quests, update_weekly_quest_progress,
    # FocusAI Learning Recommender
    get_user_analytics_for_ai, get_last_session_context,
    get_cached_ai_recommendation, cache_ai_recommendation,
    get_recent_tasks, invalidate_ai_cache,
    # Category Management
    rename_category_in_sessions
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'pomodoro-secret-key-2025')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# =============================================================================
# PROMETHEUS METRICS
# =============================================================================
metrics = PrometheusMetrics(app, path=None)  # Disable automatic /metrics endpoint

@app.route('/metrics')
def prometheus_metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

# Application info
app_info = Info('pomodoro_web', 'Pomodoro Web Application Information')
app_info.info({
    'version': '2.0',
    'service': 'pomodoro-web',
    'preset_default': 'deep_work'
})

# Custom metrics
SESSION_LOGGED = Counter(
    'pomodoro_sessions_logged_total',
    'Total number of sessions logged',
    ['preset', 'category', 'completed']
)

SESSION_DURATION = Histogram(
    'pomodoro_session_duration_minutes',
    'Duration of pomodoro sessions in minutes',
    ['preset'],
    buckets=[15, 25, 30, 45, 52, 60, 90, 120]
)

PRODUCTIVITY_RATING = Histogram(
    'pomodoro_productivity_rating',
    'Productivity rating of sessions (1-100)',
    ['category'],
    buckets=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
)

ACTIVE_USERS = Gauge(
    'pomodoro_active_users',
    'Number of active WebSocket connections'
)

ML_REQUEST_DURATION = Histogram(
    'pomodoro_ml_request_duration_seconds',
    'Duration of ML service requests',
    ['endpoint'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
)

ML_REQUEST_ERRORS = Counter(
    'pomodoro_ml_request_errors_total',
    'Total ML service request errors',
    ['endpoint']
)


@app.route('/health')
@metrics.do_not_track()
def health_check():
    """Health check endpoint for monitoring"""
    return jsonify({'status': 'healthy', 'service': 'pomodoro-web'})


# Add Python built-ins to Jinja2 environment
app.jinja_env.globals['max'] = max
app.jinja_env.globals['min'] = min

# Paths
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / 'config.json'

# ML Service URL
ML_SERVICE_URL = os.getenv('ML_SERVICE_URL', 'http://localhost:5001')


def load_config():
    """Load configuration from JSON file"""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config):
    """Save configuration to JSON file"""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_ml_recommendation():
    """Get recommendation from ML service"""
    start_time = time.time()
    try:
        response = requests.get(f'{ML_SERVICE_URL}/api/recommendation', timeout=2)
        ML_REQUEST_DURATION.labels(endpoint='recommendation').observe(time.time() - start_time)
        if response.ok:
            return response.json()
    except Exception as e:
        ML_REQUEST_ERRORS.labels(endpoint='recommendation').inc()
        print(f"ML service unavailable: {e}")
    return None


def get_ml_prediction():
    """Get prediction from ML service"""
    start_time = time.time()
    try:
        response = requests.get(f'{ML_SERVICE_URL}/api/prediction/today', timeout=2)
        ML_REQUEST_DURATION.labels(endpoint='prediction').observe(time.time() - start_time)
        if response.ok:
            return response.json()
    except Exception as e:
        ML_REQUEST_ERRORS.labels(endpoint='prediction').inc()
        print(f"ML service unavailable: {e}")
    return None


def get_ml_burnout_risk():
    """Get burnout risk assessment from ML service"""
    try:
        response = requests.get(f'{ML_SERVICE_URL}/api/burnout-risk', timeout=5)
        if response.ok:
            return response.json()
    except Exception as e:
        print(f"ML burnout service unavailable: {e}")
    return None


def get_ml_optimal_schedule(sessions=6, day='today'):
    """Get optimal schedule from Focus Optimizer ML service"""
    try:
        response = requests.get(
            f'{ML_SERVICE_URL}/api/optimal-schedule',
            params={'sessions': sessions, 'day': day},
            timeout=5
        )
        if response.ok:
            return response.json()
    except Exception as e:
        print(f"ML optimal schedule service unavailable: {e}")
    return None


def get_ml_quality_prediction(preset='deep_work', category=None):
    """Get session quality prediction from ML service"""
    from datetime import datetime

    # Calculate sessions today and minutes since last
    today_stats = get_today_stats()
    sessions_today = today_stats.get('sessions_count', 0)

    # Get last session time
    minutes_since_last = None
    history = get_history(limit=1)
    if history:
        last_session = history[0]
        last_time = last_session.get('timestamp')
        if last_time:
            try:
                if isinstance(last_time, str):
                    last_dt = datetime.fromisoformat(last_time.replace('Z', '+00:00'))
                else:
                    last_dt = last_time
                diff = datetime.now() - last_dt.replace(tzinfo=None)
                minutes_since_last = int(diff.total_seconds() / 60)
            except Exception:
                pass

    try:
        now = datetime.now()
        response = requests.post(
            f'{ML_SERVICE_URL}/api/predict-quality',
            json={
                'hour': now.hour,
                'day': now.weekday(),
                'preset': preset,
                'category': category,
                'sessions_today': sessions_today,
                'minutes_since_last': minutes_since_last
            },
            timeout=5
        )
        if response.ok:
            return response.json()
    except Exception as e:
        print(f"ML quality prediction service unavailable: {e}")
    return None


# Routes
@app.route('/')
def index():
    """Main dashboard with timer"""
    config = load_config()
    today_stats = get_today_stats()
    recommendation = get_ml_recommendation()
    prediction = get_ml_prediction()
    burnout_risk = get_ml_burnout_risk()
    optimal_schedule = get_ml_optimal_schedule()
    today_focus = get_daily_focus()  # Get today's focus theme

    # New gamification data
    user_profile = get_user_profile()
    daily_challenge = get_or_create_daily_challenge()
    streak_status = check_streak_with_protection()

    return render_template('index.html',
                           config=config,
                           today_stats=today_stats,
                           recommendation=recommendation,
                           prediction=prediction,
                           burnout_risk=burnout_risk,
                           optimal_schedule=optimal_schedule,
                           today_focus=today_focus,
                           user_profile=user_profile,
                           daily_challenge=daily_challenge,
                           streak_status=streak_status)


@app.route('/stats')
def stats():
    """Statistics page"""
    config = load_config()
    today_stats = get_today_stats()
    weekly_stats = get_weekly_stats()
    return render_template('stats.html',
                           config=config,
                           today_stats=today_stats,
                           weekly_stats=weekly_stats)


@app.route('/insights')
def insights():
    """ML Insights page"""
    config = load_config()
    today_stats = get_today_stats()
    weekly_stats = get_weekly_stats()

    # Get ML analysis
    analysis = None
    try:
        response = requests.get(f'{ML_SERVICE_URL}/api/analysis', timeout=5)
        if response.ok:
            analysis = response.json()
    except Exception:
        pass

    # Get burnout risk
    burnout = get_ml_burnout_risk()

    # Get optimal schedule for Focus Optimizer
    optimal_schedule = get_ml_optimal_schedule()

    return render_template('insights.html',
                           config=config,
                           today_stats=today_stats,
                           weekly_stats=weekly_stats,
                           analysis=analysis,
                           burnout=burnout,
                           optimal_schedule=optimal_schedule)


@app.route('/settings')
def settings():
    """Settings page with category management"""
    config = load_config()
    today_stats = get_today_stats()
    return render_template('settings.html',
                           config=config,
                           today_stats=today_stats)


# API Routes
@app.route('/api/config')
def api_config():
    """Get current configuration"""
    return jsonify(load_config())


@app.route('/api/config', methods=['POST'])
def api_update_config():
    """Update configuration"""
    config = load_config()
    updates = request.json
    config.update(updates)
    save_config(config)
    return jsonify({'status': 'ok', 'config': config})


@app.route('/api/categories', methods=['POST'])
def api_manage_categories():
    """Category management API endpoint.

    Actions:
    - add: Add new category
    - rename: Rename category and update all sessions
    - delete: Delete category (optionally reassign sessions)
    """
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    action = data.get('action')
    config = load_config()
    categories = config.get('categories', [])
    sessions_updated = 0

    if action == 'add':
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Nazev kategorie je prazdny'})
        if len(name) > 50:
            return jsonify({'success': False, 'error': 'Nazev je prilis dlouhy (max 50 znaku)'})
        if name in categories:
            return jsonify({'success': False, 'error': 'Kategorie jiz existuje'})

        categories.append(name)
        config['categories'] = categories
        save_config(config)
        _sync_categories_to_ml_service(categories)

        return jsonify({'success': True, 'categories': categories})

    elif action == 'rename':
        old_name = data.get('oldName', '').strip()
        new_name = data.get('newName', '').strip()

        if not old_name or not new_name:
            return jsonify({'success': False, 'error': 'Chybi nazvy kategorii'})
        if old_name not in categories:
            return jsonify({'success': False, 'error': 'Puvodni kategorie neexistuje'})
        if new_name in categories and new_name != old_name:
            return jsonify({'success': False, 'error': 'Kategorie s novym nazvem jiz existuje'})

        # Update category in config
        idx = categories.index(old_name)
        categories[idx] = new_name
        config['categories'] = categories
        save_config(config)

        # Update all sessions with old category name
        sessions_updated = rename_category_in_sessions(old_name, new_name)

        _sync_categories_to_ml_service(categories)

        return jsonify({
            'success': True,
            'categories': categories,
            'sessions_updated': sessions_updated
        })

    elif action == 'delete':
        name = data.get('name', '').strip()
        reassign_to = data.get('reassignTo')

        if not name:
            return jsonify({'success': False, 'error': 'Chybi nazev kategorie'})
        if name == 'Other':
            return jsonify({'success': False, 'error': 'Kategorii "Other" nelze smazat'})
        if name not in categories:
            return jsonify({'success': False, 'error': 'Kategorie neexistuje'})

        # Remove category from config
        categories.remove(name)
        config['categories'] = categories
        save_config(config)

        # Optionally reassign sessions
        if reassign_to and reassign_to in categories:
            sessions_updated = rename_category_in_sessions(name, reassign_to)

        _sync_categories_to_ml_service(categories)

        return jsonify({
            'success': True,
            'categories': categories,
            'sessions_updated': sessions_updated
        })

    else:
        return jsonify({'success': False, 'error': 'Neznama akce'}), 400


@app.route('/api/log', methods=['POST'])
def api_log_session():
    """Log a completed session"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Validate preset
    config = load_config()
    preset = data.get('preset', 'deep_work')
    if preset not in config['presets']:
        preset = 'deep_work'

    # Validate category
    category = data.get('category', 'Other')
    if category not in config['categories']:
        category = 'Other'

    # Validate duration
    duration = data.get('duration_minutes', 52)
    if not isinstance(duration, (int, float)) or duration < 1 or duration > 180:
        duration = 52

    # Validate rating (0-100%)
    rating = data.get('productivity_rating')
    if rating is not None:
        if not isinstance(rating, (int, float)) or rating < 0 or rating > 100:
            rating = None

    # Sanitize text inputs
    task = str(data.get('task', ''))[:200]  # Max 200 chars
    notes = str(data.get('notes', ''))[:500]  # Max 500 chars

    session_id = log_session(
        preset=preset,
        category=category,
        task=task,
        duration_minutes=int(duration),
        completed=bool(data.get('completed', True)),
        productivity_rating=rating,
        notes=notes
    )

    # Record Prometheus metrics
    SESSION_LOGGED.labels(
        preset=preset,
        category=category,
        completed=str(data.get('completed', True))
    ).inc()
    SESSION_DURATION.labels(preset=preset).observe(int(duration))
    if rating is not None:
        PRODUCTIVITY_RATING.labels(category=category).observe(rating)

    # Update daily focus stats after logging session
    from datetime import date
    update_daily_focus_stats(date.today())

    # === NEW GAMIFICATION SYSTEMS ===
    # Update daily challenge progress
    challenge_result = update_daily_challenge_progress()

    # Update weekly quest progress
    weekly_result = update_weekly_quest_progress()

    # Add XP for completed session
    base_xp = 10
    # Bonus XP based on productivity rating
    if rating:
        rating_bonus = int((rating / 100) * 5)  # Up to 5 bonus XP
        base_xp += rating_bonus
    # Bonus XP based on duration
    if duration >= 52:
        base_xp += 5  # Deep work bonus
    elif duration >= 25:
        base_xp += 2  # Standard session bonus

    xp_result = add_xp(base_xp, 'session')

    # Update category skill
    skill_result = update_category_skill(category, int(duration))

    # Check for newly unlocked achievements
    newly_unlocked = check_and_unlock_achievements()

    # Invalidate AI caches (new session = new data)
    try:
        import requests
        requests.post(f'{ML_SERVICE_URL}/api/ai/invalidate-cache', timeout=2)
    except Exception:
        pass  # Non-blocking, don't fail session log if cache invalidation fails

    # === STRUCTURED LOGGING ===
    logger.session_completed(
        session_id=session_id,
        preset=preset,
        category=category,
        duration=int(duration),
        rating=rating,
        completed=bool(data.get('completed', True)),
        xp_earned=base_xp,
        achievements_count=len(newly_unlocked)
    )

    # Log achievements
    for achievement in newly_unlocked:
        logger.achievement_unlocked(
            achievement_id=achievement.get('id', ''),
            name=achievement.get('name', ''),
            xp_reward=achievement.get('xp_reward', 0),
            category=achievement.get('category')
        )

    # Log level up
    if xp_result.get('level_up'):
        logger.level_up(
            old_level=xp_result.get('old_level', 1),
            new_level=xp_result.get('new_level', 1),
            new_title=xp_result.get('new_title', ''),
            total_xp=xp_result.get('total_xp', 0)
        )

    # Log challenge completion
    if challenge_result.get('completed'):
        logger.challenge_completed(
            challenge_type='daily',
            xp_reward=challenge_result.get('xp_reward', 0)
        )

    return jsonify({
        'status': 'ok',
        'session_id': session_id,
        'achievements_unlocked': newly_unlocked,
        'xp_earned': base_xp,
        'level_up': xp_result.get('level_up', False),
        'new_level': xp_result.get('new_level'),
        'challenge_completed': challenge_result.get('completed', False),
        'quest_completed': weekly_result.get('completed', False)
    })


@app.route('/api/stats/today')
def api_today_stats():
    """Get today's statistics"""
    return jsonify(get_today_stats())


@app.route('/api/stats/weekly')
def api_weekly_stats():
    """Get weekly statistics"""
    return jsonify(get_weekly_stats())


@app.route('/api/history')
def api_history():
    """Get full session history"""
    limit = request.args.get('limit', 100, type=int)
    return jsonify(get_history(limit))


@app.route('/api/export/csv')
def api_export_csv():
    """Export all sessions to CSV"""
    sessions = get_history(limit=10000)

    # Create CSV in memory
    output = io.StringIO()
    fieldnames = ['date', 'time', 'preset', 'category', 'task', 'duration_minutes',
                  'completed', 'productivity_rating', 'notes']
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()

    for session in sessions:
        writer.writerow({
            'date': session.get('date', ''),
            'time': session.get('time', ''),
            'preset': session.get('preset', ''),
            'category': session.get('category', ''),
            'task': session.get('task', ''),
            'duration_minutes': session.get('duration_minutes', 0),
            'completed': session.get('completed', False),
            'productivity_rating': session.get('productivity_rating', ''),
            'notes': session.get('notes', '')
        })

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=pomodoro_sessions.csv'}
    )


@app.route('/api/streak')
def api_streak():
    """Get streak statistics"""
    return jsonify(get_streak_stats())


@app.route('/api/reset', methods=['POST'])
def api_reset():
    """Reset all sessions - for testing"""
    deleted = clear_all_sessions()
    return jsonify({'status': 'ok', 'deleted_sessions': deleted})


@app.route('/api/recommendation')
def api_recommendation():
    """Get ML recommendation"""
    rec = get_ml_recommendation()
    if rec:
        return jsonify(rec)
    return jsonify({'error': 'ML service unavailable'}), 503


@app.route('/api/prediction')
def api_prediction():
    """Get ML prediction"""
    pred = get_ml_prediction()
    if pred:
        return jsonify(pred)
    return jsonify({'error': 'ML service unavailable'}), 503


@app.route('/api/burnout-risk')
def api_burnout_risk():
    """Get burnout risk assessment"""
    risk = get_ml_burnout_risk()
    if risk:
        return jsonify(risk)
    return jsonify({
        'error': 'ML service unavailable',
        'risk_level': 'unknown',
        'risk_score': 0
    }), 503


@app.route('/api/weekly-insights/<week_start>')
def weekly_insights_proxy(week_start):
    """Proxy pro ML weekly insights pro kalendář"""
    try:
        response = requests.get(
            f"{ML_SERVICE_URL}/api/weekly-insights/{week_start}",
            timeout=5
        )
        if response.ok:
            return jsonify(response.json())
        return jsonify({
            'predicted_sessions': None,
            'recommended_focus': None,
            'tip': 'ML service nedostupný.',
            'productivity_trend': None
        }), response.status_code
    except Exception as e:
        print(f"ML weekly insights service unavailable: {e}")
        return jsonify({
            'predicted_sessions': None,
            'recommended_focus': None,
            'tip': 'ML service není dostupný.',
            'productivity_trend': None
        }), 503


@app.route('/api/anomalies')
def api_anomalies():
    """Get pattern anomaly detection from ML service.

    Returns detected anomalies in user behavior:
    - productivity_drop: Sudden decline in productivity
    - unusual_hours: Working outside normal schedule
    - category_shift: Change in preferred categories
    - streak_break: Missing days after long streak
    - overwork_spike: Sudden increase in work intensity
    - quality_decline: Drop in session ratings
    """
    try:
        response = requests.get(f'{ML_SERVICE_URL}/api/detect-anomalies', timeout=5)
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"ML anomaly detection service unavailable: {e}")

    return jsonify({
        'error': 'ML service unavailable',
        'anomalies_detected': 0,
        'overall_status': 'error',
        'anomalies': [],
        'proactive_tips': [],
        'baseline_summary': None,
        'patterns': None,
        'confidence': 0.0,
        'metadata': {
            'model_version': '1.0',
            'error': 'Service unavailable'
        }
    }), 503


@app.route('/api/quality-prediction', methods=['GET', 'POST'])
def api_quality_prediction():
    """Get session quality prediction before starting

    Query params or JSON body:
        preset: Preset name (default: deep_work)
        category: Category name (optional)

    Returns:
        dict: Prediction with productivity, factors, recommendation
    """
    # Get parameters from request
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        preset = data.get('preset', 'deep_work')
        category = data.get('category')
    else:
        preset = request.args.get('preset', 'deep_work')
        category = request.args.get('category')

    prediction = get_ml_quality_prediction(preset, category)
    if prediction:
        return jsonify(prediction)

    # Return default prediction when ML service unavailable
    return jsonify({
        'error': 'ML service unavailable',
        'predicted_productivity': 70.0,
        'confidence': 0,
        'factors': [],
        'recommendation': {
            'type': 'info',
            'message': 'ML sluzba neni dostupna',
            'action': None,
            'icon': 'info'
        }
    }), 503


# =============================================================================
# CALENDAR ROUTES
# =============================================================================

@app.route('/calendar')
def calendar():
    """Calendar page with weekly/monthly view"""
    config = load_config()
    today_stats = get_today_stats()
    today_focus = get_daily_focus()

    return render_template('calendar.html',
                           config=config,
                           today_stats=today_stats,
                           today_focus=today_focus)


# =============================================================================
# CALENDAR API ENDPOINTS
# =============================================================================

@app.route('/api/calendar/month/<int:year>/<int:month>')
def api_calendar_month(year, month):
    """Get calendar data for a specific month"""
    if not (1 <= month <= 12) or not (2000 <= year <= 2100):
        return jsonify({'error': 'Invalid date'}), 400

    data = get_calendar_month(year, month)
    # Convert dict to array format for frontend
    days = list(data.values())
    return jsonify({
        'success': True,
        'year': year,
        'month': month,
        'days': days
    })


@app.route('/api/calendar/week/<date_str>')
def api_calendar_week(date_str):
    """Get calendar data for a week containing the specified date"""
    try:
        from datetime import datetime
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    data = get_calendar_week(target_date)
    return jsonify(data)


# =============================================================================
# DAILY FOCUS API ENDPOINTS
# =============================================================================

@app.route('/api/focus/today')
def api_focus_today():
    """Get today's focus"""
    focus = get_daily_focus()
    if focus:
        return jsonify({'success': True, 'focus': focus})
    return jsonify({'success': False, 'focus': {'date': None, 'themes': [], 'theme': None, 'notes': '', 'planned_sessions': 0, 'total_planned': 0}})


@app.route('/api/focus/<date_str>')
def api_focus_date(date_str):
    """Get focus for a specific date"""
    try:
        from datetime import datetime
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    focus = get_daily_focus(target_date)
    if focus:
        return jsonify({'success': True, 'focus': focus})
    return jsonify({'success': False, 'focus': {'date': date_str, 'themes': [], 'theme': None, 'notes': '', 'planned_sessions': 0, 'total_planned': 0}})


@app.route('/api/focus', methods=['POST'])
def api_set_focus():
    """Set or update daily focus with multiple themes"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    date_str = data.get('date')
    if not date_str:
        return jsonify({'error': 'Date is required'}), 400

    # Validate date
    try:
        from datetime import datetime
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    config = load_config()

    # Handle both old format (single theme) and new format (themes array)
    themes = data.get('themes', [])
    if not themes and data.get('theme'):
        # Backward compatibility: convert single theme to array
        themes = [{
            'theme': data.get('theme'),
            'planned_sessions': data.get('planned_sessions', 1),
            'notes': ''
        }]

    # Validate themes
    valid_themes = []
    for t in themes:
        theme_name = t.get('theme')
        if theme_name and theme_name in config['categories']:
            valid_themes.append({
                'theme': theme_name,
                'planned_sessions': min(max(int(t.get('planned_sessions', 1)), 1), 20),
                'notes': str(t.get('notes', ''))[:500]
            })

    notes = str(data.get('notes', ''))[:1000]

    result = set_daily_focus(target_date, valid_themes, notes)

    # === STRUCTURED LOGGING ===
    logger.daily_focus_set(
        date=date_str,
        themes=valid_themes,
        total_planned=sum(t.get('planned_sessions', 0) for t in valid_themes),
        notes=notes
    )

    return jsonify({
        'success': True,
        'date': date_str,
        'themes': valid_themes,
        'notes': notes
    })


@app.route('/api/focus/<date_str>', methods=['PUT'])
def api_update_focus(date_str):
    """Update existing daily focus with multiple themes"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        from datetime import datetime
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    existing = get_daily_focus(target_date)
    if not existing:
        return jsonify({'error': 'Focus not found for this date'}), 404

    # Handle themes array or merge with existing
    themes = data.get('themes')
    if themes is None:
        # If no themes provided, keep existing themes
        themes = existing.get('themes', [])
        # Backward compatibility: single theme update
        if data.get('theme'):
            themes = [{
                'theme': data.get('theme'),
                'planned_sessions': data.get('planned_sessions', 1),
                'notes': ''
            }]

    notes = str(data.get('notes', existing.get('notes', '')))[:1000]

    # Validate themes
    config = load_config()
    valid_themes = []
    for t in themes:
        theme_name = t.get('theme') if isinstance(t, dict) else t
        if theme_name and theme_name in config['categories']:
            valid_themes.append({
                'theme': theme_name,
                'planned_sessions': int(t.get('planned_sessions', 1)) if isinstance(t, dict) else 1,
                'notes': str(t.get('notes', ''))[:500] if isinstance(t, dict) else ''
            })

    result = set_daily_focus(target_date, valid_themes, notes)

    return jsonify({
        'status': 'ok',
        'date': date_str,
        'themes': valid_themes,
        'notes': notes,
        'planned_sessions': sum(t.get('planned_sessions', 0) for t in valid_themes)
    })


# =============================================================================
# WEEKLY PLANNING API ENDPOINTS
# =============================================================================

@app.route('/api/planning/week/<date_str>')
def api_get_weekly_plan(date_str):
    """Get weekly plan for the week containing the specified date"""
    try:
        from datetime import datetime
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    plan = get_weekly_plan(target_date)
    if plan:
        return jsonify(plan)

    # Return empty plan structure
    from datetime import timedelta
    days_since_monday = target_date.weekday()
    week_start = target_date - timedelta(days=days_since_monday)

    return jsonify({
        'week_start': week_start.isoformat(),
        'days': [],
        'goals': []
    })


@app.route('/api/planning/week', methods=['POST'])
def api_save_weekly_plan():
    """Save or update weekly plan"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    week_start = data.get('week_start')
    days = data.get('days', [])
    goals = data.get('goals', [])

    if not week_start:
        return jsonify({'error': 'week_start is required'}), 400

    try:
        from datetime import datetime
        week_start_date = datetime.strptime(week_start, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    # Validate days structure
    config = load_config()
    valid_days = []
    for day in days:
        if not isinstance(day, dict):
            continue
        if 'date' not in day:
            continue

        theme = day.get('theme')
        if theme and theme not in config['categories']:
            continue

        valid_days.append({
            'date': day['date'],
            'theme': theme,
            'planned_sessions': day.get('planned_sessions', 6),
            'notes': str(day.get('notes', ''))[:1000]
        })

    # Validate goals
    valid_goals = [str(g)[:500] for g in goals if g][:10]  # Max 10 goals

    result = save_weekly_plan(week_start_date, valid_days, valid_goals)

    return jsonify({
        'status': 'ok',
        'week_start': week_start,
        'days_saved': len(valid_days),
        'goals': valid_goals
    })


# =============================================================================
# WEEKLY REVIEW API ENDPOINTS
# =============================================================================

@app.route('/api/review/week/<date_str>')
def api_get_weekly_review(date_str):
    """Get weekly review for the week containing the specified date"""
    try:
        from datetime import datetime
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    review = get_weekly_review(target_date)
    if review:
        return jsonify(review)

    # Generate stats for the week even if no review exists
    stats = generate_weekly_stats(target_date)

    from datetime import timedelta
    days_since_monday = target_date.weekday()
    week_start = target_date - timedelta(days=days_since_monday)

    return jsonify({
        'week_start': week_start.isoformat(),
        'stats': stats,
        'theme_breakdown': stats.get('theme_breakdown', []),
        'reflections': {
            'what_worked': '',
            'what_to_improve': '',
            'lessons_learned': ''
        },
        'next_week_goals': [],
        'ml_insights': {}
    })


@app.route('/api/review/week', methods=['POST'])
def api_save_weekly_review():
    """Save weekly review"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    week_start = data.get('week_start')
    reflections = data.get('reflections', {})
    next_week_goals = data.get('next_week_goals', [])

    if not week_start:
        return jsonify({'error': 'week_start is required'}), 400

    try:
        from datetime import datetime
        week_start_date = datetime.strptime(week_start, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    # Get ML insights if available
    ml_insights = {}
    try:
        response = requests.get(f'{ML_SERVICE_URL}/api/prediction/week', timeout=2)
        if response.ok:
            ml_insights = response.json()
    except Exception:
        pass

    # Validate goals
    valid_goals = [str(g)[:500] for g in next_week_goals if g][:10]

    result = save_weekly_review(week_start_date, reflections, valid_goals, ml_insights)

    return jsonify({
        'status': 'ok',
        'week_start': week_start
    })


@app.route('/api/review/latest')
def api_latest_review():
    """Get the most recent weekly review"""
    review = get_latest_weekly_review()
    if review:
        return jsonify(review)
    return jsonify({'error': 'No reviews found'}), 404


# =============================================================================
# ANALYTICS API ENDPOINTS
# =============================================================================

@app.route('/api/analytics/themes')
def api_theme_analytics():
    """Get analytics for all themes/categories"""
    analytics = get_theme_analytics()
    return jsonify(analytics)


@app.route('/api/analytics/weekly-trend')
def api_weekly_trend():
    """Get weekly trend data"""
    from datetime import date, timedelta

    today = date.today()
    weeks_data = []

    for i in range(4):  # Last 4 weeks
        week_date = today - timedelta(weeks=i)
        stats = generate_weekly_stats(week_date)

        days_since_monday = week_date.weekday()
        week_start = week_date - timedelta(days=days_since_monday)

        weeks_data.append({
            'week_start': week_start.isoformat(),
            'total_sessions': stats['total_sessions'],
            'total_hours': stats['total_hours'],
            'avg_productivity': stats['avg_productivity']
        })

    return jsonify(weeks_data)


# =============================================================================
# ACHIEVEMENTS ROUTES & API
# =============================================================================

@app.route('/achievements')
def achievements():
    """Achievements page - gamification trophy room"""
    config = load_config()
    today_stats = get_today_stats()
    achievements_data = get_all_achievements()
    summary = get_achievements_summary()

    # New gamification data
    user_profile = get_user_profile()
    daily_challenge = get_or_create_daily_challenge()
    weekly_quests = get_or_create_weekly_quests()
    category_skills = get_category_skills()

    return render_template('achievements.html',
                           config=config,
                           today_stats=today_stats,
                           achievements=achievements_data,
                           summary=summary,
                           definitions=ACHIEVEMENTS_DEFINITIONS,
                           user_profile=user_profile,
                           daily_challenge=daily_challenge,
                           weekly_quests=weekly_quests,
                           category_skills=category_skills)


@app.route('/api/achievements')
def api_get_achievements():
    """Get all achievements with progress"""
    achievements_data = get_all_achievements()
    return jsonify({
        'success': True,
        'achievements': achievements_data,
        'total': len(achievements_data)
    })


@app.route('/api/achievements/stats')
def api_achievements_stats():
    """Get achievements summary statistics"""
    summary = get_achievements_summary()
    return jsonify({
        'success': True,
        'stats': summary
    })


@app.route('/api/achievements/check', methods=['POST'])
def api_check_achievements():
    """Manually trigger achievement check and return newly unlocked"""
    newly_unlocked = check_and_unlock_achievements()
    return jsonify({
        'success': True,
        'newly_unlocked': newly_unlocked,
        'count': len(newly_unlocked)
    })


# =============================================================================
# XP & PROFILE ROUTES
# =============================================================================

@app.route('/api/profile')
def api_get_profile():
    """Get user profile with XP, level, and title"""
    profile = get_user_profile()
    return jsonify({
        'success': True,
        'profile': profile
    })


@app.route('/api/xp/add', methods=['POST'])
def api_add_xp():
    """Manually add XP (for testing or special rewards)"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    amount = data.get('amount', 0)
    source = data.get('source', 'manual')

    if not isinstance(amount, (int, float)) or amount <= 0 or amount > 10000:
        return jsonify({'error': 'Invalid XP amount (1-10000)'}), 400

    result = add_xp(int(amount), source)
    return jsonify({
        'success': True,
        'result': result
    })


@app.route('/api/xp/fix', methods=['POST'])
def api_fix_xp():
    """Fix inconsistent XP/level data"""
    result = fix_user_profile_data()
    return jsonify({
        'success': True,
        'result': result
    })


@app.route('/api/level')
def api_get_level():
    """Get current level info"""
    profile = get_user_profile()
    return jsonify({
        'success': True,
        'level': profile.get('level', 1),
        'title': profile.get('title', 'Zacatecnik'),
        'xp': profile.get('xp', 0),
        'xp_to_next_level': profile.get('xp_to_next_level', 100)
    })


# =============================================================================
# DAILY CHALLENGES ROUTES
# =============================================================================

@app.route('/api/challenges/daily')
def api_get_daily_challenge():
    """Get today's daily challenge"""
    challenge = get_or_create_daily_challenge()
    return jsonify({
        'success': True,
        'challenge': challenge
    })


@app.route('/api/challenges/daily/progress', methods=['POST'])
def api_update_daily_progress():
    """Update daily challenge progress"""
    result = update_daily_challenge_progress()
    return jsonify({
        'success': True,
        'result': result
    })


# =============================================================================
# WEEKLY QUESTS ROUTES
# =============================================================================

@app.route('/api/challenges/weekly')
def api_get_weekly_quests():
    """Get this week's quests"""
    quests = get_or_create_weekly_quests()
    return jsonify({
        'success': True,
        'quests': quests
    })


@app.route('/api/challenges/weekly/progress', methods=['POST'])
def api_update_weekly_progress():
    """Update weekly quest progress"""
    data = request.json
    quest_id = data.get('quest_id') if data else None

    result = update_weekly_quest_progress(quest_id)
    return jsonify({
        'success': True,
        'result': result
    })


# =============================================================================
# STREAK PROTECTION ROUTES
# =============================================================================

@app.route('/api/streak/status')
def api_streak_status():
    """Get streak status with protection info"""
    status = check_streak_with_protection()
    return jsonify({
        'success': True,
        'streak': status
    })


@app.route('/api/streak/freeze', methods=['POST'])
def api_use_streak_freeze():
    """Use a streak freeze token"""
    result = use_streak_freeze()
    return jsonify({
        'success': result.get('success', False),
        'result': result
    })


@app.route('/api/streak/vacation', methods=['POST'])
def api_toggle_vacation():
    """Toggle vacation mode"""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    enable = data.get('enable', True)
    days = data.get('days', 7)

    if not isinstance(days, int) or days < 1 or days > 30:
        days = 7

    result = toggle_vacation_mode(enable, days)
    return jsonify({
        'success': True,
        'result': result
    })


# =============================================================================
# CATEGORY SKILLS ROUTES
# =============================================================================

@app.route('/api/skills')
def api_get_skills():
    """Get all category skills"""
    skills = get_category_skills()
    return jsonify({
        'success': True,
        'skills': skills
    })


@app.route('/api/skills/<category>')
def api_get_skill(category):
    """Get skill for a specific category"""
    skills = get_category_skills()

    # Find the specific category
    skill = next((s for s in skills if s.get('category') == category), None)

    if skill:
        return jsonify({
            'success': True,
            'skill': skill
        })

    return jsonify({
        'success': False,
        'error': f'Category "{category}" not found'
    }), 404


# =============================================================================
# AI CHALLENGES PROXY ROUTES (from ML service)
# =============================================================================

@app.route('/api/ai/daily-challenge')
def api_ai_daily_challenge():
    """Get AI-generated daily challenge from ML service"""
    try:
        # Get user context for personalization
        today_stats = get_today_stats()
        profile = get_user_profile()

        response = requests.get(
            f'{ML_SERVICE_URL}/api/ai/daily-challenge',
            params={
                'sessions_today': today_stats.get('sessions_count', 0),
                'level': profile.get('level', 1)
            },
            timeout=10
        )
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI daily challenge service unavailable: {e}")

    return jsonify({
        'error': 'AI service unavailable',
        'fallback': True
    }), 503


@app.route('/api/ai/weekly-quest')
def api_ai_weekly_quest():
    """Get AI-generated weekly quest from ML service"""
    try:
        profile = get_user_profile()
        weekly_stats = get_weekly_stats()

        response = requests.get(
            f'{ML_SERVICE_URL}/api/ai/weekly-quest',
            params={
                'level': profile.get('level', 1),
                'weekly_sessions': weekly_stats.get('sessions_count', 0)
            },
            timeout=10
        )
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI weekly quest service unavailable: {e}")

    return jsonify({
        'error': 'AI service unavailable',
        'fallback': True
    }), 503


@app.route('/api/ai/motivation')
def api_ai_motivation():
    """Get AI-generated motivation message"""
    try:
        today_stats = get_today_stats()
        streak = get_streak_stats()

        response = requests.get(
            f'{ML_SERVICE_URL}/api/ai/motivation',
            params={
                'sessions_today': today_stats.get('sessions_count', 0),
                'streak': streak.get('current_streak', 0)
            },
            timeout=10
        )
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI motivation service unavailable: {e}")

    return jsonify({
        'error': 'AI service unavailable',
        'fallback': True,
        'message': 'Pokracuj v praci! Kazda session te posouvá blíz k cíli.'
    })


@app.route('/api/ai/health')
def api_ai_health():
    """Check AI/Ollama service health"""
    try:
        response = requests.get(f'{ML_SERVICE_URL}/api/ai/health', timeout=5)
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI health check failed: {e}")

    return jsonify({
        'status': 'unavailable',
        'ollama_connected': False
    })


# =============================================================================
# FOCUSAI FULL LLM ANALYSIS ROUTES (Ollama-powered)
# =============================================================================

@app.route('/api/ai/morning-briefing')
def api_ai_morning_briefing():
    """FocusAI: Get morning briefing with AI predictions and recommendations.

    Uses full LLM analysis of session history including notes from last 30 days.
    Provides personalized daily plan, wellbeing check, and motivation.

    Cache: 4 hours (invalidated on new session)
    """
    try:
        response = requests.get(
            f'{ML_SERVICE_URL}/api/ai/morning-briefing',
            timeout=60  # Long timeout for full LLM analysis
        )
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI morning briefing unavailable: {e}")

    return jsonify({
        'error': 'AI service unavailable',
        'ai_available': False,
        'fallback': True
    }), 503


@app.route('/api/ai/evening-review')
def api_ai_evening_review():
    """FocusAI: Get evening review with day analysis.

    Analyzes today's sessions, compares to predictions, identifies patterns.
    Provides insights from session notes and recommendations for tomorrow.

    Cache: Until next day (invalidated on new session)
    """
    try:
        response = requests.get(
            f'{ML_SERVICE_URL}/api/ai/evening-review',
            timeout=45
        )
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI evening review unavailable: {e}")

    return jsonify({
        'error': 'AI service unavailable',
        'ai_available': False,
        'fallback': True
    }), 503


@app.route('/api/ai/integrated-insight')
def api_ai_integrated_insight():
    """FocusAI: Get cross-model integrated recommendations.

    Combines insights from burnout, anomaly, quality, and schedule analysis.
    Provides holistic view of productivity patterns and actionable advice.

    Cache: 2 hours (invalidated on new session)
    """
    try:
        response = requests.get(
            f'{ML_SERVICE_URL}/api/ai/integrated-insight',
            timeout=90  # Longest timeout - combines multiple analyses
        )
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI integrated insight unavailable: {e}")

    return jsonify({
        'error': 'AI service unavailable',
        'ai_available': False,
        'fallback': True
    }), 503


@app.route('/api/ai/analyze-burnout')
def api_ai_analyze_burnout():
    """FocusAI: Full LLM burnout risk analysis with notes context.

    Analyzes session patterns AND notes for burnout signals.
    More comprehensive than rule-based /api/burnout-risk endpoint.

    Cache: 6 hours (invalidated on new session)
    """
    try:
        response = requests.get(
            f'{ML_SERVICE_URL}/api/ai/analyze-burnout',
            timeout=45
        )
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI burnout analysis unavailable: {e}")

    return jsonify({
        'error': 'AI service unavailable',
        'ai_available': False,
        'fallback': True
    }), 503


@app.route('/api/ai/analyze-anomalies')
def api_ai_analyze_anomalies():
    """FocusAI: Full LLM anomaly detection with notes context.

    Detects patterns and anomalies in user behavior using LLM analysis.
    More intelligent than rule-based /api/anomalies endpoint.

    Cache: 6 hours (invalidated on new session)
    """
    try:
        response = requests.get(
            f'{ML_SERVICE_URL}/api/ai/analyze-anomalies',
            timeout=45
        )
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI anomaly analysis unavailable: {e}")

    return jsonify({
        'error': 'AI service unavailable',
        'ai_available': False,
        'fallback': True
    }), 503


@app.route('/api/ai/analyze-quality', methods=['GET', 'POST'])
def api_ai_analyze_quality():
    """FocusAI: Full LLM quality prediction with context.

    Query params or JSON body:
        preset: Preset name (default: deep_work)
        category: Category name (optional)

    Cache: 30 minutes (invalidated on new session)
    """
    # Get parameters
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        preset = data.get('preset', 'deep_work')
        category = data.get('category')
    else:
        preset = request.args.get('preset', 'deep_work')
        category = request.args.get('category')

    try:
        response = requests.post(
            f'{ML_SERVICE_URL}/api/ai/analyze-quality',
            json={'preset': preset, 'category': category},
            timeout=45
        )
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI quality analysis unavailable: {e}")

    return jsonify({
        'error': 'AI service unavailable',
        'ai_available': False,
        'fallback': True
    }), 503


@app.route('/api/ai/optimal-schedule-ai')
def api_ai_optimal_schedule_ai():
    """FocusAI: Full LLM schedule optimization.

    Query params:
        sessions: Number of sessions to plan (default: 6)
        day: Day of week (default: today)

    Cache: 4 hours (invalidated on new session)
    """
    sessions = request.args.get('sessions', 6, type=int)
    day = request.args.get('day', 'today')

    try:
        response = requests.get(
            f'{ML_SERVICE_URL}/api/ai/optimal-schedule-ai',
            params={'sessions': sessions, 'day': day},
            timeout=45
        )
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI optimal schedule unavailable: {e}")

    return jsonify({
        'error': 'AI service unavailable',
        'ai_available': False,
        'fallback': True
    }), 503


@app.route('/api/ai/learning-v2')
def api_ai_learning_v2():
    """FocusAI: Enhanced learning recommendations (v2).

    Full LLM analysis of session notes to identify learning patterns.

    Cache: 6 hours (invalidated on new session)
    """
    try:
        response = requests.get(
            f'{ML_SERVICE_URL}/api/ai/learning-v2',
            timeout=60
        )
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI learning v2 unavailable: {e}")

    return jsonify({
        'error': 'AI service unavailable',
        'ai_available': False,
        'fallback': True
    }), 503


@app.route('/api/ai/cache-status')
def api_ai_cache_status():
    """Get AI cache status from ML service."""
    try:
        response = requests.get(
            f'{ML_SERVICE_URL}/api/ai/cache-status',
            timeout=5
        )
        if response.ok:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI cache status unavailable: {e}")

    return jsonify({
        'error': 'AI service unavailable',
        'total_cached': 0,
        'valid': 0,
        'caches': []
    }), 503


# =============================================================================
# FOCUSAI LEARNING RECOMMENDER ROUTES
# =============================================================================

@app.route('/api/ai/learning-recommendations')
def api_ai_learning_recommendations():
    """FocusAI: Get comprehensive learning recommendations.

    Analyzes user's session history, skills, and patterns to provide:
    - Skill gaps identification
    - Recommended topics to learn
    - Category balance analysis
    - Personalized tips
    - Next session suggestion

    Cache: 24 hours (invalidated after 5+ new sessions)
    """
    # Check cache first
    cached = get_cached_ai_recommendation('learning')
    if cached:
        return jsonify({
            **cached,
            'from_cache': True
        })

    # Gather user analytics
    try:
        user_data = get_user_analytics_for_ai()

        # Serialize datetime objects for JSON
        for session in user_data.get('recent_sessions', []):
            if 'created_at' in session:
                session['created_at'] = session['created_at'].isoformat() if hasattr(session['created_at'], 'isoformat') else str(session['created_at'])
            if '_id' in session:
                session['_id'] = str(session['_id'])

        response = requests.post(
            f"{ML_SERVICE_URL}/api/ai/learning-recommendations",
            json=user_data,
            timeout=60
        )
        if response.status_code == 200:
            result = response.json()
            # Cache for 24 hours
            cache_ai_recommendation('learning', result, ttl_hours=24)
            return jsonify({
                **result,
                'from_cache': False
            })
        else:
            print(f"AI learning recommendations failed: {response.status_code}")
    except Exception as e:
        print(f"AI learning recommendations error: {e}")

    # Return fallback recommendations
    return jsonify(_get_fallback_learning_recommendations())


@app.route('/api/ai/next-session')
def api_ai_next_session():
    """FocusAI: Get quick suggestion for next session.

    Optimized for timer start modal - provides:
    - Suggested category
    - Suggested topic/task
    - Recommended preset
    - Reason for suggestion

    Cache: 15 minutes
    """
    # Check short-term cache
    cached = get_cached_ai_recommendation('next_session')
    if cached:
        return jsonify({
            **cached,
            'from_cache': True
        })

    # Get context
    from datetime import datetime
    context = get_last_session_context()
    today_stats = get_today_stats()
    config = load_config()

    try:
        response = requests.get(
            f"{ML_SERVICE_URL}/api/ai/next-session-suggestion",
            params={
                'category': context.get('last_category', ''),
                'task': context.get('last_task', ''),
                'hour': datetime.now().hour,
                'sessions': today_stats.get('sessions_count', 0),
                'categories': ','.join(config.get('categories', []))  # Pass user's categories
            },
            timeout=180
        )
        if response.status_code == 200:
            result = response.json()
            # Cache for 15 minutes
            cache_ai_recommendation('next_session', result, ttl_hours=0.25)
            return jsonify({
                **result,
                'from_cache': False
            })
    except Exception as e:
        print(f"AI next session suggestion error: {e}")

    # Fallback suggestion
    return jsonify(_get_fallback_session_suggestion())


@app.route('/api/ai/expand-suggestion', methods=['POST'])
def api_ai_expand_suggestion():
    """FocusAI: Expand a suggestion with more details.

    Use this after getting a suggestion from /api/ai/next-session
    to get more detailed information about the suggested topic.

    Request body:
    {
        "suggestion": {
            "category": "Learning",
            "topic": "Robot Framework basics",
            "reason": "Improve automation skills"
        },
        "question_type": "resources|steps|time_estimate|connection"
    }

    Question types:
    - resources: Learning materials, documentation, tutorials
    - steps: Concrete action steps
    - time_estimate: How long it takes
    - connection: How it connects to career goals
    """
    data = request.json or {}
    suggestion = data.get('suggestion', {})
    question_type = data.get('question_type', 'resources')

    if not suggestion.get('topic'):
        return jsonify({
            'error': 'Missing suggestion.topic',
            'answer': 'Chybí téma k rozšíření.',
            'confidence': 0
        }), 400

    try:
        response = requests.post(
            f"{ML_SERVICE_URL}/api/ai/expand-suggestion",
            json={
                'suggestion': suggestion,
                'question_type': question_type
            },
            timeout=180
        )
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            print(f"AI expand suggestion failed: {response.status_code}")
    except Exception as e:
        print(f"AI expand suggestion error: {e}")

    # Fallback response
    return jsonify({
        'answer': 'AI dočasně nedostupná. Zkus to později.',
        'type': question_type,
        'icon': '⚠️',
        'confidence': 0,
        'ai_generated': False,
        'fallback': True
    })


@app.route('/api/ai/extract-topics', methods=['POST'])
def api_ai_extract_topics():
    """FocusAI: Extract technologies and concepts from task history.

    Analyzes task descriptions to identify:
    - Technologies user works with
    - Concepts being learned
    - Areas of expertise
    """
    data = request.json
    tasks = data.get('tasks') if data else None

    # If no tasks provided, get from database
    if not tasks:
        tasks = get_recent_tasks(limit=100)

    try:
        response = requests.post(
            f"{ML_SERVICE_URL}/api/ai/extract-topics",
            json={'tasks': tasks},
            timeout=180
        )
        if response.status_code == 200:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI extract topics error: {e}")

    # Fallback - basic extraction
    return jsonify({
        'technologies': [],
        'concepts': [],
        'expertise_areas': [],
        'fallback': True
    })


@app.route('/api/ai/analyze-patterns', methods=['POST'])
def api_ai_analyze_patterns():
    """FocusAI: Analyze productivity patterns.

    Analyzes:
    - Best productive hours
    - Category preferences by time
    - Consistency patterns
    - Recommendations based on patterns
    """
    try:
        # Gather productivity data
        from datetime import datetime, timedelta
        today_stats = get_today_stats()
        weekly_stats = get_weekly_stats()
        streak = get_streak_stats()

        data = {
            'today_stats': today_stats,
            'weekly_stats': weekly_stats,
            'streak_data': streak,
            'current_hour': datetime.now().hour,
            'day_of_week': datetime.now().weekday()
        }

        response = requests.post(
            f"{ML_SERVICE_URL}/api/ai/analyze-patterns",
            json=data,
            timeout=180
        )
        if response.status_code == 200:
            return jsonify(response.json())
    except Exception as e:
        print(f"AI analyze patterns error: {e}")

    return jsonify({
        'productivity': {
            'best_hours': [9, 10, 14, 15],
            'worst_hours': [12, 13, 18],
            'best_day': 'Tuesday',
            'avg_sessions_per_day': 3.0,
            'consistency_score': 0.5
        },
        'recommendations': ['Zkuste pracovat v dopolednich hodinach pro lepsi produktivitu'],
        'warnings': [],
        'fallback': True
    })


@app.route('/api/ai/invalidate-cache', methods=['POST'])
def api_ai_invalidate_cache():
    """Invalidate AI recommendation cache.

    Query params:
        type: Specific cache type to invalidate (learning, next_session, topics)
              If not provided, invalidates all caches.
    """
    cache_type = request.args.get('type')
    invalidate_ai_cache(cache_type)

    return jsonify({
        'status': 'ok',
        'invalidated': cache_type or 'all'
    })


def _get_fallback_learning_recommendations():
    """Get fallback learning recommendations when AI is unavailable."""
    from datetime import datetime
    return {
        'skill_gaps': [],
        'recommended_topics': [
            {
                'topic': 'Prozkoumat nove technologie',
                'category': 'Learning',
                'reason': 'Pravidelne uceni udrzuje znalosti aktualni',
                'priority': 'medium',
                'estimated_sessions': 5,
                'related_to': None
            }
        ],
        'category_balance': [],
        'personalized_tips': [
            'Zkuste stridavat ruzne typy prace pro lepsi produktivitu',
            'Pravidelne prestavky pomahaji udrzet soustredeni'
        ],
        'next_session_suggestion': {
            'category': 'Learning',
            'topic': 'Osobni rozvoj',
            'preset': 'standard',
            'reason': 'Vzdy je dobry cas pro uceni',
            'confidence': 0.3
        },
        'user_knowledge': {
            'technologies': [],
            'concepts': [],
            'expertise_areas': []
        },
        'motivational_message': 'Kazda session te priblizuje k tvym cilum!',
        'analysis_summary': 'Pro detailnejsi analyzu potrebuji vice dat o tvych sessions.',
        'generated_at': datetime.now().isoformat(),
        'confidence_score': 0.3,
        'fallback': True
    }


def _get_fallback_session_suggestion():
    """Get fallback session suggestion when AI is unavailable."""
    from datetime import datetime
    hour = datetime.now().hour

    # Time-based suggestions
    if 6 <= hour < 12:
        # Morning - deep work
        return {
            'category': 'Coding',
            'topic': 'Code review a refaktoring',
            'preset': 'deep_work',
            'reason': 'Rano je idealni cas pro narocnou praci - vyuzijte maximalni soustredeni',
            'confidence': 0.5,
            'fallback': True
        }
    elif 12 <= hour < 17:
        # Afternoon - learning
        return {
            'category': 'Learning',
            'topic': 'Dokumentace a tutorialy',
            'preset': 'standard',
            'reason': 'Odpoledne je vhodne pro uceni novych veci',
            'confidence': 0.5,
            'fallback': True
        }
    else:
        # Evening - planning
        return {
            'category': 'Planning',
            'topic': 'Planovani a organizace',
            'preset': 'short_focus',
            'reason': 'Vecer je dobry cas pro planovani dalsiho dne',
            'confidence': 0.5,
            'fallback': True
        }


# =============================================================================
# START DAY WORKFLOW ROUTES
# =============================================================================

def _sync_categories_to_ml_service(categories: list) -> bool:
    """Send categories to ML service so AI uses correct category list."""
    try:
        response = requests.post(
            f'{ML_SERVICE_URL}/api/config/categories',
            json={'categories': categories},
            timeout=5
        )
        return response.ok
    except Exception as e:
        print(f"Failed to sync categories to ML service: {e}")
        return False


@app.route('/api/start-day')
def api_start_day():
    """Get all data needed for Start Day workflow.

    Returns:
        - categories: User's categories from config.json
        - morning_briefing: AI analysis + predictions (from ML service)
        - daily_challenge: Today's challenge with XP reward
        - today_focus: Current daily focus (if already set)
        - user_profile: Level, XP, title
        - streak_status: Current streak with protection info
    """
    from datetime import date

    # Load categories from config
    config = load_config()
    categories = config.get('categories', [])

    # Sync categories to ML service for AI prompts
    _sync_categories_to_ml_service(categories)

    # Get morning briefing from ML service (with user's categories)
    morning_briefing = None
    try:
        response = requests.get(
            f'{ML_SERVICE_URL}/api/ai/morning-briefing',
            timeout=60
        )
        if response.ok:
            morning_briefing = response.json()
    except Exception as e:
        print(f"Morning briefing unavailable: {e}")

    # Get daily challenge
    daily_challenge = get_or_create_daily_challenge()

    # Get today's focus (may be empty)
    today_focus = get_daily_focus(date.today())

    # Get user profile
    user_profile = get_user_profile()

    # Get streak status with protection
    streak_status = check_streak_with_protection()

    # Get today's stats
    today_stats = get_today_stats()

    return jsonify({
        'success': True,
        'categories': categories,
        'morning_briefing': morning_briefing,
        'daily_challenge': daily_challenge,
        'today_focus': today_focus,
        'user_profile': user_profile,
        'streak_status': streak_status,
        'today_stats': today_stats,
        'date': date.today().isoformat()
    })


@app.route('/api/start-day', methods=['POST'])
def api_save_start_day():
    """Save Start Day plan (themes + challenge acceptance).

    Request body:
        - themes: Array of {theme, planned_sessions, notes}
        - challenge_accepted: Boolean
        - notes: Optional overall notes for the day

    Returns:
        - success: Boolean
        - saved focus data
    """
    from datetime import date

    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    config = load_config()
    today = date.today()

    # Process themes
    themes = data.get('themes', [])
    valid_themes = []
    for t in themes:
        theme_name = t.get('theme')
        if theme_name and theme_name in config['categories']:
            valid_themes.append({
                'theme': theme_name,
                'planned_sessions': min(max(int(t.get('planned_sessions', 1)), 1), 20),
                'notes': str(t.get('notes', ''))[:500]
            })

    # Save daily focus
    notes = str(data.get('notes', ''))[:1000]
    set_daily_focus(today, valid_themes, notes)

    # Handle challenge acceptance
    challenge_accepted = data.get('challenge_accepted', False)
    challenge_result = None
    if challenge_accepted:
        # Mark challenge as accepted in today's focus or similar
        # The challenge is auto-created, so we just track acceptance
        challenge_result = {
            'accepted': True,
            'challenge': get_or_create_daily_challenge()
        }

    # Calculate total planned sessions
    total_planned = sum(t.get('planned_sessions', 0) for t in valid_themes)

    return jsonify({
        'success': True,
        'date': today.isoformat(),
        'themes': valid_themes,
        'total_planned_sessions': total_planned,
        'notes': notes,
        'challenge': challenge_result
    })


# WebSocket Events
@socketio.on('connect')
def handle_connect():
    """Client connected"""
    ACTIVE_USERS.inc()
    logger.websocket_event('connect')
    emit('connected', {'status': 'connected'})


@socketio.on('disconnect')
def handle_disconnect():
    """Client disconnected"""
    ACTIVE_USERS.dec()
    logger.websocket_event('disconnect')


@socketio.on('timer_complete')
def handle_timer_complete(data):
    """Timer completed - log session"""
    preset = data.get('preset', 'deep_work')
    category = data.get('category', 'Other')
    duration = data.get('duration_minutes', 52)
    rating = data.get('productivity_rating')

    session_id = log_session(
        preset=preset,
        category=category,
        task=data.get('task', ''),
        duration_minutes=duration,
        completed=True,
        productivity_rating=rating,
        notes=data.get('notes', '')
    )

    # Update daily focus stats after logging session
    from datetime import date
    update_daily_focus_stats(date.today())

    # === NEW GAMIFICATION SYSTEMS ===
    # Update daily challenge progress
    challenge_result = update_daily_challenge_progress()

    # Update weekly quest progress
    weekly_result = update_weekly_quest_progress()

    # Add XP for completed session
    base_xp = 10
    if rating:
        rating_bonus = int((rating / 100) * 5)
        base_xp += rating_bonus
    if duration >= 52:
        base_xp += 5
    elif duration >= 25:
        base_xp += 2

    xp_result = add_xp(base_xp, 'session')

    # Update category skill
    update_category_skill(category, int(duration))

    # Check for newly unlocked achievements
    newly_unlocked = check_and_unlock_achievements()

    # Invalidate AI caches (new session = new data)
    try:
        import requests
        requests.post(f'{ML_SERVICE_URL}/api/ai/invalidate-cache', timeout=2)
    except Exception:
        pass  # Non-blocking

    emit('session_logged', {
        'status': 'ok',
        'session_id': session_id,
        'xp_earned': base_xp,
        'level_up': xp_result.get('level_up', False),
        'new_level': xp_result.get('new_level'),
        'challenge_completed': challenge_result.get('completed', False),
        'quest_completed': weekly_result.get('completed', False)
    })

    # Emit achievement notifications for each newly unlocked
    for achievement in newly_unlocked:
        emit('achievement_unlocked', achievement)

    # Emit level up notification
    if xp_result.get('level_up'):
        emit('level_up', {
            'new_level': xp_result.get('new_level'),
            'new_title': xp_result.get('new_title')
        })

    # Emit challenge completion notification
    if challenge_result.get('completed'):
        emit('challenge_completed', {
            'type': 'daily',
            'xp_reward': challenge_result.get('xp_reward', 0)
        })


@socketio.on('request_stats')
def handle_request_stats():
    """Send updated stats to client"""
    emit('stats_update', {
        'today': get_today_stats(),
        'weekly': get_weekly_stats()
    })


if __name__ == '__main__':
    # Initialize database
    print("\n" + "=" * 50)
    print("  POMODORO TIMER v2.0 - IT Optimized (52/17)")
    print("  Docker + MongoDB + ML")
    print("=" * 50)

    if init_db():
        print("  Database: Connected")
        logger.info("STARTUP", "Database connected", {"db_type": "PostgreSQL"})
        # Oprava případných nekonzistencí v XP/level datech
        try:
            fix_result = fix_user_profile_data()
            if fix_result.get('fixed'):
                print(f"  XP/Level: Fixed (level {fix_result['old_level']} -> {fix_result['new_level']}, total_xp={fix_result['total_xp']})")
        except Exception as e:
            print(f"  XP/Level: Skipped fix ({e})")
    else:
        print("  Database: Connection failed (using fallback)")

    print(f"\n  Open in browser: http://localhost:5000")
    print(f"\n  Presets:")
    config = load_config()
    for key, preset in config['presets'].items():
        print(f"    - {preset['name']}: {preset['work_minutes']}/{preset['break_minutes']} min")
    print("\n" + "=" * 50 + "\n")

    debug_mode = os.getenv('FLASK_ENV') == 'development' and os.getenv('FLASK_DEBUG', '0') == '1'
    socketio.run(app, host='0.0.0.0', port=5000, debug=debug_mode, allow_unsafe_werkzeug=True)
