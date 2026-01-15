"""
Pomodoro ML Service - Flask API for productivity analysis
"""

import os
import time
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from dotenv import load_dotenv
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from models import ProductivityAnalyzer, PresetRecommender, SessionPredictor, BurnoutPredictor, FocusOptimizer, SessionQualityPredictor, PatternAnomalyDetector
from models.ai_challenge_generator import AIChallengeGenerator
from models.ai_analyzer import AIAnalyzer, CacheManager

# Structured logging for Loki
from utils.logger import logger

# Centralized Prometheus metrics
from utils.metrics import (
    ml_info,
    PREDICTION_REQUESTS, PREDICTION_ERRORS, PREDICTION_DURATION,
    AI_REQUESTS, AI_REQUEST_DURATION, AI_ERRORS,
    AI_TOKENS_INPUT, AI_TOKENS_OUTPUT, AI_COST_USD,
    CACHE_HITS, CACHE_MISSES, SESSIONS_ANALYZED
)

# Import PostgreSQL database module
import db as database

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# =============================================================================
# REQUEST LOGGING MIDDLEWARE
# =============================================================================
@app.before_request
def log_incoming_request():
    """Log incoming requests for observability."""
    # Skip metrics endpoint for noise reduction
    if request.path == '/metrics':
        return

    # Extract trace ID from X-Request-ID header for distributed tracing
    trace_id = request.headers.get('X-Request-ID')
    if trace_id:
        logger.set_trace_id(trace_id)

    request.start_time = time.time()
    logger.debug("request_received",
                 message="Incoming request",
                 context={
                     "method": request.method,
                     "path": request.path,
                     "query_args": dict(request.args),
                     "remote_addr": request.remote_addr
                 })

@app.after_request
def log_request_response(response):
    """Log completed requests with timing information."""
    # Skip metrics endpoint
    if request.path == '/metrics':
        return response

    # Calculate duration if start_time was set
    duration_ms = None
    if hasattr(request, 'start_time'):
        duration_ms = round((time.time() - request.start_time) * 1000, 2)

    # Determine log level based on status code
    if response.status_code >= 500:
        logger.error("request_completed",
                    message=f"Request completed with server error",
                    context={
                        "method": request.method,
                        "path": request.path,
                        "status": response.status_code
                    },
                    metrics={"duration_ms": duration_ms} if duration_ms else None)
    elif response.status_code >= 400:
        logger.warning("request_completed",
                      message=f"Request completed with client error",
                      context={
                          "method": request.method,
                          "path": request.path,
                          "status": response.status_code
                      },
                      metrics={"duration_ms": duration_ms} if duration_ms else None)
    else:
        logger.info("request_completed",
                    message="Request completed successfully",
                    context={
                        "method": request.method,
                        "path": request.path,
                        "status": response.status_code
                    },
                    metrics={"duration_ms": duration_ms} if duration_ms else None)

    return response

# =============================================================================
# PROMETHEUS METRICS
# =============================================================================
metrics = PrometheusMetrics(app, path=None)  # Disable automatic /metrics endpoint

@app.route('/metrics')
def prometheus_metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

# Set application info
ml_info.info({
    'version': '1.0',
    'service': 'pomodoro-ml',
    'ollama_model': os.getenv('OLLAMA_MODEL', 'qwen2.5:14b')
})

# Database connection status
db_connected = False

# AI Challenge Generator (singleton)
ai_generator = AIChallengeGenerator()

# AI Analyzer (singleton - initialized after DB connection)
ai_analyzer = None


def init_db():
    """Initialize PostgreSQL connection and AI Analyzer"""
    global db_connected, ai_analyzer
    try:
        db_connected = database.init_db()
        if db_connected:
            logger.db_connected("PostgreSQL")

            # Initialize AI Analyzer
            ai_analyzer = AIAnalyzer()
            logger.info("AI_ANALYZER_INITIALIZED", message="AI Analyzer initialized successfully", context={"model": os.getenv('OLLAMA_MODEL', 'qwen2.5:14b')})

            # Clear AI cache on startup (docker-compose up)
            try:
                deleted = database.clear_all_cache()
                logger.cache_invalidated("all", "startup", deleted)
            except Exception as e:
                logger.warning("CACHE_CLEAR_FAILED", message="Could not clear AI cache on startup", error={"type": "CacheError", "message": str(e)})

            return True
        return False
    except Exception as e:
        logger.error("DB_INIT_FAILED", message="PostgreSQL connection failed", exception=e)
        return False


def get_sessions():
    """Get all completed sessions from database"""
    if not db_connected:
        return []

    return database.get_sessions(completed_only=True)


