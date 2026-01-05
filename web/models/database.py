"""
MongoDB Database Connection and Operations
"""

import os
from datetime import datetime, date, timedelta
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

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
        print(f"Connected to MongoDB: {MONGO_URI}")

        # Create indexes
        db.sessions.create_index([("date", -1)])
        db.sessions.create_index([("category", 1)])
        db.sessions.create_index([("preset", 1)])
        db.sessions.create_index([("completed", 1)])
        db.sessions.create_index([("date", -1), ("completed", 1)])

        return True
    except ConnectionFailure as e:
        print(f"MongoDB connection failed: {e}")
        return False


def get_db():
    """Get database instance"""
    global db
    if db is None:
        init_db()
    return db


def normalize_rating(rating):
    """Konvertuje staré hodnocení 1-5 na nové 0-100%

    Pro zpětnou kompatibilitu: pokud je rating <= 5, předpokládáme starý formát
    a násobíme 20 pro konverzi na procenta.
    """
    if rating is None:
        return None
    if 1 <= rating <= 5:
        return rating * 20  # Starý formát 1-5 -> 20-100%
    return rating  # Nový formát 0-100%


def log_session(preset, category, task, duration_minutes, completed=True,
                productivity_rating=None, notes=''):
    """Log a completed session to MongoDB"""
    database = get_db()
    now = datetime.now()

    session = {
        'date': date.today().isoformat(),
        'time': now.strftime('%H:%M'),
        'preset': preset,
        'category': category,
        'task': task,
        'duration_minutes': duration_minutes,
        'completed': completed,
        'productivity_rating': productivity_rating,
        'notes': notes,
        'day_of_week': now.weekday(),  # 0=Monday, 6=Sunday
        'hour': now.hour,
        'created_at': now
    }

    result = database.sessions.insert_one(session)
    return str(result.inserted_id)


def get_today_stats():
    """Get statistics for today"""
    database = get_db()
    today = date.today().isoformat()

    sessions = list(database.sessions.find({'date': today}))

    total_minutes = sum(
        s.get('duration_minutes', 0)
        for s in sessions
        if s.get('completed', False)
    )

    avg_rating = 0
    rated_sessions = [s for s in sessions if s.get('productivity_rating')]
    if rated_sessions:
        normalized_ratings = [normalize_rating(s['productivity_rating']) for s in rated_sessions]
        avg_rating = sum(normalized_ratings) / len(normalized_ratings)

    # Convert ObjectId to string for JSON serialization
    # a normalizuj rating na 0-100%
    for s in sessions:
        s['_id'] = str(s['_id'])
        if 'created_at' in s:
            s['created_at'] = s['created_at'].isoformat()
        if s.get('productivity_rating'):
            s['productivity_rating'] = normalize_rating(s['productivity_rating'])

    return {
        'sessions': len(sessions),
        'completed_sessions': len([s for s in sessions if s.get('completed')]),
        'total_minutes': total_minutes,
        'total_hours': round(total_minutes / 60, 1),
        'avg_rating': round(avg_rating, 1),
        'details': sessions
    }


def get_weekly_stats():
    """Get statistics for current week"""
    database = get_db()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    sessions = list(database.sessions.find({
        'date': {'$gte': week_start.isoformat()},
        'completed': True
    }))

    daily_stats = {}
    categories = {}
    presets = {}
    hourly_stats = {}

    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    for session in sessions:
        duration = session.get('duration_minutes', 0)
        raw_rating = session.get('productivity_rating', 0)
        rating = normalize_rating(raw_rating) if raw_rating else 0

        # Daily totals
        session_date = datetime.strptime(session['date'], '%Y-%m-%d').date()
        day_name = day_names[session_date.weekday()]
        if day_name not in daily_stats:
            daily_stats[day_name] = {'minutes': 0, 'sessions': 0, 'ratings': []}
        daily_stats[day_name]['minutes'] += duration
        daily_stats[day_name]['sessions'] += 1
        if rating:
            daily_stats[day_name]['ratings'].append(rating)

        # Category totals
        cat = session.get('category', 'Other')
        if cat not in categories:
            categories[cat] = {'minutes': 0, 'sessions': 0, 'ratings': []}
        categories[cat]['minutes'] += duration
        categories[cat]['sessions'] += 1
        if rating:
            categories[cat]['ratings'].append(rating)

        # Preset totals
        preset = session.get('preset', 'deep_work')
        if preset not in presets:
            presets[preset] = {'minutes': 0, 'sessions': 0}
        presets[preset]['minutes'] += duration
        presets[preset]['sessions'] += 1

        # Hourly stats
        hour = session.get('hour', 0)
        if hour not in hourly_stats:
            hourly_stats[hour] = {'sessions': 0, 'ratings': []}
        hourly_stats[hour]['sessions'] += 1
        if rating:
            hourly_stats[hour]['ratings'].append(rating)

    # Calculate averages
    for day in daily_stats.values():
        day['avg_rating'] = round(sum(day['ratings']) / len(day['ratings']), 1) if day['ratings'] else 0
        del day['ratings']

    for cat in categories.values():
        cat['avg_rating'] = round(sum(cat['ratings']) / len(cat['ratings']), 1) if cat['ratings'] else 0
        del cat['ratings']

    for hour in hourly_stats.values():
        hour['avg_rating'] = round(sum(hour['ratings']) / len(hour['ratings']), 1) if hour['ratings'] else 0
        del hour['ratings']

    total_minutes = sum(d['minutes'] for d in daily_stats.values())

    return {
        'daily': daily_stats,
        'categories': categories,
        'presets': presets,
        'hourly': hourly_stats,
        'total_minutes': total_minutes,
        'total_hours': round(total_minutes / 60, 1),
        'total_sessions': sum(d['sessions'] for d in daily_stats.values())
    }


