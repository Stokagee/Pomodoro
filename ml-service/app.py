"""
Pomodoro ML Service - Flask API for productivity analysis
"""

import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv

from models import ProductivityAnalyzer, PresetRecommender, SessionPredictor

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/pomodoro')
client = None
db = None


def init_db():
    """Initialize MongoDB connection"""
    global client, db
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        db = client.get_database()
        print(f"ML Service connected to MongoDB: {MONGO_URI}")
        return True
    except ConnectionFailure as e:
        print(f"MongoDB connection failed: {e}")
        return False


def get_sessions():
    """Get all completed sessions from database"""
    if db is None:
        return []

    try:
        sessions = list(db.sessions.find({'completed': True}))
        # Convert ObjectId to string
        for s in sessions:
            s['_id'] = str(s['_id'])
        return sessions
    except Exception as e:
        print(f"Error fetching sessions: {e}")
        return []


@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'pomodoro-ml',
        'mongodb': 'connected' if db else 'disconnected'
    })


@app.route('/api/analysis')
def analysis():
    """
    Get full productivity analysis

    Returns:
        dict: Complete analysis including best hours, days, categories
    """
    sessions = get_sessions()
    analyzer = ProductivityAnalyzer(sessions)

    analysis_result = analyzer.analyze()
    heatmap = analyzer.get_hourly_heatmap()

    return jsonify({
        'analysis': analysis_result,
        'heatmap': heatmap
    })


@app.route('/api/recommendation')
def recommendation():
    """
    Get preset recommendation for current time

    Query params:
        category: Optional category for context-aware recommendation

    Returns:
        dict: Recommended preset with reason
    """
    category = request.args.get('category')

    sessions = get_sessions()
    recommender = PresetRecommender(sessions)

    rec = recommender.recommend(category=category)
    return jsonify(rec)


@app.route('/api/prediction/today')
def prediction_today():
    """
    Get prediction for today

    Returns:
        dict: Predicted sessions and productivity for today
    """
    sessions = get_sessions()
    predictor = SessionPredictor(sessions)

    prediction = predictor.predict_today()
    return jsonify(prediction)


@app.route('/api/prediction/week')
def prediction_week():
    """
    Get prediction for the coming week

    Returns:
        dict: Weekly prediction
    """
    sessions = get_sessions()
    predictor = SessionPredictor(sessions)

    prediction = predictor.predict_week()
    return jsonify(prediction)


@app.route('/api/trends')
def trends():
    """
    Get recent trends

    Query params:
        days: Number of days to analyze (default: 14)

    Returns:
        dict: Trend analysis
    """
    days = request.args.get('days', 14, type=int)

    sessions = get_sessions()
    predictor = SessionPredictor(sessions)

    trend_data = predictor.get_trends(days=days)
    return jsonify(trend_data)


@app.route('/api/preset-stats')
def preset_stats():
    """
    Get statistics for each preset

    Returns:
        dict: Stats per preset
    """
    sessions = get_sessions()
    recommender = PresetRecommender(sessions)

    stats = recommender.get_preset_stats()
    return jsonify(stats)


@app.route('/api/train', methods=['POST'])
def train():
    """
    Trigger model retraining

    This endpoint can be called to refresh the analysis after new data is added.
    In the current implementation, models are rebuilt on each request,
    so this is mainly for future ML model caching.

    Returns:
        dict: Training status
    """
    sessions = get_sessions()

    if not sessions:
        return jsonify({
            'status': 'no_data',
            'message': 'Žádná data k trénování'
        })

    # Run analysis to validate data
    analyzer = ProductivityAnalyzer(sessions)
    analysis = analyzer.analyze()

    return jsonify({
        'status': 'success',
        'sessions_analyzed': len(sessions),
        'sessions_with_rating': analysis['total_sessions_analyzed']
    })