def get_rich_context_for_ai():
    """
    Načte bohatý kontext pro AI doporučení.
    Obsahuje týdenní statistiky, produktivitu, rozložení kategorií a poslední dokončené úkoly.
    """
    if not db_connected:
        return {
            'weekly_total': 0,
            'avg_productivity': 0,
            'categories': {},
            'streak': 0,
            'recent_tasks': [],
            'recent_topics': [],
            'last_session_hours_ago': None
        }

    try:
        from datetime import datetime, timedelta

        sessions = database.get_sessions_with_notes(30)  # posledních 30 dní pro více historie

        # Spočítat statistiky
        categories = {}
        total_productivity = 0
        productivity_count = 0

        for s in sessions:
            cat = s.get('category', 'Other')
            categories[cat] = categories.get(cat, 0) + 1
            if s.get('productivity_rating'):
                total_productivity += s['productivity_rating']
                productivity_count += 1

        # Spočítat streak (po sobě jdoucí dny s alespoň 1 session)
        streak = 0
        today = datetime.now().date()
        dates_with_sessions = set(s.get('date') for s in sessions if s.get('date'))

        for i in range(30):  # max 30 dní zpět
            check_date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
            if check_date in dates_with_sessions:
                streak += 1
            elif i > 0:  # První den (dnes) může být prázdný
                break

        # NEW: Získat posledních 10 dokončených tasks pro vyhnutí se opakováním
        recent_tasks = []
        recent_topics = []
        now = datetime.now()

        for s in sessions[:10]:  # Prvních 10 (nejnovější)
            task = s.get('task', '').strip()
            category = s.get('category', 'Other')
            session_date = s.get('date', '')
            session_time = s.get('time', '')

            if task:  # Pouze tasks s názvem
                # Vypočitat jak dávno to bylo
                hours_ago = None
                if session_date:
                    try:
                        # Parse date and time
                        if session_time:
                            dt_str = f"{session_date} {session_time}"
                            session_dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M')
                        else:
                            session_dt = datetime.strptime(session_date, '%Y-%m-%d')
                        hours_ago = (now - session_dt).total_seconds() / 3600
                    except:
                        hours_ago = None

                recent_tasks.append({
                    'task': task,
                    'category': category,
                    'date': session_date,
                    'hours_ago': hours_ago
                })
                recent_topics.append(task)

        # Vypočitat čas od poslední session
        last_session_hours_ago = None
        if sessions:
            last_s = sessions[0]  # První je nejnovější
            last_date = last_s.get('date', '')
            last_time = last_s.get('time', '')
            if last_date:
                try:
                    if last_time:
                        dt_str = f"{last_date} {last_time}"
                        last_dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M')
                    else:
                        last_dt = datetime.strptime(last_date, '%Y-%m-%d')
                    last_session_hours_ago = (now - last_dt).total_seconds() / 3600
                except:
                    pass

        return {
            'weekly_total': len(sessions),
            'avg_productivity': round(total_productivity / productivity_count, 1) if productivity_count > 0 else 0,
            'categories': categories,
            'streak': streak,
            'recent_tasks': recent_tasks,
            'recent_topics': recent_topics,
            'last_session_hours_ago': last_session_hours_ago
        }
    except Exception as e:
        logger.warning("RICH_CONTEXT_ERROR", message="Error getting rich context", error={"type": "ContextError", "message": str(e)})
        return {
            'weekly_total': 0,
            'avg_productivity': 0,
            'categories': {},
            'streak': 0,
            'recent_tasks': [],
            'recent_topics': [],
            'last_session_hours_ago': None
        }


@app.route('/api/health')
@metrics.do_not_track()
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'pomodoro-ml',
        'database': 'connected' if db_connected else 'disconnected'
    })


@app.route('/api/config/categories', methods=['POST'])
def set_categories():
    """Receive categories from web service for AI prompts.

    This endpoint allows the web service to pass user's configured
    categories so AI prompts use the correct category list.
    Updates both AIAnalyzer and AIChallengeGenerator.
    """
    global ai_analyzer, ai_generator

    data = request.get_json() or {}
    categories = data.get('categories', [])

    updated_components = []

    # Update AIAnalyzer
    if ai_analyzer is not None:
        ai_analyzer.update_categories(categories)
        updated_components.append('ai_analyzer')

    # Update AIChallengeGenerator (for next-session suggestions)
    if ai_generator is not None:
        ai_generator.update_categories(categories)
        updated_components.append('ai_generator')

    if updated_components:
        return jsonify({
            'status': 'ok',
            'categories_count': len(categories),
            'categories': categories,
            'updated_components': updated_components
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'No AI components initialized'
        }), 503


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
    start_time = time.time()
    PREDICTION_REQUESTS.labels(prediction_type='recommendation').inc()

    try:
        category = request.args.get('category')
        sessions = get_sessions()
        SESSIONS_ANALYZED.set(len(sessions))
        recommender = PresetRecommender(sessions)
        rec = recommender.recommend(category=category)
        latency_ms = int((time.time() - start_time) * 1000)
        PREDICTION_DURATION.labels(prediction_type='recommendation').observe(time.time() - start_time)

        # === STRUCTURED LOGGING ===
        logger.ml_recommendation(
            preset=rec.get('recommended_preset', 'unknown'),
            confidence=rec.get('confidence', 0),
            reason=rec.get('reason', ''),
            latency_ms=latency_ms,
            category=category
        )

        return jsonify(rec)
    except Exception as e:
        PREDICTION_ERRORS.labels(prediction_type='recommendation', error_type=type(e).__name__).inc()
        logger.error("ML_ERROR", f"Recommendation failed: {str(e)}", error={"type": type(e).__name__, "message": str(e)})
        raise


@app.route('/api/prediction/today')
def prediction_today():
    """
    Get prediction for today

    Returns:
        dict: Predicted sessions and productivity for today
    """
    start_time = time.time()
    PREDICTION_REQUESTS.labels(prediction_type='today').inc()

    try:
        sessions = get_sessions()
        SESSIONS_ANALYZED.set(len(sessions))
        predictor = SessionPredictor(sessions)
        prediction = predictor.predict_today()
        PREDICTION_DURATION.labels(prediction_type='today').observe(time.time() - start_time)
        return jsonify(prediction)
    except Exception as e:
        PREDICTION_ERRORS.labels(prediction_type='today', error_type=type(e).__name__).inc()
        raise


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