def get_history(limit=100):
    """Get session history"""
    database = get_db()
    sessions = list(database.sessions.find().sort('created_at', -1).limit(limit))

    for s in sessions:
        s['_id'] = str(s['_id'])
        if 'created_at' in s:
            s['created_at'] = s['created_at'].isoformat()
        if s.get('productivity_rating'):
            s['productivity_rating'] = normalize_rating(s['productivity_rating'])

    return sessions


def get_all_sessions():
    """Get all sessions for ML analysis"""
    database = get_db()
    sessions = list(database.sessions.find({'completed': True}))

    for s in sessions:
        s['_id'] = str(s['_id'])
        if 'created_at' in s:
            s['created_at'] = s['created_at'].isoformat()

    return sessions


def save_insight(insight_type, data):
    """Save ML insight to database"""
    database = get_db()

    database.insights.update_one(
        {'type': insight_type},
        {
            '$set': {
                'type': insight_type,
                'data': data,
                'updated_at': datetime.now()
            }
        },
        upsert=True
    )


def get_insight(insight_type):
    """Get ML insight from database"""
    database = get_db()
    return database.insights.find_one({'type': insight_type})


def save_prediction(prediction_data):
    """Save prediction to database"""
    database = get_db()
    prediction_data['created_at'] = datetime.now()
    database.predictions.insert_one(prediction_data)


def get_latest_prediction():
    """Get latest prediction"""
    database = get_db()
    return database.predictions.find_one(
        {'date': date.today().isoformat()},
        sort=[('created_at', -1)]
    )


def clear_all_sessions():
    """Delete all sessions - for testing purposes"""
    database = get_db()
    result = database.sessions.delete_many({})
    return result.deleted_count


def get_streak_stats():
    """Calculate current and longest streak"""
    database = get_db()

    # Get all unique dates with completed sessions
    pipeline = [
        {'$match': {'completed': True}},
        {'$group': {'_id': '$date'}},
        {'$sort': {'_id': -1}}
    ]
    dates = [doc['_id'] for doc in database.sessions.aggregate(pipeline)]

    if not dates:
        return {'current_streak': 0, 'longest_streak': 0, 'total_days': 0}

    # Convert to date objects and sort
    date_objects = []
    for d in dates:
        try:
            date_objects.append(datetime.strptime(d, '%Y-%m-%d').date())
        except (ValueError, TypeError):
            continue

    date_objects = sorted(set(date_objects), reverse=True)

    if not date_objects:
        return {'current_streak': 0, 'longest_streak': 0, 'total_days': 0}

    # Calculate current streak
    current_streak = 0
    today = date.today()
    check_date = today

    for d in date_objects:
        if d == check_date or d == check_date - timedelta(days=1):
            current_streak += 1
            check_date = d
        else:
            break

    # Calculate longest streak
    longest_streak = 1
    current_run = 1

    for i in range(1, len(date_objects)):
        diff = (date_objects[i-1] - date_objects[i]).days
        if diff == 1:
            current_run += 1
            longest_streak = max(longest_streak, current_run)
        else:
            current_run = 1

    return {
        'current_streak': current_streak,
        'longest_streak': longest_streak,
        'total_days': len(date_objects)
    }
