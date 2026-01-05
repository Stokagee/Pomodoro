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