@app.route('/api/burnout-risk')
def burnout_risk():
    """
    Get burnout risk assessment

    Returns:
        dict: Risk score, level, factors, and recommendations
    """
    start_time = time.time()
    sessions = get_sessions()
    predictor = BurnoutPredictor(sessions)
    result = predictor.predict_burnout()
    latency_ms = int((time.time() - start_time) * 1000)

    # === STRUCTURED LOGGING ===
    logger.burnout_risk(
        risk_level=result.get('risk_level', 'unknown'),
        risk_score=result.get('risk_score', 0),
        top_factors=result.get('risk_factors', []),
        latency_ms=latency_ms
    )

    return jsonify(result)


@app.route('/api/optimal-schedule')
def optimal_schedule():
    """
    Focus Optimizer - Generate optimal work schedule

    Query params:
        sessions: Number of sessions to schedule (1-12, default: 6)
        day: Day of week or 'today' (default: 'today')
             Options: today, monday, tuesday, wednesday, thursday, friday, saturday, sunday
                      or Czech: pondeli, utery, streda, ctvrtek, patek, sobota, nedele

    Returns:
        dict: Optimal schedule with peak hours, avoid hours, and recommendations
    """
    from datetime import datetime

    # Parse parameters
    num_sessions = request.args.get('sessions', 6, type=int)
    day_param = request.args.get('day', 'today').lower()

    # Validate sessions (1-12 reasonable range)
    num_sessions = max(1, min(12, num_sessions))

    # Parse day parameter
    day_map = {
        'monday': 0, 'pondeli': 0, 'pondělí': 0,
        'tuesday': 1, 'utery': 1, 'úterý': 1,
        'wednesday': 2, 'streda': 2, 'středa': 2,
        'thursday': 3, 'ctvrtek': 3, 'čtvrtek': 3,
        'friday': 4, 'patek': 4, 'pátek': 4,
        'saturday': 5, 'sobota': 5,
        'sunday': 6, 'nedele': 6, 'neděle': 6,
        'today': datetime.now().weekday()
    }

    target_day = day_map.get(day_param, datetime.now().weekday())

    try:
        # Get sessions and create optimizer
        sessions = get_sessions()
        optimizer = FocusOptimizer(sessions)
        result = optimizer.analyze(day=target_day, num_sessions=num_sessions)
        return jsonify(result)
    except Exception as e:
        logger.warning("OPTIMAL_SCHEDULE_ERROR", message="Error in optimal-schedule", error={"type": "ScheduleError", "message": str(e)})
        return jsonify({
            'error': str(e),
            'date': datetime.now().strftime('%Y-%m-%d'),
            'peak_hours': [],
            'avoid_hours': [],
            'optimal_schedule': {'sessions': []},
            'confidence': 0
        }), 500


@app.route('/api/predict-quality', methods=['POST', 'GET'])
def predict_quality():
    """
    Session Quality Predictor - Predict expected productivity BEFORE session starts

    Query params (GET) or JSON body (POST):
        hour: Current hour (0-23, default: current)
        day: Day of week (0=Mon to 6=Sun, default: today)
        preset: Preset name (default: 'deep_work')
        category: Category name (optional)
        sessions_today: Number of completed sessions today (default: 0)
        minutes_since_last: Minutes since last session ended (optional)
        wellness: Today's wellness check-in data (optional, POST only)

    Returns:
        dict: Prediction with factors, confidence, and recommendation
    """
    from datetime import datetime

    # Get parameters from either JSON body or query params
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
    else:
        data = {}

    # Parse parameters with defaults (use 'is None' to handle 0 values correctly)
    now = datetime.now()

    hour = data.get('hour')
    if hour is None:
        hour = request.args.get('hour', type=int)
    if hour is None:
        hour = now.hour

    day = data.get('day')
    if day is None:
        day = request.args.get('day', type=int)
    if day is None:
        day = now.weekday()

    preset = data.get('preset') or request.args.get('preset', 'deep_work')
    category = data.get('category') or request.args.get('category')

    sessions_today = data.get('sessions_today')
    if sessions_today is None:
        sessions_today = request.args.get('sessions_today', 0, type=int)

    minutes_since_last = data.get('minutes_since_last')
    if minutes_since_last is None:
        minutes_since_last = request.args.get('minutes_since_last', type=int)

    # Wellness data (only available via POST with JSON body)
    wellness_data = data.get('wellness')

    try:
        sessions = get_sessions()
        predictor = SessionQualityPredictor(sessions)
        result = predictor.predict(
            hour=hour,
            day=day,
            preset=preset,
            category=category,
            sessions_today=sessions_today,
            minutes_since_last=minutes_since_last,
            wellness_data=wellness_data
        )
        return jsonify(result)
    except Exception as e:
        logger.warning("QUALITY_PREDICTION_ERROR", message="Error in predict-quality", error={"type": "PredictionError", "message": str(e)})
        return jsonify({
            'error': str(e),
            'predicted_productivity': 70.0,
            'confidence': 0,
            'factors': [],
            'recommendation': {
                'type': 'info',
                'message': 'Nelze načíst predikci',
                'action': 'Zkuste to znovu',
                'icon': '⚠️'
            }
        }), 500


