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
    get_history, get_all_sessions, get_streak_stats, clear_all_sessions
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

    return render_template('index.html',
                           config=config,
                           today_stats=today_stats,
                           recommendation=recommendation,
                           prediction=prediction)


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
