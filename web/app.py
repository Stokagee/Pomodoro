"""
Pomodoro Timer - Flask Web Application v2.0
Optimized for IT professionals with 52/17 Deep Work mode
Docker + MongoDB + ML Integration
"""

import os
import io
import csv
import json
import requests
from flask import Flask, render_template, jsonify, request, Response
from flask_socketio import SocketIO, emit
from pathlib import Path
from dotenv import load_dotenv

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
    get_latest_weekly_review, get_theme_analytics
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'pomodoro-secret-key-2025')
socketio = SocketIO(app, cors_allowed_origins="*")

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
    try:
        response = requests.get(f'{ML_SERVICE_URL}/api/recommendation', timeout=2)
        if response.ok:
            return response.json()
    except Exception as e:
        print(f"ML service unavailable: {e}")
    return None


def get_ml_prediction():
    """Get prediction from ML service"""
    try:
        response = requests.get(f'{ML_SERVICE_URL}/api/prediction/today', timeout=2)
        if response.ok:
            return response.json()
    except Exception as e:
        print(f"ML service unavailable: {e}")
    return None


# Routes
@app.route('/')
def index():
    """Main dashboard with timer"""
    config = load_config()
    today_stats = get_today_stats()
    recommendation = get_ml_recommendation()
    prediction = get_ml_prediction()
    today_focus = get_daily_focus()  # Get today's focus theme

    return render_template('index.html',
                           config=config,
                           today_stats=today_stats,
                           recommendation=recommendation,
                           prediction=prediction,
                           today_focus=today_focus)


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

    return render_template('insights.html',
                           config=config,
                           today_stats=today_stats,
                           weekly_stats=weekly_stats,
                           analysis=analysis)


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

    # Update daily focus stats after logging session
    from datetime import date
    update_daily_focus_stats(date.today())

    return jsonify({'status': 'ok', 'session_id': session_id})


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


# WebSocket Events
@socketio.on('connect')
def handle_connect():
    """Client connected"""
    emit('connected', {'status': 'connected'})


@socketio.on('timer_complete')
def handle_timer_complete(data):
    """Timer completed - log session"""
    session_id = log_session(
        preset=data.get('preset', 'deep_work'),
        category=data.get('category', 'Other'),
        task=data.get('task', ''),
        duration_minutes=data.get('duration_minutes', 52),
        completed=True,
        productivity_rating=data.get('productivity_rating'),
        notes=data.get('notes', '')
    )

    # Update daily focus stats after logging session
    from datetime import date
    update_daily_focus_stats(date.today())

    emit('session_logged', {'status': 'ok', 'session_id': session_id})


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
        print("  MongoDB: Connected")
    else:
        print("  MongoDB: Connection failed (using fallback)")

    print(f"\n  Open in browser: http://localhost:5000")
    print(f"\n  Presets:")
    config = load_config()
    for key, preset in config['presets'].items():
        print(f"    - {preset['name']}: {preset['work_minutes']}/{preset['break_minutes']} min")
    print("\n" + "=" * 50 + "\n")

    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