@app.route('/api/detect-anomalies', methods=['GET'])
def detect_anomalies():
    """
    Pattern Anomaly Detector - Detect unusual patterns in user behavior

    Detects 6 anomaly types:
    - productivity_drop: Sudden decline in productivity
    - unusual_hours: Working outside normal schedule
    - category_shift: Change in preferred categories
    - streak_break: Missing days after long streak
    - overwork_spike: Sudden increase in work intensity
    - quality_decline: Drop in session ratings

    Returns:
        dict: Detected anomalies with severity, recommendations, and proactive tips
    """
    try:
        start_time = time.time()
        sessions = get_sessions()
        detector = PatternAnomalyDetector(sessions)
        result = detector.detect_all()
        latency_ms = int((time.time() - start_time) * 1000)

        # === STRUCTURED LOGGING ===
        for anomaly in result.get('anomalies', []):
            logger.anomaly_detected(
                anomaly_type=anomaly.get('type', 'unknown'),
                severity=anomaly.get('severity', 'low'),
                description=anomaly.get('description', ''),
                recommendation=anomaly.get('recommendation')
            )

        return jsonify(result)
    except Exception as e:
        logger.error("ANOMALY_DETECTION_ERROR", message="Error in detect-anomalies", exception=e)
        return jsonify({
            'error': str(e),
            'anomalies_detected': 0,
            'overall_status': 'error',
            'anomalies': [],
            'proactive_tips': [],
            'confidence': 0.0,
            'metadata': {
                'model_version': '1.0',
                'error_message': str(e)
            }
        }), 500