@app.route('/api/insights/summary')
def insights_summary():
    """
    Get a summary of all insights for dashboard

    Returns:
        dict: Combined insights from all models
    """
    sessions = get_sessions()

    analyzer = ProductivityAnalyzer(sessions)
    recommender = PresetRecommender(sessions)
    predictor = SessionPredictor(sessions)

    analysis = analyzer.analyze()
    recommendation = recommender.recommend()
    prediction = predictor.predict_today()
    trends = predictor.get_trends()

    return jsonify({
        'analysis': {
            'best_hours': analysis['best_hours'],
            'best_day': analysis['best_day'],
            'trend': analysis['trend']
        },
        'recommendation': {
            'preset': recommendation['recommended_preset'],
            'reason': recommendation['reason'],
            'confidence': recommendation['confidence']
        },
        'prediction': {
            'sessions': prediction['predicted_sessions'],
            'productivity': prediction['predicted_productivity'],
            'remaining': prediction['remaining_sessions']
        },
        'trends': trends
    })


# === Calendar & Theme Analytics Endpoints ===

@app.route('/api/theme-productivity')
def theme_productivity():
    """
    Get productivity analysis per theme/category

    Returns:
        dict: Productivity stats for each category
    """
    sessions = get_sessions()

    if not sessions:
        return jsonify({'themes': [], 'best_theme': None})

    from collections import defaultdict
    theme_stats = defaultdict(lambda: {'sessions': 0, 'total_rating': 0, 'rated_count': 0})

    for session in sessions:
        cat = session.get('category', 'Other')
        theme_stats[cat]['sessions'] += 1
        if session.get('productivity_rating'):
            theme_stats[cat]['total_rating'] += session['productivity_rating']
            theme_stats[cat]['rated_count'] += 1

    themes = []
    best_theme = None
    best_avg = 0

    for theme, stats in theme_stats.items():
        avg_rating = (stats['total_rating'] / stats['rated_count']) if stats['rated_count'] > 0 else 0
        themes.append({
            'theme': theme,
            'sessions': stats['sessions'],
            'avg_rating': round(avg_rating, 1),
            'rated_count': stats['rated_count']
        })
        if avg_rating > best_avg and stats['rated_count'] >= 3:
            best_avg = avg_rating
            best_theme = theme

    themes.sort(key=lambda x: x['sessions'], reverse=True)

    return jsonify({
        'themes': themes,
        'best_theme': best_theme,
        'best_avg_rating': round(best_avg, 1)
    })


@app.route('/api/weekly-insights/<week_start>')
def weekly_insights(week_start):
    """
    Get ML insights for weekly review

    Args:
        week_start: Week start date in YYYY-MM-DD format

    Returns:
        dict: ML predictions and recommendations for the week
    """
    from datetime import datetime, timedelta

    sessions = get_sessions()

    if not sessions:
        return jsonify({
            'predicted_sessions': 30,
            'recommended_focus': None,
            'tip': 'Sbírejte více dat pro personalizované insights.',
            'productivity_trend': 0
        })

    # Get week's data
    try:
        week_start_date = datetime.strptime(week_start, '%Y-%m-%d')
        week_end_date = week_start_date + timedelta(days=7)
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    # Filter sessions for this week
    week_sessions = [
        s for s in sessions
        if s.get('date') and week_start <= s['date'] < week_end_date.strftime('%Y-%m-%d')
    ]

    # Calculate week stats
    total_sessions = len(week_sessions)

    # Get theme productivity
    from collections import defaultdict
    theme_stats = defaultdict(lambda: {'count': 0, 'rating_sum': 0, 'rated': 0})

    for session in week_sessions:
        cat = session.get('category', 'Other')
        theme_stats[cat]['count'] += 1
        if session.get('productivity_rating'):
            theme_stats[cat]['rating_sum'] += session['productivity_rating']
            theme_stats[cat]['rated'] += 1

    # Find best performing theme
    best_theme = None
    best_score = 0
    for theme, stats in theme_stats.items():
        if stats['rated'] > 0:
            avg = stats['rating_sum'] / stats['rated']
            if avg > best_score:
                best_score = avg
                best_theme = theme

    # Calculate trend vs previous week
    prev_week_start = (week_start_date - timedelta(days=7)).strftime('%Y-%m-%d')
    prev_week_end = week_start
    prev_week_sessions = [
        s for s in sessions
        if s.get('date') and prev_week_start <= s['date'] < prev_week_end
    ]

    prev_total = len(prev_week_sessions)
    trend = 0
    if prev_total > 0:
        trend = round(((total_sessions - prev_total) / prev_total) * 100)

    # Predict next week
    predictor = SessionPredictor(sessions)
    weekly_pred = predictor.predict_week()
    predicted_sessions = weekly_pred.get('predicted_total', 30)

    # Generate tip
    tips = []
    if best_theme:
        tips.append(f"Tvoje nejvyšší produktivita je při práci na {best_theme}.")
    if trend < -10:
        tips.append("Zkus si naplánovat více deep work bloků na příští týden.")
    elif trend > 10:
        tips.append("Skvělý pokrok! Udržuj tempo.")

    analyzer = ProductivityAnalyzer(sessions)
    analysis = analyzer.analyze()
    if analysis.get('best_hours'):
        best_hour = analysis['best_hours'][0] if analysis['best_hours'] else None
        if best_hour:
            tips.append(f"Tvoje nejproduktivnější hodina je {best_hour}:00.")

    tip = ' '.join(tips) if tips else 'Pokračuj ve sbírání dat pro lepší insights.'

    return jsonify({
        'predicted_sessions': predicted_sessions,
        'recommended_focus': best_theme,
        'tip': tip,
        'productivity_trend': trend,
        'week_sessions': total_sessions,
        'best_theme_rating': round(best_score, 1) if best_score else None
    })