@app.route('/api/debug/diversity', methods=['GET'])
def debug_diversity():
    """Debug endpoint to test diversity detection."""
    try:
        from models.diversity_detector import DiversityDetector
        from datetime import datetime, timedelta

        # Get recent sessions - already ordered DESC (newest first)
        sessions = get_sessions()

        # Create detector with current categories
        categories = ai_generator.categories if ai_generator else []
        detector = DiversityDetector(categories=categories)

        # Show what sessions we're analyzing
        recent_sessions = sessions[:20]  # First 20 are most recent
        cutoff_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')

        # Test detection
        result = detector.detect_category_overload(
            sessions=recent_sessions,
            days=2,
            threshold=0.70
        )

        return jsonify({
            'status': 'ok',
            'cutoff_date': cutoff_date,
            'ai_generator_categories': categories,
            'detector_categories': detector.categories,
            'recent_sessions': [{'date': s.get('date'), 'category': s.get('category')} for s in recent_sessions[:10]],
            'total_sessions_in_db': len(sessions),
            'total_sessions_analyzed': len(recent_sessions),
            'diversity_result': result
        })
    except Exception as e:
        import traceback
        return jsonify({
            'status': 'error',
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


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
    burnout_predictor = BurnoutPredictor(sessions)

    analysis = analyzer.analyze()
    recommendation = recommender.recommend()
    prediction = predictor.predict_today()
    trends = predictor.get_trends()
    burnout = burnout_predictor.predict_burnout()

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
        'trends': trends,
        'burnout': {
            'risk_score': burnout['risk_score'],
            'risk_level': burnout['risk_level'],
            'top_factor': burnout['risk_factors'][0] if burnout['risk_factors'] else None
        }
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


# === AI Challenge Generation Endpoints ===

@app.route('/api/ai/health')
def ai_health():
    """
    Check AI (Ollama) service health

    Returns:
        dict: Status of Ollama connection and model availability
    """
    return jsonify(ai_generator.health_check())


@app.route('/api/ai/daily-challenge')
def ai_daily_challenge():
    """
    Get AI-generated daily challenge

    Query params:
        level: User level (default: 1)
        avg_sessions: Average daily sessions (default: 3)
        top_category: User's top category (default: Coding)
        streak: Current streak days (default: 0)

    Returns:
        dict: Daily challenge with title, description, target, xp_reward
    """
    user_context = {
        'level': request.args.get('level', 1, type=int),
        'avg_sessions': request.args.get('avg_sessions', 3, type=float),
        'top_category': request.args.get('top_category', 'Coding'),
        'streak': request.args.get('streak', 0, type=int),
        'weak_areas': request.args.get('weak_areas', 'zadna data')
    }

    challenge = ai_generator.generate_daily_challenge(user_context)
    return jsonify(challenge)


@app.route('/api/ai/weekly-quest')
def ai_weekly_quest():
    """
    Get AI-generated weekly quests

    Query params:
        level: User level (default: 1)
        xp: User total XP (default: 0)
        weekly_avg: Average weekly sessions (default: 15)

    Returns:
        list: Array of weekly quests
    """
    user_profile = {
        'level': request.args.get('level', 1, type=int),
        'xp': request.args.get('xp', 0, type=int),
        'weekly_avg': request.args.get('weekly_avg', 15, type=float),
        'best_categories': request.args.getlist('best_categories') or (ai_generator.categories[:1] if ai_generator.categories else ['Other'])
    }

    quests = ai_generator.generate_weekly_quests(user_profile)
    return jsonify(quests)


@app.route('/api/ai/motivation')
def ai_motivation():
    """
    Get AI-generated motivation message

    Query params:
        sessions_today: Today's completed sessions (default: 0)
        streak: Current streak days (default: 0)
        mood: Current mood (default: neutralni)

    Returns:
        dict: Motivation message
    """
    context = {
        'sessions_today': request.args.get('sessions_today', 0, type=int),
        'streak': request.args.get('streak', 0, type=int),
        'mood': request.args.get('mood', 'neutralni')
    }

    message = ai_generator.generate_motivation_message(context)
    return jsonify({'message': message})


@app.route('/api/ai/achievement-focus')
def ai_achievement_focus():
    """
    Get AI suggestion for which achievement to focus on

    This endpoint requires achievements data to be passed as JSON body
    or fetched from the database.

    Returns:
        dict: Suggested achievement with reason
    """
    # Try to get achievements from database
    if db_connected:
        try:
            achievements = database.get_achievements()
        except Exception as e:
            logger.warning("ACHIEVEMENTS_FETCH_ERROR", message="Error fetching achievements", error={"type": "FetchError", "message": str(e)})
            achievements = []
    else:
        achievements = []

    suggestion = ai_generator.suggest_achievement_focus(achievements)
    return jsonify(suggestion)


# === FocusAI - Learning Recommendation Endpoints ===

@app.route('/api/ai/learning-recommendations', methods=['POST'])
def ai_learning_recommendations():
    """
    FocusAI: Generate comprehensive learning recommendations

    Expects JSON body with user analytics data:
    {
        "recent_sessions": [...],
        "category_distribution": {...},
        "skill_levels": [...],
        "streak_data": {...},
        "recent_tasks": [...],
        "productivity_by_time": {...},
        "achievements_progress": [...],
        "user_profile": {...}
    }

    Returns:
        dict: LearningRecommendation with skill_gaps, recommended_topics,
              category_balance, personalized_tips, next_session_suggestion,
              user_knowledge, motivational_message, analysis_summary
    """
    try:
        user_data = request.get_json() or {}

        # If no data provided, try to gather from database
        if not user_data and db is not None:
            user_data = _gather_user_analytics()

        result = ai_generator.generate_learning_recommendations(user_data)
        return jsonify(result)
    except Exception as e:
        logger.warning("LEARNING_RECOMMENDATIONS_ERROR", message="Error in learning-recommendations", error={"type": "MLError", "message": str(e)})
        from models.pydantic_models import FallbackSuggestion
        return jsonify(FallbackSuggestion.get_learning_recommendation())


@app.route('/api/ai/next-session-suggestion', methods=['GET'])
def ai_next_session_suggestion():
    """
    FocusAI: Quick suggestion for next session (optimized for timer start)

    Query params:
        category: Last used category (optional)
        task: Last task description (optional)
        hour: Current hour 0-23 (default: current hour)
        sessions: Sessions completed today (default: 0)
        exclude_topic: Topic to exclude - for "Jiný nápad" functionality (optional)
        bypass_cache: Force refresh without cache (default: false)

    Returns:
        dict: SessionSuggestion with category, topic, preset, reason, confidence
    """
    from datetime import datetime

    try:
        # Základní kontext z parametrů
        hour = request.args.get('hour', datetime.now().hour, type=int)
        day_of_week = datetime.now().weekday()  # 0=Po, 6=Ne
        day_names = ['Pondeli', 'Utery', 'Streda', 'Ctvrtek', 'Patek', 'Sobota', 'Nedele']

        # Get exclude_topic for "Jiný nápad" functionality
        exclude_topic = request.args.get('exclude_topic', '')

        # Get bypass_cache for force refresh
        bypass_cache = request.args.get('bypass_cache', 'false').lower() == 'true'

        # Update categories from request (from user's config.json)
        categories_param = request.args.get('categories', '')
        if categories_param:
            categories = [c.strip() for c in categories_param.split(',') if c.strip()]
            if categories:
                ai_generator.update_categories(categories)
                logger.info("CATEGORIES_UPDATED", message="Updated AI categories from request", context={"categories": categories})

        # Bohatý kontext z databáze
        rich_context = get_rich_context_for_ai()

        # Get recent sessions directly for diversity detection
        recent_sessions = get_sessions()[:20]  # Last 20 sessions

        context = {
            'last_category': request.args.get('category', ''),
            'last_task': request.args.get('task', ''),
            'time_of_day': hour,
            'day_of_week': day_of_week,
            'day_name': day_names[day_of_week],
            'sessions_today': request.args.get('sessions', 0, type=int),
            # Bohatší kontext
            'weekly_stats': rich_context,
            # Recent sessions for diversity detection
            'recent_sessions': recent_sessions,
            'user_profile': {
                'role': 'Tester',
                'style': 'pragmatic',
                'goals': ['productivity', 'learning', 'balance']
            },
            # Exclude topic for "Jiný nápad"
            'exclude_topic': exclude_topic,
            # Force refresh without cache
            'bypass_cache': bypass_cache
        }

        result = ai_generator.suggest_next_session_topic(context)
        return jsonify(result)
    except Exception as e:
        logger.warning("NEXT_SESSION_ERROR", message="Error in next-session-suggestion", error={"type": "MLError", "message": str(e)})
        from models.pydantic_models import FallbackSuggestion
        return jsonify(FallbackSuggestion.get_session_suggestion(
            request.args.get('category'),
            datetime.now().hour
        ))


@app.route('/api/ai/expand-suggestion', methods=['POST'])
def ai_expand_suggestion():
    """
    FocusAI: Expand a previous suggestion with more details

    Expects JSON body:
    {
        "suggestion": {
            "category": "Learning",
            "topic": "Robot Framework basics",
            "reason": "Improve automation skills"
        },
        "question_type": "resources|steps|time_estimate|connection"
    }

    Question types:
    - resources: Learning materials, documentation, tutorials, YouTube
    - steps: Concrete action steps (what to do)
    - time_estimate: How long it takes (sessions/hours)
    - connection: How it connects to job hunting/career goals

    Returns:
        dict: {
            "answer": "Detailed answer with bullet points",
            "type": "resources",
            "icon": "📚",
            "confidence": 0.85,
            "ai_generated": true
        }
    """
    try:
        data = request.get_json() or {}
        suggestion = data.get('suggestion', {})
        question_type = data.get('question_type', 'resources')
        category = suggestion.get('category', '')

        if not suggestion.get('topic'):
            return jsonify({
                'error': 'Missing suggestion.topic',
                'answer': 'Chybí téma k rozšíření.',
                'confidence': 0
            }), 400

        # Get REAL user data from database
        user_context = {}
        try:
            # Get sessions from last 30 days
            all_sessions = database.get_sessions_with_notes(30)

            # Filter sessions for the suggested category
            category_sessions = [
                s for s in all_sessions
                if s.get('category', '').lower() == category.lower()
            ]

            # Also get all tasks for broader context
            all_tasks = [s.get('task') for s in all_sessions if s.get('task')]

            # Extract unique tools/technologies from tasks
            user_tools = ['Postman', 'Robot Framework', 'DBeaver', 'SOAP UI']  # defaults

            user_context = {
                'recent_tasks': [s.get('task') for s in category_sessions if s.get('task')][:10],
                'category_sessions': category_sessions[:5],
                'user_tools': user_tools,
                'all_recent_tasks': all_tasks[:20]  # broader context
            }
            logger.debug("EXPAND_CONTEXT", message="User context gathered", context={"category": category, "sessions_count": len(category_sessions)})
        except Exception as e:
            logger.warning("EXPAND_CONTEXT_WARNING", message="Could not get user context", error={"type": "ContextError", "message": str(e)})

        result = ai_generator.expand_suggestion(suggestion, question_type, user_context)
        return jsonify(result)
    except Exception as e:
        logger.warning("EXPAND_SUGGESTION_ERROR", message="Error in expand-suggestion", error={"type": "MLError", "message": str(e)})
        return jsonify({
            'answer': 'AI dočasně nedostupná. Zkus to později.',
            'type': 'error',
            'icon': '⚠️',
            'confidence': 0,
            'ai_generated': False,
            'error': str(e)
        }), 500


@app.route('/api/ai/extract-topics', methods=['POST'])
def ai_extract_topics():
    """
    FocusAI: Extract technologies, concepts, and expertise areas from task history

    Expects JSON body:
    {
        "tasks": [
            {"task": "React hooks refactoring", "category": "Coding"},
            {"task": "Python async learning", "category": "Learning"},
            ...
        ]
    }

    Returns:
        dict: UserKnowledge with technologies, concepts, expertise_areas
    """
    try:
        data = request.get_json() or {}
        tasks = data.get('tasks', [])

        # If no tasks provided, try to get from database
        if not tasks and db_connected:
            try:
                sessions = database.get_sessions_with_notes(30)
                tasks = [
                    {'task': s.get('task', ''), 'category': s.get('category', '')}
                    for s in sessions[:100]
                    if s.get('task')
                ]
            except Exception as e:
                logger.warning("TASKS_FETCH_ERROR", message="Error fetching tasks", error={"type": "FetchError", "message": str(e)})
                tasks = []

        result = ai_generator.extract_topics_from_tasks(tasks)
        return jsonify(result)
    except Exception as e:
        logger.warning("EXTRACT_TOPICS_ERROR", message="Error in extract-topics", error={"type": "MLError", "message": str(e)})
        return jsonify({
            "technologies": [],
            "concepts": [],
            "expertise_areas": []
        })


@app.route('/api/ai/analyze-patterns', methods=['POST'])
def ai_analyze_patterns():
    """
    FocusAI: Analyze productivity patterns and provide recommendations

    Expects JSON body:
    {
        "hourly_productivity": {...},
        "daily_stats": {...}
    }

    Returns:
        dict: PatternAnalysis with productivity stats, recommendations, warnings
    """
    try:
        data = request.get_json() or {}

        # If no data provided, try to gather from database
        if not data and db is not None:
            data = _gather_productivity_data()

        result = ai_generator.analyze_productivity_patterns(data)
        return jsonify(result)
    except Exception as e:
        logger.warning("ANALYZE_PATTERNS_ERROR", message="Error in analyze-patterns", error={"type": "MLError", "message": str(e)})
        return jsonify({
            "productivity": {
                "best_hours": [9, 10, 14],
                "worst_hours": [12, 13, 22],
                "best_day": "Unknown",
                "avg_sessions_per_day": 0,
                "consistency_score": 0
            },
            "recommendations": [],
            "warnings": []
        })


def _gather_user_analytics() -> dict:
    """Helper to gather user analytics from database for AI"""
    if not db_connected:
        return {}

    from datetime import datetime, timedelta
    from collections import defaultdict

    try:
        # Get recent sessions (last 30 days)
        recent_sessions = database.get_sessions_with_notes(30)

        # Calculate category distribution
        cat_stats = defaultdict(lambda: {'sessions': 0, 'minutes': 0})
        total_sessions = len(recent_sessions)

        for s in recent_sessions:
            cat = s.get('category', 'Other')
            cat_stats[cat]['sessions'] += 1
            cat_stats[cat]['minutes'] += s.get('duration_minutes', 0)

        category_distribution = {}
        for cat, stats in cat_stats.items():
            category_distribution[cat] = {
                'percentage': round(stats['sessions'] / total_sessions * 100, 1) if total_sessions > 0 else 0,
                'sessions': stats['sessions'],
                'minutes': stats['minutes']
            }

        # Get skill levels
        skill_levels = database.get_skill_levels()

        # Get recent tasks
        recent_tasks = [
            {'task': s.get('task', ''), 'category': s.get('category', '')}
            for s in recent_sessions[:100]
            if s.get('task')
        ]

        # Get user profile
        user_profile = database.get_user_profile()

        return {
            'recent_sessions': recent_sessions[:100],
            'category_distribution': category_distribution,
            'skill_levels': skill_levels,
            'streak_data': {},
            'recent_tasks': recent_tasks,
            'productivity_by_time': {},
            'achievements_progress': [],
            'user_profile': user_profile
        }
    except Exception as e:
        logger.warning("USER_ANALYTICS_ERROR", message="Error gathering user analytics", error={"type": "AnalyticsError", "message": str(e)})
        return {}


def _gather_productivity_data() -> dict:
    """Helper to gather productivity data for pattern analysis"""
    if not db_connected:
        return {}

    from datetime import datetime, timedelta
    from collections import defaultdict

    try:
        # Get sessions from last 14 days
        sessions = database.get_sessions_with_notes(14)

        # Calculate hourly stats
        hourly_stats = defaultdict(lambda: {'sessions': 0, 'ratings': []})
        daily_stats = defaultdict(lambda: {'sessions': 0, 'minutes': 0})

        for s in sessions:
            hour = s.get('hour', 12)
            date = s.get('date', '')

            hourly_stats[hour]['sessions'] += 1
            if s.get('productivity_rating'):
                hourly_stats[hour]['ratings'].append(s['productivity_rating'])

            if date:
                daily_stats[date]['sessions'] += 1
                daily_stats[date]['minutes'] += s.get('duration_minutes', 0)

        return {
            'hourly_productivity': dict(hourly_stats),
            'daily_stats': dict(daily_stats)
        }
    except Exception as e:
        logger.warning("PRODUCTIVITY_DATA_ERROR", message="Error gathering productivity data", error={"type": "DataError", "message": str(e)})
        return {}


# =============================================================================
# SEMANTIC SEARCH ENDPOINT (pgvector)
# =============================================================================

@app.route('/api/semantic-search')
def semantic_search():
    """
    Search session notes semantically using pgvector.

    Query params:
        query: Search query text (required)
        limit: Maximum results (default: 10)
        min_similarity: Minimum similarity threshold 0-1 (default: 0.4)
        days: Days back to search (default: 30)

    Returns:
        dict: Search results with similar sessions
    """
    query = request.args.get('query', '')
    if not query:
        return jsonify({'error': 'Query parameter required'}), 400

    limit = request.args.get('limit', 10, type=int)
    min_similarity = request.args.get('min_similarity', 0.4, type=float)
    days = request.args.get('days', 30, type=int)

    try:
        from services.embedding_service import embedding_service

        # Generate embedding for query
        query_embedding = embedding_service.embed(query)
        if not query_embedding:
            return jsonify({
                'error': 'Could not generate embedding',
                'results': []
            }), 500

        # Search
        results = database.semantic_search_sessions(
            query_embedding,
            limit=limit,
            min_similarity=min_similarity,
            days_back=days
        )

        return jsonify({
            'query': query,
            'results': results,
            'count': len(results),
            'model': embedding_service.model_name,
            'dimensions': embedding_service.dimensions
        })

    except ImportError:
        return jsonify({
            'error': 'Embedding service not available',
            'results': []
        }), 503
    except Exception as e:
        logger.warning("SEMANTIC_SEARCH_ERROR", message="Semantic search error", error={"type": "SearchError", "message": str(e)})
        return jsonify({
            'error': str(e),
            'results': []
        }), 500


@app.route('/api/embedding/health')
def embedding_health():
    """Check embedding service health."""
    try:
        from services.embedding_service import embedding_service
        return jsonify(embedding_service.health_check())
    except ImportError:
        return jsonify({
            'status': 'not_available',
            'error': 'Embedding service not installed'
        }), 503
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


# =============================================================================
# NEW AI ANALYZER ENDPOINTS (Full LLM Analysis)
# =============================================================================

@app.route('/api/ai/v2/health')
def ai_v2_health():
    """Health check for new AI Analyzer"""
    if ai_analyzer is None:
        return jsonify({'status': 'not_initialized', 'message': 'AI Analyzer not initialized'}), 503
    return jsonify(ai_analyzer.health_check())


@app.route('/api/ai/morning-briefing')
def ai_morning_briefing():
    """
    Get AI-generated morning briefing with predictions and recommendations.
    Full LLM analysis with session notes from last 30 days.
    """
    if ai_analyzer is None:
        return jsonify({'error': 'AI Analyzer not initialized'}), 503

    try:
        result = ai_analyzer.morning_briefing()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e), 'fallback': True}), 500


@app.route('/api/ai/evening-review')
def ai_evening_review():
    """
    Get AI-generated evening review and reflection.
    Analyzes today's sessions and provides insights for tomorrow.
    """
    if ai_analyzer is None:
        return jsonify({'error': 'AI Analyzer not initialized'}), 503

    try:
        result = ai_analyzer.evening_review()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e), 'fallback': True}), 500


@app.route('/api/ai/integrated-insight')
def ai_integrated_insight():
    """
    Get cross-model integrated recommendation.
    Combines burnout, anomaly, productivity, and schedule analyses.
    """
    if ai_analyzer is None:
        return jsonify({'error': 'AI Analyzer not initialized'}), 503

    try:
        result = ai_analyzer.integrated_insight()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e), 'fallback': True}), 500


@app.route('/api/ai/analyze-burnout')
def ai_analyze_burnout():
    """
    Full LLM burnout risk analysis with notes context.
    Analyzes session notes for burnout signals and provides recovery plan.
    """
    if ai_analyzer is None:
        return jsonify({'error': 'AI Analyzer not initialized'}), 503

    try:
        result = ai_analyzer.analyze_burnout()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e), 'fallback': True}), 500


@app.route('/api/ai/analyze-anomalies')
def ai_analyze_anomalies():
    """
    Full LLM anomaly detection.
    Detects unusual patterns in behavior including notes sentiment analysis.
    """
    if ai_analyzer is None:
        return jsonify({'error': 'AI Analyzer not initialized'}), 503

    try:
        result = ai_analyzer.analyze_anomalies()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e), 'fallback': True}), 500