@app.route('/api/theme-recommendation/<date>')
def theme_recommendation(date):
    """
    Get recommended theme for a specific date

    Args:
        date: Date in YYYY-MM-DD format

    Returns:
        dict: Recommended theme based on day patterns
    """
    from datetime import datetime

    sessions = get_sessions()

    if not sessions:
        return jsonify({
            'recommended_theme': None,
            'reason': 'Nedostatek dat pro doporučení',
            'confidence': 0
        })

    try:
        target_date = datetime.strptime(date, '%Y-%m-%d')
        day_of_week = target_date.weekday()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    # Analyze historical patterns for this day of week
    from collections import defaultdict
    day_themes = defaultdict(lambda: {'count': 0, 'rating_sum': 0, 'rated': 0})

    for session in sessions:
        if session.get('date'):
            try:
                session_date = datetime.strptime(session['date'], '%Y-%m-%d')
                if session_date.weekday() == day_of_week:
                    cat = session.get('category', 'Other')
                    day_themes[cat]['count'] += 1
                    if session.get('productivity_rating'):
                        day_themes[cat]['rating_sum'] += session['productivity_rating']
                        day_themes[cat]['rated'] += 1
            except ValueError:
                continue

    # Score themes by combination of frequency and rating
    best_theme = None
    best_score = 0
    best_reason = ''

    for theme, stats in day_themes.items():
        if stats['count'] < 2:
            continue

        avg_rating = (stats['rating_sum'] / stats['rated']) if stats['rated'] > 0 else 50
        # Score = (normalized count * 0.3) + (normalized rating * 0.7)
        freq_score = min(stats['count'] / 5, 1) * 30
        rating_score = (avg_rating / 100) * 70
        score = freq_score + rating_score

        if score > best_score:
            best_score = score
            best_theme = theme
            if stats['rated'] > 0:
                best_reason = f"Historicky máš {round(avg_rating)}% produktivitu na {theme} v tento den."
            else:
                best_reason = f"Často pracuješ na {theme} v tento den."

    day_names = ['pondělí', 'úterý', 'středa', 'čtvrtek', 'pátek', 'sobota', 'neděle']

    return jsonify({
        'recommended_theme': best_theme,
        'reason': best_reason or f'Nemám dostatek dat pro {day_names[day_of_week]}.',
        'confidence': min(round(best_score), 100),
        'day_of_week': day_names[day_of_week]
    })


if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("  POMODORO ML SERVICE")
    print("=" * 50)

    if init_db():
        print("  MongoDB: Connected")
    else:
        print("  MongoDB: Connection failed")

    print(f"\n  API available at: http://localhost:5001/api")
    print("\n  Endpoints:")
    print("    GET  /api/health         - Health check")
    print("    GET  /api/analysis       - Full productivity analysis")
    print("    GET  /api/recommendation - Get preset recommendation")
    print("    GET  /api/prediction/today - Today's prediction")
    print("    GET  /api/prediction/week  - Weekly forecast")
    print("    GET  /api/trends         - Recent trends")
    print("    POST /api/train          - Retrain models")
    print("\n" + "=" * 50 + "\n")

    app.run(host='0.0.0.0', port=5001, debug=True)