@app.route('/api/ai/analyze-quality', methods=['GET', 'POST'])
def ai_analyze_quality():
    """
    Full LLM quality prediction before session start.

    Query params / JSON body:
        preset: Preset to use (default: deep_work)
        category: Optional category for context
    """
    if ai_analyzer is None:
        return jsonify({'error': 'AI Analyzer not initialized'}), 503

    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            preset = data.get('preset', 'deep_work')
            category = data.get('category')
        else:
            preset = request.args.get('preset', 'deep_work')
            category = request.args.get('category')

        result = ai_analyzer.analyze_quality(preset, category)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e), 'fallback': True}), 500


@app.route('/api/ai/optimal-schedule-ai')
def ai_optimal_schedule():
    """
    Full LLM schedule optimization.

    Query params:
        day: Day to optimize (default: today)
        sessions: Number of sessions to plan (default: 6)
    """
    if ai_analyzer is None:
        return jsonify({'error': 'AI Analyzer not initialized'}), 503

    try:
        day = request.args.get('day', 'today')
        sessions = int(request.args.get('sessions', 6))
        sessions = max(1, min(sessions, 12))

        result = ai_analyzer.get_optimal_schedule(day, sessions)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e), 'fallback': True}), 500


@app.route('/api/ai/learning-v2')
def ai_learning_v2():
    """
    Full LLM learning recommendations.
    Analyzes session notes for learning patterns and gaps.
    """
    if ai_analyzer is None:
        return jsonify({'error': 'AI Analyzer not initialized'}), 503

    try:
        result = ai_analyzer.get_learning_recommendations()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e), 'fallback': True}), 500


@app.route('/api/ai/invalidate-cache', methods=['POST'])
def ai_invalidate_cache():
    """
    Invalidate all AI caches.
    Called automatically when a new session is logged or when user requests new suggestion.
    """
    total_invalidated = 0

    try:
        # Invalidate ai_analyzer cache
        if ai_analyzer is not None:
            total_invalidated += ai_analyzer.cache.invalidate_all()

        # Invalidate ai_generator cache (for next_session suggestions)
        if ai_generator is not None:
            total_invalidated += ai_generator.clear_cache()

        return jsonify({
            'status': 'invalidated',
            'invalidated_count': total_invalidated,
            'message': f'Invalidated {total_invalidated} cache entries'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/cache-status')
def ai_cache_status():
    """Get current AI cache status."""
    if ai_analyzer is None:
        return jsonify({'error': 'AI Analyzer not initialized'}), 503

    try:
        status = ai_analyzer.cache.get_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    logger.info("ML_SERVICE_STARTUP", message="Pomodoro ML Service starting", context={
        "version": "2.0",
        "api_url": "http://localhost:5002/api"
    })

    if init_db():
        logger.db_connected("PostgreSQL")
    else:
        logger.critical("DB_CONNECTION_FAILED", message="PostgreSQL connection failed for ML service")

    logger.info("ML_SERVICE_READY", message="ML service ready to accept requests", context={
        "endpoints": {
            "health": "/api/health",
            "analysis": "/api/analysis",
            "recommendation": "/api/recommendation",
            "prediction": "/api/prediction/today",
            "burnout_risk": "/api/burnout-risk",
            "optimal_schedule": "/api/optimal-schedule",
            "predict_quality": "/api/predict-quality",
            "detect_anomalies": "/api/detect-anomalies",
            "ai_endpoints": "/api/ai/*"
        }
    })

    app.run(host='0.0.0.0', port=5002, debug=True)
