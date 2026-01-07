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

        # Create indexes for sessions
        db.sessions.create_index([("date", -1)])
        db.sessions.create_index([("category", 1)])
        db.sessions.create_index([("preset", 1)])
        db.sessions.create_index([("completed", 1)])
        db.sessions.create_index([("date", -1), ("completed", 1)])
        db.sessions.create_index([("hour", 1)])  # For time-based achievements
        db.sessions.create_index([("day_of_week", 1)])  # For weekend achievements

        # Create indexes for calendar collections
        db.daily_focus.create_index([("date", -1)], unique=True)
        db.daily_focus.create_index([("theme", 1)])
        db.weekly_plans.create_index([("week_start", -1)], unique=True)
        db.weekly_plans.create_index([("year", 1), ("week_number", 1)])
        db.weekly_reviews.create_index([("week_start", -1)], unique=True)

        # Create index for achievements
        db.achievements.create_index([("achievement_id", 1)], unique=True)

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


# =============================================================================
# CALENDAR & DAILY FOCUS FUNCTIONS
# =============================================================================

def init_calendar_indexes():
    """Initialize indexes for calendar collections"""
    database = get_db()

    # Daily focus indexes
    database.daily_focus.create_index([("date", -1)], unique=True)
    database.daily_focus.create_index([("theme", 1)])

    # Weekly plans indexes
    database.weekly_plans.create_index([("week_start", -1)], unique=True)
    database.weekly_plans.create_index([("year", 1), ("week_number", 1)])

    # Weekly reviews indexes
    database.weekly_reviews.create_index([("week_start", -1)], unique=True)


def get_daily_focus(target_date=None):
    """Get daily focus for a specific date

    Returns focus with themes array. Handles backward compatibility
    with old 'theme' (string) format by converting to themes array.
    """
    database = get_db()
    if target_date is None:
        target_date = date.today().isoformat()
    elif isinstance(target_date, date):
        target_date = target_date.isoformat()

    focus = database.daily_focus.find_one({'date': target_date})
    if focus:
        focus['_id'] = str(focus['_id'])
        if 'created_at' in focus:
            focus['created_at'] = focus['created_at'].isoformat()
        if 'updated_at' in focus:
            focus['updated_at'] = focus['updated_at'].isoformat()

        # Backward compatibility: convert old 'theme' to 'themes' array
        if 'themes' not in focus and 'theme' in focus:
            focus['themes'] = [{
                'theme': focus['theme'],
                'planned_sessions': focus.get('planned_sessions', 6),
                'notes': focus.get('notes', '')
            }] if focus['theme'] else []
        elif 'themes' not in focus:
            focus['themes'] = []

        # Calculate total planned sessions from all themes
        focus['total_planned'] = sum(t.get('planned_sessions', 0) for t in focus.get('themes', []))

        # Backward compatibility: add theme string from first themes item for UI
        if focus.get('themes') and len(focus['themes']) > 0:
            focus['theme'] = focus['themes'][0]['theme']
            # Keep planned_sessions as total if already set, otherwise use first theme
            if 'planned_sessions' not in focus or focus['planned_sessions'] == 0:
                focus['planned_sessions'] = focus['total_planned']
        else:
            focus['theme'] = None
            if 'planned_sessions' not in focus:
                focus['planned_sessions'] = 0

    return focus


def set_daily_focus(target_date, themes, notes=''):
    """Set or update daily focus for a specific date

    Args:
        target_date: Date string or date object
        themes: List of theme objects, each with:
            - theme: Category/theme name
            - planned_sessions: Number of planned sessions for this theme
            - notes: Optional notes for this specific theme
        notes: General notes for the day (optional)
    """
    database = get_db()
    if isinstance(target_date, date):
        target_date = target_date.isoformat()

    now = datetime.now()

    # Validate and clean themes
    clean_themes = []
    total_planned = 0
    for t in (themes or []):
        if t.get('theme'):
            clean_theme = {
                'theme': str(t['theme']),
                'planned_sessions': int(t.get('planned_sessions', 1)),
                'notes': str(t.get('notes', ''))[:500]
            }
            clean_themes.append(clean_theme)
            total_planned += clean_theme['planned_sessions']

    # Calculate actual sessions for this date
    actual_sessions = database.sessions.count_documents({
        'date': target_date,
        'completed': True
    })

    # Calculate productivity score
    sessions = list(database.sessions.find({
        'date': target_date,
        'completed': True,
        'productivity_rating': {'$exists': True, '$ne': None}
    }))

    productivity_score = 0
    if sessions:
        ratings = [normalize_rating(s['productivity_rating']) for s in sessions]
        productivity_score = sum(ratings) / len(ratings)

    result = database.daily_focus.update_one(
        {'date': target_date},
        {
            '$set': {
                'date': target_date,
                'themes': clean_themes,
                'notes': str(notes)[:1000],  # General day notes
                'planned_sessions': total_planned,  # Total for backward compat
                'actual_sessions': actual_sessions,
                'productivity_score': round(productivity_score, 1),
                'updated_at': now
            },
            '$setOnInsert': {
                'created_at': now
            }
        },
        upsert=True
    )

    return result.upserted_id or result.modified_count > 0


def update_daily_focus_stats(target_date):
    """Update actual_sessions and productivity_score for a date"""
    database = get_db()
    if isinstance(target_date, date):
        target_date = target_date.isoformat()

    # Calculate actual sessions
    actual_sessions = database.sessions.count_documents({
        'date': target_date,
        'completed': True
    })

    # Calculate productivity score
    sessions = list(database.sessions.find({
        'date': target_date,
        'completed': True,
        'productivity_rating': {'$exists': True, '$ne': None}
    }))

    productivity_score = 0
    if sessions:
        ratings = [normalize_rating(s['productivity_rating']) for s in sessions]
        productivity_score = sum(ratings) / len(ratings)

    database.daily_focus.update_one(
        {'date': target_date},
        {
            '$set': {
                'actual_sessions': actual_sessions,
                'productivity_score': round(productivity_score, 1),
                'updated_at': datetime.now()
            }
        }
    )


def get_calendar_month(year, month):
    """Get all daily focus data for a month"""
    database = get_db()

    # Calculate date range for the month
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    # Get daily focus data
    focus_data = list(database.daily_focus.find({
        'date': {
            '$gte': first_day.isoformat(),
            '$lte': last_day.isoformat()
        }
    }))

    # Get sessions data aggregated by date
    sessions_pipeline = [
        {
            '$match': {
                'date': {
                    '$gte': first_day.isoformat(),
                    '$lte': last_day.isoformat()
                },
                'completed': True
            }
        },
        {
            '$group': {
                '_id': '$date',
                'sessions': {'$sum': 1},
                'total_minutes': {'$sum': '$duration_minutes'},
                'ratings': {'$push': '$productivity_rating'}
            }
        }
    ]
    sessions_data = {doc['_id']: doc for doc in database.sessions.aggregate(sessions_pipeline)}

    # Build result
    result = {}
    current = first_day
    while current <= last_day:
        date_str = current.isoformat()
        focus = next((f for f in focus_data if f['date'] == date_str), None)
        session_info = sessions_data.get(date_str, {})

        # Calculate avg rating
        ratings = [r for r in session_info.get('ratings', []) if r is not None]
        avg_rating = 0
        if ratings:
            normalized = [normalize_rating(r) for r in ratings]
            avg_rating = sum(normalized) / len(normalized)

        # Handle themes array with backward compatibility
        themes = []
        total_planned = 0
        if focus:
            if 'themes' in focus and focus['themes']:
                themes = focus['themes']
                total_planned = sum(t.get('planned_sessions', 0) for t in themes)
            elif focus.get('theme'):
                # Backward compatibility: convert old single theme to array
                themes = [{
                    'theme': focus['theme'],
                    'planned_sessions': focus.get('planned_sessions', 6),
                    'notes': ''
                }]
                total_planned = focus.get('planned_sessions', 6)

        result[date_str] = {
            'date': date_str,
            'day_of_week': current.weekday(),
            'themes': themes,
            'theme': themes[0]['theme'] if themes else None,  # Backward compat
            'notes': focus.get('notes', '') if focus else '',
            'total_planned': total_planned,
            'planned_sessions': total_planned,  # Backward compat
            'actual_sessions': session_info.get('sessions', 0),
            'total_minutes': session_info.get('total_minutes', 0),
            'productivity_score': round(avg_rating, 1)
        }
        current += timedelta(days=1)

    return result


def get_calendar_week(week_start_date):
    """Get daily focus data for a week starting from given date"""
    database = get_db()

    if isinstance(week_start_date, str):
        week_start_date = datetime.strptime(week_start_date, '%Y-%m-%d').date()

    # Adjust to Monday if not already
    days_since_monday = week_start_date.weekday()
    week_start = week_start_date - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=6)

    # Get daily focus data
    focus_data = list(database.daily_focus.find({
        'date': {
            '$gte': week_start.isoformat(),
            '$lte': week_end.isoformat()
        }
    }))

    # Get sessions data
    sessions_pipeline = [
        {
            '$match': {
                'date': {
                    '$gte': week_start.isoformat(),
                    '$lte': week_end.isoformat()
                },
                'completed': True
            }
        },
        {
            '$group': {
                '_id': '$date',
                'sessions': {'$sum': 1},
                'total_minutes': {'$sum': '$duration_minutes'},
                'ratings': {'$push': '$productivity_rating'},
                'categories': {'$push': '$category'}
            }
        }
    ]
    sessions_data = {doc['_id']: doc for doc in database.sessions.aggregate(sessions_pipeline)}

    # Build result
    result = {
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'days': {}
    }

    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    current = week_start

    for i in range(7):
        date_str = current.isoformat()
        focus = next((f for f in focus_data if f['date'] == date_str), None)
        session_info = sessions_data.get(date_str, {})

        ratings = [r for r in session_info.get('ratings', []) if r is not None]
        avg_rating = 0
        if ratings:
            normalized = [normalize_rating(r) for r in ratings]
            avg_rating = sum(normalized) / len(normalized)

        # Handle themes array with backward compatibility
        themes = []
        total_planned = 0
        if focus:
            if 'themes' in focus and focus['themes']:
                themes = focus['themes']
                total_planned = sum(t.get('planned_sessions', 0) for t in themes)
            elif focus.get('theme'):
                themes = [{
                    'theme': focus['theme'],
                    'planned_sessions': focus.get('planned_sessions', 6),
                    'notes': ''
                }]
                total_planned = focus.get('planned_sessions', 6)

        result['days'][date_str] = {
            'date': date_str,
            'day_name': day_names[i],
            'day_of_week': i,
            'themes': themes,
            'theme': themes[0]['theme'] if themes else None,  # Backward compat
            'notes': focus.get('notes', '') if focus else '',
            'total_planned': total_planned,
            'planned_sessions': total_planned,  # Backward compat
            'actual_sessions': session_info.get('sessions', 0),
            'total_minutes': session_info.get('total_minutes', 0),
            'productivity_score': round(avg_rating, 1),
            'categories': session_info.get('categories', [])
        }
        current += timedelta(days=1)

    return result


# =============================================================================
# WEEKLY PLANNING FUNCTIONS
# =============================================================================

def get_weekly_plan(week_start_date):
    """Get weekly plan for a specific week"""
    database = get_db()

    if isinstance(week_start_date, str):
        week_start_date = datetime.strptime(week_start_date, '%Y-%m-%d').date()

    # Adjust to Monday
    days_since_monday = week_start_date.weekday()
    week_start = week_start_date - timedelta(days=days_since_monday)

    plan = database.weekly_plans.find_one({'week_start': week_start.isoformat()})
    if plan:
        plan['_id'] = str(plan['_id'])
        if 'created_at' in plan:
            plan['created_at'] = plan['created_at'].isoformat()
        if 'updated_at' in plan:
            plan['updated_at'] = plan['updated_at'].isoformat()

    return plan


def save_weekly_plan(week_start_date, days, goals=None):
    """Save or update weekly plan"""
    database = get_db()

    if isinstance(week_start_date, str):
        week_start_date = datetime.strptime(week_start_date, '%Y-%m-%d').date()

    # Adjust to Monday
    days_since_monday = week_start_date.weekday()
    week_start = week_start_date - timedelta(days=days_since_monday)

    # Calculate ISO week number
    iso_calendar = week_start.isocalendar()

    now = datetime.now()

    result = database.weekly_plans.update_one(
        {'week_start': week_start.isoformat()},
        {
            '$set': {
                'week_start': week_start.isoformat(),
                'week_number': iso_calendar[1],
                'year': iso_calendar[0],
                'days': days,
                'goals': goals or [],
                'updated_at': now
            },
            '$setOnInsert': {
                'created_at': now
            }
        },
        upsert=True
    )

    # Also update daily_focus for each day
    for day in days:
        if day.get('theme'):
            set_daily_focus(
                day['date'],
                day['theme'],
                day.get('notes', ''),
                day.get('planned_sessions', 6)
            )

    return result.upserted_id or result.modified_count > 0


# =============================================================================
# WEEKLY REVIEW FUNCTIONS
# =============================================================================

def get_weekly_review(week_start_date):
    """Get weekly review for a specific week"""
    database = get_db()

    if isinstance(week_start_date, str):
        week_start_date = datetime.strptime(week_start_date, '%Y-%m-%d').date()

    # Adjust to Monday
    days_since_monday = week_start_date.weekday()
    week_start = week_start_date - timedelta(days=days_since_monday)

    review = database.weekly_reviews.find_one({'week_start': week_start.isoformat()})
    if review:
        review['_id'] = str(review['_id'])
        if 'created_at' in review:
            review['created_at'] = review['created_at'].isoformat()

    return review


def generate_weekly_stats(week_start_date):
    """Generate statistics for weekly review"""
    database = get_db()

    if isinstance(week_start_date, str):
        week_start_date = datetime.strptime(week_start_date, '%Y-%m-%d').date()

    # Adjust to Monday
    days_since_monday = week_start_date.weekday()
    week_start = week_start_date - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=6)

    # Get all sessions for the week
    sessions = list(database.sessions.find({
        'date': {
            '$gte': week_start.isoformat(),
            '$lte': week_end.isoformat()
        },
        'completed': True
    }))

    if not sessions:
        return {
            'total_sessions': 0,
            'total_hours': 0,
            'avg_productivity': 0,
            'completed_ratio': 0,
            'best_day': None,
            'best_theme': None
        }

    # Calculate stats
    total_sessions = len(sessions)
    total_minutes = sum(s.get('duration_minutes', 0) for s in sessions)

    ratings = [normalize_rating(s['productivity_rating'])
               for s in sessions
               if s.get('productivity_rating') is not None]
    avg_productivity = sum(ratings) / len(ratings) if ratings else 0

    # Get all sessions including incomplete
    all_sessions = database.sessions.count_documents({
        'date': {
            '$gte': week_start.isoformat(),
            '$lte': week_end.isoformat()
        }
    })
    completed_ratio = (total_sessions / all_sessions * 100) if all_sessions > 0 else 0

    # Find best day
    day_stats = {}
    for s in sessions:
        d = s['date']
        if d not in day_stats:
            day_stats[d] = {'sessions': 0, 'ratings': []}
        day_stats[d]['sessions'] += 1
        if s.get('productivity_rating'):
            day_stats[d]['ratings'].append(normalize_rating(s['productivity_rating']))

    best_day = None
    best_day_score = 0
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    for d, stats in day_stats.items():
        if stats['ratings']:
            score = sum(stats['ratings']) / len(stats['ratings'])
            if score > best_day_score:
                best_day_score = score
                day_date = datetime.strptime(d, '%Y-%m-%d').date()
                best_day = day_names[day_date.weekday()]

    # Theme breakdown
    theme_stats = {}
    focus_data = list(database.daily_focus.find({
        'date': {
            '$gte': week_start.isoformat(),
            '$lte': week_end.isoformat()
        }
    }))
    date_to_theme = {f['date']: f['theme'] for f in focus_data}

    for s in sessions:
        theme = date_to_theme.get(s['date'], s.get('category', 'Other'))
        if theme not in theme_stats:
            theme_stats[theme] = {'sessions': 0, 'ratings': []}
        theme_stats[theme]['sessions'] += 1
        if s.get('productivity_rating'):
            theme_stats[theme]['ratings'].append(normalize_rating(s['productivity_rating']))

    theme_breakdown = []
    best_theme = None
    best_theme_score = 0

    for theme, stats in theme_stats.items():
        avg_rating = sum(stats['ratings']) / len(stats['ratings']) if stats['ratings'] else 0
        theme_breakdown.append({
            'theme': theme,
            'sessions': stats['sessions'],
            'avg_rating': round(avg_rating, 1)
        })
        if avg_rating > best_theme_score:
            best_theme_score = avg_rating
            best_theme = theme

    # Sort by sessions
    theme_breakdown.sort(key=lambda x: x['sessions'], reverse=True)

    return {
        'total_sessions': total_sessions,
        'total_hours': round(total_minutes / 60, 1),
        'avg_productivity': round(avg_productivity, 1),
        'completed_ratio': round(completed_ratio, 1),
        'best_day': best_day,
        'best_theme': best_theme,
        'theme_breakdown': theme_breakdown
    }


def save_weekly_review(week_start_date, reflections, next_week_goals=None, ml_insights=None):
    """Save weekly review"""
    database = get_db()

    if isinstance(week_start_date, str):
        week_start_date = datetime.strptime(week_start_date, '%Y-%m-%d').date()

    # Adjust to Monday
    days_since_monday = week_start_date.weekday()
    week_start = week_start_date - timedelta(days=days_since_monday)

    # Generate stats
    stats = generate_weekly_stats(week_start)

    # Calculate ISO week
    iso_calendar = week_start.isocalendar()

    review_data = {
        'week_start': week_start.isoformat(),
        'week_number': iso_calendar[1],
        'year': iso_calendar[0],
        'stats': {
            'total_sessions': stats['total_sessions'],
            'total_hours': stats['total_hours'],
            'avg_productivity': stats['avg_productivity'],
            'completed_ratio': stats['completed_ratio'],
            'best_day': stats['best_day'],
            'best_theme': stats['best_theme']
        },
        'theme_breakdown': stats.get('theme_breakdown', []),
        'reflections': {
            'what_worked': str(reflections.get('what_worked', ''))[:2000],
            'what_to_improve': str(reflections.get('what_to_improve', ''))[:2000],
            'lessons_learned': str(reflections.get('lessons_learned', ''))[:2000]
        },
        'next_week_goals': next_week_goals or [],
        'ml_insights': ml_insights or {},
        'created_at': datetime.now()
    }

    result = database.weekly_reviews.update_one(
        {'week_start': week_start.isoformat()},
        {'$set': review_data},
        upsert=True
    )

    return result.upserted_id or result.modified_count > 0


def get_latest_weekly_review():
    """Get the most recent weekly review"""
    database = get_db()
    review = database.weekly_reviews.find_one(sort=[('week_start', -1)])
    if review:
        review['_id'] = str(review['_id'])
        if 'created_at' in review:
            review['created_at'] = review['created_at'].isoformat()
    return review


def get_theme_analytics():
    """Get analytics for all themes/categories"""
    database = get_db()

    # Get theme productivity from daily_focus
    pipeline = [
        {
            '$lookup': {
                'from': 'sessions',
                'localField': 'date',
                'foreignField': 'date',
                'as': 'sessions'
            }
        },
        {
            '$unwind': '$sessions'
        },
        {
            '$match': {
                'sessions.completed': True
            }
        },
        {
            '$group': {
                '_id': '$theme',
                'total_sessions': {'$sum': 1},
                'total_minutes': {'$sum': '$sessions.duration_minutes'},
                'ratings': {'$push': '$sessions.productivity_rating'},
                'days_used': {'$addToSet': '$date'}
            }
        }
    ]

    theme_data = list(database.daily_focus.aggregate(pipeline))

    # Also get category data from sessions without daily_focus
    category_pipeline = [
        {
            '$match': {'completed': True}
        },
        {
            '$group': {
                '_id': '$category',
                'total_sessions': {'$sum': 1},
                'total_minutes': {'$sum': '$duration_minutes'},
                'ratings': {'$push': '$productivity_rating'},
                'days_used': {'$addToSet': '$date'}
            }
        }
    ]
    category_data = list(database.sessions.aggregate(category_pipeline))

    # Merge and calculate averages
    result = {}

    for item in theme_data + category_data:
        theme = item['_id']
        if theme and theme not in result:
            ratings = [normalize_rating(r) for r in item['ratings'] if r is not None]
            avg_rating = sum(ratings) / len(ratings) if ratings else 0

            result[theme] = {
                'theme': theme,
                'total_sessions': item['total_sessions'],
                'total_hours': round(item['total_minutes'] / 60, 1),
                'avg_productivity': round(avg_rating, 1),
                'days_used': len(item['days_used'])
            }

    return list(result.values())


# =============================================================================
# ACHIEVEMENT SYSTEM
# =============================================================================

# Achievement definitions - all available achievements
ACHIEVEMENTS_DEFINITIONS = {
    # SESSION MILESTONES
    'first_session': {
        'name': 'První krok',
        'icon': '🎯',
        'rarity': 'common',
        'description': 'Dokončil jsi první session',
        'type': 'sessions_total',
        'target': 1,
        'category': 'sessions',
        'points': 10
    },
    'sessions_10': {
        'name': 'Začátečník',
        'icon': '🌱',
        'rarity': 'common',
        'description': '10 dokončených sessions',
        'type': 'sessions_total',
        'target': 10,
        'category': 'sessions',
        'points': 25
    },
    'sessions_50': {
        'name': 'Pravidelný',
        'icon': '🎖️',
        'rarity': 'common',
        'description': '50 dokončených sessions',
        'type': 'sessions_total',
        'target': 50,
        'category': 'sessions',
        'points': 50
    },
    'sessions_100': {
        'name': 'Centurion',
        'icon': '🏅',
        'rarity': 'rare',
        'description': '100 dokončených sessions',
        'type': 'sessions_total',
        'target': 100,
        'category': 'sessions',
        'points': 100
    },
    'sessions_500': {
        'name': 'Veterán',
        'icon': '🏆',
        'rarity': 'epic',
        'description': '500 dokončených sessions',
        'type': 'sessions_total',
        'target': 500,
        'category': 'sessions',
        'points': 250
    },
    'sessions_1000': {
        'name': 'Tisícovka',
        'icon': '👑',
        'rarity': 'legendary',
        'description': '1000 dokončených sessions',
        'type': 'sessions_total',
        'target': 1000,
        'category': 'sessions',
        'points': 500
    },

    # STREAK ACHIEVEMENTS
    'streak_3': {
        'name': 'Hatrick',
        'icon': '🔥',
        'rarity': 'common',
        'description': '3 dny v řadě',
        'type': 'streak',
        'target': 3,
        'category': 'streak',
        'points': 15
    },
    'streak_7': {
        'name': 'Týdenní bojovník',
        'icon': '⚡',
        'rarity': 'rare',
        'description': '7 dní v řadě',
        'type': 'streak',
        'target': 7,
        'category': 'streak',
        'points': 50
    },
    'streak_14': {
        'name': 'Čtrnáctidenní výzva',
        'icon': '💪',
        'rarity': 'rare',
        'description': '14 dní v řadě',
        'type': 'streak',
        'target': 14,
        'category': 'streak',
        'points': 100
    },
    'streak_30': {
        'name': 'Měsíční mistr',
        'icon': '💎',
        'rarity': 'epic',
        'description': '30 dní v řadě',
        'type': 'streak',
        'target': 30,
        'category': 'streak',
        'points': 200
    },
    'streak_90': {
        'name': 'Kvartální legenda',
        'icon': '🌟',
        'rarity': 'legendary',
        'description': '90 dní v řadě',
        'type': 'streak',
        'target': 90,
        'category': 'streak',
        'points': 500
    },

    # PRESET ACHIEVEMENTS
    'deep_work_master': {
        'name': 'Deep Work Master',
        'icon': '🧠',
        'rarity': 'rare',
        'description': '20 sessions s Deep Work (52/17)',
        'type': 'preset_count',
        'target': 20,
        'preset': 'deep_work',
        'category': 'preset',
        'points': 75
    },
    'flow_state': {
        'name': 'Flow State',
        'icon': '🌊',
        'rarity': 'rare',
        'description': '5 sessions s Flow Mode (90 min)',
        'type': 'preset_count',
        'target': 5,
        'preset': 'flow_mode',
        'category': 'preset',
        'points': 50
    },
    'quick_master': {
        'name': 'Rychlostřelec',
        'icon': '⚡',
        'rarity': 'rare',
        'description': '30 sessions s Quick Tasks',
        'type': 'preset_count',
        'target': 30,
        'preset': 'quick_tasks',
        'category': 'preset',
        'points': 75
    },
    'all_rounder': {
        'name': 'Všestranný',
        'icon': '🎭',
        'rarity': 'epic',
        'description': 'Použil jsi všechny 4 presety',
        'type': 'unique_presets',
        'target': 4,
        'category': 'preset',
        'points': 100
    },

    # PRODUCTIVITY ACHIEVEMENTS
    'perfect_day': {
        'name': 'Perfektní den',
        'icon': '✨',
        'rarity': 'epic',
        'description': '5+ sessions s průměrem 90%+ v jeden den',
        'type': 'perfect_day',
        'target': 1,
        'min_sessions': 5,
        'min_rating': 90,
        'category': 'productivity',
        'points': 150
    },
    'star_performer': {
        'name': 'Hvězda produktivity',
        'icon': '🌟',
        'rarity': 'epic',
        'description': 'Celkový průměr 80%+ při min 20 sessions',
        'type': 'avg_rating',
        'target': 80,
        'min_sessions': 20,
        'category': 'productivity',
        'points': 150
    },
    'consistency': {
        'name': 'Konzistence',
        'icon': '📈',
        'rarity': 'epic',
        'description': '10 sessions v řadě s hodnocením 70%+',
        'type': 'consecutive_rating',
        'target': 10,
        'min_rating': 70,
        'category': 'productivity',
        'points': 125
    },

    # TIME-BASED ACHIEVEMENTS
    'early_bird': {
        'name': 'Ranní ptáče',
        'icon': '☀️',
        'rarity': 'rare',
        'description': '10 sessions před 8:00',
        'type': 'time_sessions',
        'target': 10,
        'hour_max': 8,
        'category': 'time',
        'points': 75
    },
    'night_owl': {
        'name': 'Noční sova',
        'icon': '🌙',
        'rarity': 'rare',
        'description': '10 sessions po 20:00',
        'type': 'time_sessions',
        'target': 10,
        'hour_min': 20,
        'category': 'time',
        'points': 75
    },
    'marathon': {
        'name': 'Maratonec',
        'icon': '🏃',
        'rarity': 'epic',
        'description': '8+ sessions v jednom dni',
        'type': 'daily_max',
        'target': 8,
        'category': 'time',
        'points': 125
    },
    'weekend_warrior': {
        'name': 'Víkendový válečník',
        'icon': '🎮',
        'rarity': 'rare',
        'description': '20 sessions o víkendech',
        'type': 'weekend_sessions',
        'target': 20,
        'category': 'time',
        'points': 75
    },

    # CATEGORY ACHIEVEMENTS
    'coding_ninja': {
        'name': 'Coding Ninja',
        'icon': '💻',
        'rarity': 'epic',
        'description': '50 sessions v programovacích kategoriích',
        'type': 'coding_sessions',
        'target': 50,
        'category': 'category',
        'points': 150
    },
    'eternal_student': {
        'name': 'Věčný student',
        'icon': '📚',
        'rarity': 'rare',
        'description': '30 sessions v Learning',
        'type': 'category_count',
        'target': 30,
        'target_category': 'Learning',
        'category': 'category',
        'points': 75
    },
    'multitasker': {
        'name': 'Multitasker',
        'icon': '🎪',
        'rarity': 'rare',
        'description': 'Sessions v 5+ různých kategoriích',
        'type': 'unique_categories',
        'target': 5,
        'category': 'category',
        'points': 50
    },

    # PLANNING ACHIEVEMENTS
    'planner': {
        'name': 'Plánovač',
        'icon': '📊',
        'rarity': 'rare',
        'description': '5 týdenních plánů',
        'type': 'weekly_plans',
        'target': 5,
        'category': 'planning',
        'points': 75
    },
    'reflective': {
        'name': 'Reflexivní myslitel',
        'icon': '🪞',
        'rarity': 'rare',
        'description': '5 týdenních reviews',
        'type': 'weekly_reviews',
        'target': 5,
        'category': 'planning',
        'points': 75
    },
    'strategist': {
        'name': 'Stratég',
        'icon': '🏁',
        'rarity': 'epic',
        'description': '80%+ splnění plánovaných sessions',
        'type': 'plan_completion',
        'target': 80,
        'min_planned': 10,
        'category': 'planning',
        'points': 150
    },

    # ==========================================================================
    # COMBO ACHIEVEMENTS (15 new)
    # ==========================================================================
    'productive_morning': {
        'name': 'Produktivni rano',
        'icon': '🌅',
        'rarity': 'rare',
        'description': '3+ sessions pred polednem v jednom dni',
        'type': 'daily_time_combo',
        'target': 1,
        'combo_target': 3,
        'hour_max': 12,
        'category': 'combo',
        'points': 30
    },
    'afternoon_sprint': {
        'name': 'Odpoledni sprint',
        'icon': '🏃',
        'rarity': 'rare',
        'description': '4+ sessions mezi 12:00-18:00 v jednom dni',
        'type': 'daily_time_combo',
        'target': 1,
        'combo_target': 4,
        'hour_min': 12,
        'hour_max': 18,
        'category': 'combo',
        'points': 30
    },
    'night_shift': {
        'name': 'Nocni smena',
        'icon': '🌃',
        'rarity': 'rare',
        'description': '3+ sessions po 20:00 v jednom dni',
        'type': 'daily_time_combo',
        'target': 1,
        'combo_target': 3,
        'hour_min': 20,
        'category': 'combo',
        'points': 30
    },
    'daily_marathon_combo': {
        'name': 'Celodenni maraton',
        'icon': '🏅',
        'rarity': 'epic',
        'description': '8+ sessions v jednom dni',
        'type': 'daily_max',
        'target': 8,
        'category': 'combo',
        'points': 75
    },
    'perfectionist_day': {
        'name': 'Perfekcionista',
        'icon': '💯',
        'rarity': 'epic',
        'description': '5+ sessions vsechny s 80%+ rating',
        'type': 'perfect_rating_day',
        'target': 1,
        'min_sessions': 5,
        'min_rating': 80,
        'category': 'combo',
        'points': 100
    },
    'balanced_week': {
        'name': 'Balanced Week',
        'icon': '⚖️',
        'rarity': 'rare',
        'description': 'Session kazdy den v tydnu',
        'type': 'full_week',
        'target': 1,
        'category': 'combo',
        'points': 50
    },
    'weekend_warrior_combo': {
        'name': 'Weekend Warrior',
        'icon': '🎯',
        'rarity': 'rare',
        'description': '10+ sessions o vikendu',
        'type': 'weekend_sessions',
        'target': 10,
        'category': 'combo',
        'points': 40
    },
    'workweek_hero': {
        'name': 'Workweek Hero',
        'icon': '💼',
        'rarity': 'epic',
        'description': '25+ sessions pondeli-patek v jednom tydnu',
        'type': 'workweek_sessions',
        'target': 25,
        'category': 'combo',
        'points': 100
    },
    'focus_mixer': {
        'name': 'Focus Mixer',
        'icon': '🎨',
        'rarity': 'rare',
        'description': '3+ ruzne presety za den',
        'type': 'daily_preset_variety',
        'target': 1,
        'preset_count': 3,
        'category': 'combo',
        'points': 25
    },
    'deep_dive_day': {
        'name': 'Deep Dive Day',
        'icon': '🤿',
        'rarity': 'epic',
        'description': '4+ deep_work sessions za den',
        'type': 'daily_preset_count',
        'target': 1,
        'preset': 'deep_work',
        'preset_target': 4,
        'category': 'combo',
        'points': 75
    },
    'flow_master_combo': {
        'name': 'Flow Master',
        'icon': '🌊',
        'rarity': 'epic',
        'description': '2+ flow_mode sessions za sebou',
        'type': 'consecutive_preset',
        'target': 2,
        'preset': 'flow_mode',
        'category': 'combo',
        'points': 100
    },
    'quick_fire': {
        'name': 'Quick Fire',
        'icon': '🔥',
        'rarity': 'rare',
        'description': '10+ quick_tasks za den',
        'type': 'daily_preset_count',
        'target': 1,
        'preset': 'quick_tasks',
        'preset_target': 10,
        'category': 'combo',
        'points': 40
    },
    'code_and_learn': {
        'name': 'Code & Learn',
        'icon': '📖',
        'rarity': 'common',
        'description': 'Coding + Learning v jednom dni',
        'type': 'daily_category_combo',
        'target': 1,
        'required_categories': ['Coding', 'Learning'],
        'category': 'combo',
        'points': 15
    },
    'full_stack_day': {
        'name': 'Full Stack Day',
        'icon': '🗂️',
        'rarity': 'rare',
        'description': '4+ ruzne kategorie za den',
        'type': 'daily_category_variety',
        'target': 1,
        'category_count': 4,
        'category': 'combo',
        'points': 35
    },
    'triple_threat': {
        'name': 'Triple Threat',
        'icon': '🎯',
        'rarity': 'rare',
        'description': '3 sessions ve 3 ruznych kategoriich',
        'type': 'triple_category',
        'target': 1,
        'category': 'combo',
        'points': 30
    },

    # ==========================================================================
    # SECRET/HIDDEN ACHIEVEMENTS (12 new)
    # ==========================================================================
    'midnight_coder': {
        'name': 'Pulnocni programator',
        'icon': '🌑',
        'rarity': 'rare',
        'description': '???',
        'type': 'secret_midnight',
        'target': 1,
        'category': 'secret',
        'points': 50,
        'hidden': True
    },
    'early_bird_extreme': {
        'name': 'Svitani',
        'icon': '🌄',
        'rarity': 'rare',
        'description': '???',
        'type': 'secret_early',
        'target': 1,
        'hour_max': 5,
        'category': 'secret',
        'points': 50,
        'hidden': True
    },
    'eleven_eleven': {
        'name': '11:11',
        'icon': '🕚',
        'rarity': 'epic',
        'description': '???',
        'type': 'secret_time',
        'target': 1,
        'hour': 11,
        'minute': 11,
        'category': 'secret',
        'points': 100,
        'hidden': True
    },
    'new_year': {
        'name': 'Novy rok',
        'icon': '🎆',
        'rarity': 'rare',
        'description': '???',
        'type': 'secret_date',
        'target': 1,
        'month': 1,
        'day': 1,
        'category': 'secret',
        'points': 75,
        'hidden': True
    },
    'lucky_seven': {
        'name': 'Lucky 7',
        'icon': '🎰',
        'rarity': 'rare',
        'description': '???',
        'type': 'secret_exact_count',
        'target': 1,
        'exact_sessions': 7,
        'category': 'secret',
        'points': 50,
        'hidden': True
    },
    'perfect_ten': {
        'name': 'Perfect 10',
        'icon': '🔟',
        'rarity': 'epic',
        'description': '???',
        'type': 'secret_exact_count',
        'target': 1,
        'exact_sessions': 10,
        'category': 'secret',
        'points': 100,
        'hidden': True
    },
    'the_answer': {
        'name': 'The Answer',
        'icon': '🌌',
        'rarity': 'common',
        'description': '???',
        'type': 'secret_total',
        'target': 42,
        'category': 'secret',
        'points': 42,
        'hidden': True
    },
    'leet_master': {
        'name': '1337',
        'icon': '👾',
        'rarity': 'rare',
        'description': '???',
        'type': 'secret_minutes',
        'target': 1337,
        'category': 'secret',
        'points': 50,
        'hidden': True
    },
    'year_of_work': {
        'name': 'Rok prace',
        'icon': '📅',
        'rarity': 'legendary',
        'description': '???',
        'type': 'secret_total',
        'target': 365,
        'category': 'secret',
        'points': 300,
        'hidden': True
    },
    'thousand_hours': {
        'name': 'Tisic hodin',
        'icon': '⏱️',
        'rarity': 'legendary',
        'description': '???',
        'type': 'secret_minutes',
        'target': 60000,
        'category': 'secret',
        'points': 500,
        'hidden': True
    },
    'coffee_break': {
        'name': 'Coffee Break',
        'icon': '☕',
        'rarity': 'rare',
        'description': '???',
        'type': 'secret_breaks',
        'target': 100,
        'category': 'secret',
        'points': 30,
        'hidden': True
    },
    'fibonacci': {
        'name': 'Fibonacci',
        'icon': '🐚',
        'rarity': 'legendary',
        'description': '???',
        'type': 'secret_fibonacci',
        'target': 1,
        'category': 'secret',
        'points': 200,
        'hidden': True
    },

    # ==========================================================================
    # CROSS-CATEGORY SPECIAL (3 new)
    # ==========================================================================
    'renaissance_person': {
        'name': 'Renesancni clovek',
        'icon': '🎨',
        'rarity': 'legendary',
        'description': 'Level 2+ ve vsech 7 kategoriich',
        'type': 'all_categories_level',
        'target': 7,
        'min_level': 2,
        'category': 'mastery',
        'points': 300
    },
    'specialist': {
        'name': 'Specialista',
        'icon': '🎓',
        'rarity': 'epic',
        'description': 'Level 5 v jakekoli kategorii',
        'type': 'max_category_level',
        'target': 5,
        'category': 'mastery',
        'points': 150
    },
    'polyglot': {
        'name': 'Polyglot',
        'icon': '🌐',
        'rarity': 'epic',
        'description': 'Level 3+ ve 4+ kategoriich',
        'type': 'multi_category_level',
        'target': 4,
        'min_level': 3,
        'category': 'mastery',
        'points': 100
    },

    # ==========================================================================
    # CATEGORY MASTERY ACHIEVEMENTS (35 new = 7 categories x 5 levels)
    # ==========================================================================

    # CODING MASTERY
    'coding_novice': {
        'name': 'Coding Novacek',
        'icon': '💻',
        'rarity': 'common',
        'description': '10 sessions v Coding',
        'type': 'category_mastery',
        'target': 10,
        'target_category': 'Coding',
        'mastery_level': 1,
        'category': 'mastery',
        'points': 10
    },
    'coding_apprentice': {
        'name': 'Coding Praktikant',
        'icon': '💻',
        'rarity': 'rare',
        'description': '50 sessions v Coding',
        'type': 'category_mastery',
        'target': 50,
        'target_category': 'Coding',
        'mastery_level': 2,
        'category': 'mastery',
        'points': 25
    },
    'coding_expert': {
        'name': 'Coding Expert',
        'icon': '💻',
        'rarity': 'rare',
        'description': '100 sessions v Coding',
        'type': 'category_mastery',
        'target': 100,
        'target_category': 'Coding',
        'mastery_level': 3,
        'category': 'mastery',
        'points': 50
    },
    'coding_master': {
        'name': 'Coding Mistr',
        'icon': '💻',
        'rarity': 'epic',
        'description': '250 sessions v Coding',
        'type': 'category_mastery',
        'target': 250,
        'target_category': 'Coding',
        'mastery_level': 4,
        'category': 'mastery',
        'points': 100
    },
    'coding_legend': {
        'name': 'Coding Legenda',
        'icon': '💻',
        'rarity': 'legendary',
        'description': '500 sessions v Coding',
        'type': 'category_mastery',
        'target': 500,
        'target_category': 'Coding',
        'mastery_level': 5,
        'category': 'mastery',
        'points': 250
    },

    # LEARNING MASTERY
    'learning_novice': {
        'name': 'Learning Novacek',
        'icon': '📚',
        'rarity': 'common',
        'description': '10 sessions v Learning',
        'type': 'category_mastery',
        'target': 10,
        'target_category': 'Learning',
        'mastery_level': 1,
        'category': 'mastery',
        'points': 10
    },
    'learning_apprentice': {
        'name': 'Learning Praktikant',
        'icon': '📚',
        'rarity': 'rare',
        'description': '50 sessions v Learning',
        'type': 'category_mastery',
        'target': 50,
        'target_category': 'Learning',
        'mastery_level': 2,
        'category': 'mastery',
        'points': 25
    },
    'learning_expert': {
        'name': 'Learning Expert',
        'icon': '📚',
        'rarity': 'rare',
        'description': '100 sessions v Learning',
        'type': 'category_mastery',
        'target': 100,
        'target_category': 'Learning',
        'mastery_level': 3,
        'category': 'mastery',
        'points': 50
    },
    'learning_master': {
        'name': 'Learning Mistr',
        'icon': '📚',
        'rarity': 'epic',
        'description': '250 sessions v Learning',
        'type': 'category_mastery',
        'target': 250,
        'target_category': 'Learning',
        'mastery_level': 4,
        'category': 'mastery',
        'points': 100
    },
    'learning_legend': {
        'name': 'Learning Legenda',
        'icon': '📚',
        'rarity': 'legendary',
        'description': '500 sessions v Learning',
        'type': 'category_mastery',
        'target': 500,
        'target_category': 'Learning',
        'mastery_level': 5,
        'category': 'mastery',
        'points': 250
    },

    # WRITING MASTERY
    'writing_novice': {
        'name': 'Writing Novacek',
        'icon': '✍️',
        'rarity': 'common',
        'description': '10 sessions v Writing',
        'type': 'category_mastery',
        'target': 10,
        'target_category': 'Writing',
        'mastery_level': 1,
        'category': 'mastery',
        'points': 10
    },
    'writing_apprentice': {
        'name': 'Writing Praktikant',
        'icon': '✍️',
        'rarity': 'rare',
        'description': '50 sessions v Writing',
        'type': 'category_mastery',
        'target': 50,
        'target_category': 'Writing',
        'mastery_level': 2,
        'category': 'mastery',
        'points': 25
    },
    'writing_expert': {
        'name': 'Writing Expert',
        'icon': '✍️',
        'rarity': 'rare',
        'description': '100 sessions v Writing',
        'type': 'category_mastery',
        'target': 100,
        'target_category': 'Writing',
        'mastery_level': 3,
        'category': 'mastery',
        'points': 50
    },
    'writing_master': {
        'name': 'Writing Mistr',
        'icon': '✍️',
        'rarity': 'epic',
        'description': '250 sessions v Writing',
        'type': 'category_mastery',
        'target': 250,
        'target_category': 'Writing',
        'mastery_level': 4,
        'category': 'mastery',
        'points': 100
    },
    'writing_legend': {
        'name': 'Writing Legenda',
        'icon': '✍️',
        'rarity': 'legendary',
        'description': '500 sessions v Writing',
        'type': 'category_mastery',
        'target': 500,
        'target_category': 'Writing',
        'mastery_level': 5,
        'category': 'mastery',
        'points': 250
    },

    # PLANNING MASTERY
    'planning_novice': {
        'name': 'Planning Novacek',
        'icon': '📋',
        'rarity': 'common',
        'description': '10 sessions v Planning',
        'type': 'category_mastery',
        'target': 10,
        'target_category': 'Planning',
        'mastery_level': 1,
        'category': 'mastery',
        'points': 10
    },
    'planning_apprentice': {
        'name': 'Planning Praktikant',
        'icon': '📋',
        'rarity': 'rare',
        'description': '50 sessions v Planning',
        'type': 'category_mastery',
        'target': 50,
        'target_category': 'Planning',
        'mastery_level': 2,
        'category': 'mastery',
        'points': 25
    },
    'planning_expert': {
        'name': 'Planning Expert',
        'icon': '📋',
        'rarity': 'rare',
        'description': '100 sessions v Planning',
        'type': 'category_mastery',
        'target': 100,
        'target_category': 'Planning',
        'mastery_level': 3,
        'category': 'mastery',
        'points': 50
    },
    'planning_master': {
        'name': 'Planning Mistr',
        'icon': '📋',
        'rarity': 'epic',
        'description': '250 sessions v Planning',
        'type': 'category_mastery',
        'target': 250,
        'target_category': 'Planning',
        'mastery_level': 4,
        'category': 'mastery',
        'points': 100
    },
    'planning_legend': {
        'name': 'Planning Legenda',
        'icon': '📋',
        'rarity': 'legendary',
        'description': '500 sessions v Planning',
        'type': 'category_mastery',
        'target': 500,
        'target_category': 'Planning',
        'mastery_level': 5,
        'category': 'mastery',
        'points': 250
    },

    # DESIGN MASTERY
    'design_novice': {
        'name': 'Design Novacek',
        'icon': '🎨',
        'rarity': 'common',
        'description': '10 sessions v Design',
        'type': 'category_mastery',
        'target': 10,
        'target_category': 'Design',
        'mastery_level': 1,
        'category': 'mastery',
        'points': 10
    },
    'design_apprentice': {
        'name': 'Design Praktikant',
        'icon': '🎨',
        'rarity': 'rare',
        'description': '50 sessions v Design',
        'type': 'category_mastery',
        'target': 50,
        'target_category': 'Design',
        'mastery_level': 2,
        'category': 'mastery',
        'points': 25
    },
    'design_expert': {
        'name': 'Design Expert',
        'icon': '🎨',
        'rarity': 'rare',
        'description': '100 sessions v Design',
        'type': 'category_mastery',
        'target': 100,
        'target_category': 'Design',
        'mastery_level': 3,
        'category': 'mastery',
        'points': 50
    },
    'design_master': {
        'name': 'Design Mistr',
        'icon': '🎨',
        'rarity': 'epic',
        'description': '250 sessions v Design',
        'type': 'category_mastery',
        'target': 250,
        'target_category': 'Design',
        'mastery_level': 4,
        'category': 'mastery',
        'points': 100
    },
    'design_legend': {
        'name': 'Design Legenda',
        'icon': '🎨',
        'rarity': 'legendary',
        'description': '500 sessions v Design',
        'type': 'category_mastery',
        'target': 500,
        'target_category': 'Design',
        'mastery_level': 5,
        'category': 'mastery',
        'points': 250
    },

    # REVIEW MASTERY
    'review_novice': {
        'name': 'Review Novacek',
        'icon': '🔍',
        'rarity': 'common',
        'description': '10 sessions v Review',
        'type': 'category_mastery',
        'target': 10,
        'target_category': 'Review',
        'mastery_level': 1,
        'category': 'mastery',
        'points': 10
    },
    'review_apprentice': {
        'name': 'Review Praktikant',
        'icon': '🔍',
        'rarity': 'rare',
        'description': '50 sessions v Review',
        'type': 'category_mastery',
        'target': 50,
        'target_category': 'Review',
        'mastery_level': 2,
        'category': 'mastery',
        'points': 25
    },
    'review_expert': {
        'name': 'Review Expert',
        'icon': '🔍',
        'rarity': 'rare',
        'description': '100 sessions v Review',
        'type': 'category_mastery',
        'target': 100,
        'target_category': 'Review',
        'mastery_level': 3,
        'category': 'mastery',
        'points': 50
    },
    'review_master': {
        'name': 'Review Mistr',
        'icon': '🔍',
        'rarity': 'epic',
        'description': '250 sessions v Review',
        'type': 'category_mastery',
        'target': 250,
        'target_category': 'Review',
        'mastery_level': 4,
        'category': 'mastery',
        'points': 100
    },
    'review_legend': {
        'name': 'Review Legenda',
        'icon': '🔍',
        'rarity': 'legendary',
        'description': '500 sessions v Review',
        'type': 'category_mastery',
        'target': 500,
        'target_category': 'Review',
        'mastery_level': 5,
        'category': 'mastery',
        'points': 250
    },

    # MEETING MASTERY
    'meeting_novice': {
        'name': 'Meeting Novacek',
        'icon': '👥',
        'rarity': 'common',
        'description': '10 sessions v Meeting',
        'type': 'category_mastery',
        'target': 10,
        'target_category': 'Meeting',
        'mastery_level': 1,
        'category': 'mastery',
        'points': 10
    },
    'meeting_apprentice': {
        'name': 'Meeting Praktikant',
        'icon': '👥',
        'rarity': 'rare',
        'description': '50 sessions v Meeting',
        'type': 'category_mastery',
        'target': 50,
        'target_category': 'Meeting',
        'mastery_level': 2,
        'category': 'mastery',
        'points': 25
    },
    'meeting_expert': {
        'name': 'Meeting Expert',
        'icon': '👥',
        'rarity': 'rare',
        'description': '100 sessions v Meeting',
        'type': 'category_mastery',
        'target': 100,
        'target_category': 'Meeting',
        'mastery_level': 3,
        'category': 'mastery',
        'points': 50
    },
    'meeting_master': {
        'name': 'Meeting Mistr',
        'icon': '👥',
        'rarity': 'epic',
        'description': '250 sessions v Meeting',
        'type': 'category_mastery',
        'target': 250,
        'target_category': 'Meeting',
        'mastery_level': 4,
        'category': 'mastery',
        'points': 100
    },
    'meeting_legend': {
        'name': 'Meeting Legenda',
        'icon': '👥',
        'rarity': 'legendary',
        'description': '500 sessions v Meeting',
        'type': 'category_mastery',
        'target': 500,
        'target_category': 'Meeting',
        'mastery_level': 5,
        'category': 'mastery',
        'points': 250
    },
}


def init_achievements():
    """Initialize achievements in database"""
    database = get_db()

    # Create index
    database.achievements.create_index([("achievement_id", 1)], unique=True)

    # Initialize all achievements
    for ach_id, definition in ACHIEVEMENTS_DEFINITIONS.items():
        database.achievements.update_one(
            {'achievement_id': ach_id},
            {
                '$setOnInsert': {
                    'achievement_id': ach_id,
                    'progress': 0,
                    'unlocked': False,
                    'unlocked_at': None,
                    'notified': False,
                    'created_at': datetime.now()
                }
            },
            upsert=True
        )


def _calculate_achievement_progress(ach_id, definition):
    """Calculate current progress for an achievement"""
    database = get_db()
    ach_type = definition['type']

    if ach_type == 'sessions_total':
        return database.sessions.count_documents({'completed': True})

    elif ach_type == 'streak':
        stats = get_streak_stats()
        return max(stats.get('current_streak', 0), stats.get('longest_streak', 0))

    elif ach_type == 'preset_count':
        preset = definition.get('preset', 'deep_work')
        return database.sessions.count_documents({
            'completed': True,
            'preset': preset
        })

    elif ach_type == 'unique_presets':
        pipeline = [
            {'$match': {'completed': True}},
            {'$group': {'_id': '$preset'}},
            {'$count': 'total'}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return result[0]['total'] if result else 0

    elif ach_type == 'perfect_day':
        # Check if any day has 5+ sessions with 90%+ avg rating
        min_sessions = definition.get('min_sessions', 5)
        min_rating = definition.get('min_rating', 90)
        pipeline = [
            {'$match': {'completed': True, 'productivity_rating': {'$exists': True, '$ne': None}}},
            {'$group': {
                '_id': '$date',
                'count': {'$sum': 1},
                'avg_rating': {'$avg': '$productivity_rating'}
            }},
            {'$match': {'count': {'$gte': min_sessions}, 'avg_rating': {'$gte': min_rating}}},
            {'$count': 'total'}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return result[0]['total'] if result else 0

    elif ach_type == 'avg_rating':
        min_sessions = definition.get('min_sessions', 20)
        pipeline = [
            {'$match': {'completed': True, 'productivity_rating': {'$exists': True, '$ne': None}}},
            {'$group': {
                '_id': None,
                'avg': {'$avg': '$productivity_rating'},
                'count': {'$sum': 1}
            }}
        ]
        result = list(database.sessions.aggregate(pipeline))
        if result and result[0]['count'] >= min_sessions:
            return round(result[0]['avg'], 1)
        return 0

    elif ach_type == 'consecutive_rating':
        min_rating = definition.get('min_rating', 70)
        sessions = list(database.sessions.find(
            {'completed': True},
            {'productivity_rating': 1}
        ).sort('created_at', 1))

        max_consecutive = 0
        current_consecutive = 0
        for s in sessions:
            rating = s.get('productivity_rating', 0)
            if rating and rating >= min_rating:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        return max_consecutive

    elif ach_type == 'time_sessions':
        hour_max = definition.get('hour_max')
        hour_min = definition.get('hour_min')
        query = {'completed': True}
        if hour_max:
            query['hour'] = {'$lt': hour_max}
        elif hour_min:
            query['hour'] = {'$gte': hour_min}
        return database.sessions.count_documents(query)

    elif ach_type == 'daily_max':
        pipeline = [
            {'$match': {'completed': True}},
            {'$group': {'_id': '$date', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
            {'$limit': 1}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return result[0]['count'] if result else 0

    elif ach_type == 'weekend_sessions':
        return database.sessions.count_documents({
            'completed': True,
            'day_of_week': {'$in': [5, 6]}
        })

    elif ach_type == 'coding_sessions':
        coding_categories = ['SOAP', 'Robot Framework', 'REST API', 'Database', 'Frontend']
        return database.sessions.count_documents({
            'completed': True,
            'category': {'$in': coding_categories}
        })

    elif ach_type == 'category_count':
        target_category = definition.get('target_category', 'Learning')
        return database.sessions.count_documents({
            'completed': True,
            'category': target_category
        })

    elif ach_type == 'unique_categories':
        pipeline = [
            {'$match': {'completed': True}},
            {'$group': {'_id': '$category'}},
            {'$count': 'total'}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return result[0]['total'] if result else 0

    elif ach_type == 'weekly_plans':
        return database.weekly_plans.count_documents({})

    elif ach_type == 'weekly_reviews':
        return database.weekly_reviews.count_documents({})

    elif ach_type == 'plan_completion':
        min_planned = definition.get('min_planned', 10)
        pipeline = [
            {'$match': {'planned_sessions': {'$gt': 0}}},
            {'$group': {
                '_id': None,
                'total_planned': {'$sum': '$planned_sessions'},
                'total_actual': {'$sum': '$actual_sessions'}
            }}
        ]
        result = list(database.daily_focus.aggregate(pipeline))
        if result and result[0]['total_planned'] >= min_planned:
            return round((result[0]['total_actual'] / result[0]['total_planned']) * 100, 1)
        return 0

    # ==========================================================================
    # NEW COMBO ACHIEVEMENT TYPES
    # ==========================================================================

    elif ach_type == 'daily_time_combo':
        # X+ sessions in specific time window in one day
        combo_target = definition.get('combo_target', 3)
        hour_min = definition.get('hour_min', 0)
        hour_max = definition.get('hour_max', 24)
        query = {'completed': True, 'hour': {'$gte': hour_min, '$lt': hour_max}}
        pipeline = [
            {'$match': query},
            {'$group': {'_id': '$date', 'count': {'$sum': 1}}},
            {'$match': {'count': {'$gte': combo_target}}},
            {'$count': 'total'}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return result[0]['total'] if result else 0

    elif ach_type == 'perfect_rating_day':
        # Day with X+ sessions all with Y+ rating
        min_sessions = definition.get('min_sessions', 5)
        min_rating = definition.get('min_rating', 80)
        pipeline = [
            {'$match': {'completed': True, 'productivity_rating': {'$exists': True, '$ne': None}}},
            {'$group': {
                '_id': '$date',
                'count': {'$sum': 1},
                'min_rating': {'$min': '$productivity_rating'}
            }},
            {'$match': {'count': {'$gte': min_sessions}, 'min_rating': {'$gte': min_rating}}},
            {'$count': 'total'}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return result[0]['total'] if result else 0

    elif ach_type == 'full_week':
        # Session every day in a week (7 consecutive days)
        pipeline = [
            {'$match': {'completed': True}},
            {'$group': {'_id': '$date'}},
            {'$sort': {'_id': 1}}
        ]
        dates = [doc['_id'] for doc in database.sessions.aggregate(pipeline)]
        if len(dates) < 7:
            return 0

        # Check for 7 consecutive days
        date_objects = []
        for d in dates:
            try:
                date_objects.append(datetime.strptime(d, '%Y-%m-%d').date())
            except (ValueError, TypeError):
                continue
        date_objects = sorted(set(date_objects))

        consecutive = 1
        max_consecutive = 1
        for i in range(1, len(date_objects)):
            if (date_objects[i] - date_objects[i-1]).days == 1:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 1
        return 1 if max_consecutive >= 7 else 0

    elif ach_type == 'workweek_sessions':
        # X+ sessions Mon-Fri in one week
        target = definition.get('target', 25)
        # Get sessions grouped by ISO week, only Mon-Fri (0-4)
        pipeline = [
            {'$match': {'completed': True, 'day_of_week': {'$in': [0, 1, 2, 3, 4]}}},
            {'$addFields': {
                'week': {'$dateFromString': {'dateString': '$date', 'format': '%Y-%m-%d'}}
            }},
            {'$group': {
                '_id': {'$isoWeek': '$week'},
                'count': {'$sum': 1}
            }},
            {'$match': {'count': {'$gte': target}}},
            {'$count': 'total'}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return result[0]['total'] if result else 0

    elif ach_type == 'daily_preset_variety':
        # X+ different presets in one day
        preset_count = definition.get('preset_count', 3)
        pipeline = [
            {'$match': {'completed': True}},
            {'$group': {
                '_id': '$date',
                'presets': {'$addToSet': '$preset'}
            }},
            {'$addFields': {'preset_count': {'$size': '$presets'}}},
            {'$match': {'preset_count': {'$gte': preset_count}}},
            {'$count': 'total'}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return result[0]['total'] if result else 0

    elif ach_type == 'daily_preset_count':
        # X+ sessions of specific preset in one day
        preset = definition.get('preset', 'deep_work')
        preset_target = definition.get('preset_target', 4)
        pipeline = [
            {'$match': {'completed': True, 'preset': preset}},
            {'$group': {'_id': '$date', 'count': {'$sum': 1}}},
            {'$match': {'count': {'$gte': preset_target}}},
            {'$count': 'total'}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return result[0]['total'] if result else 0

    elif ach_type == 'consecutive_preset':
        # X consecutive sessions with same preset
        target = definition.get('target', 2)
        preset = definition.get('preset', 'flow_mode')
        sessions = list(database.sessions.find(
            {'completed': True},
            {'preset': 1}
        ).sort('created_at', 1))

        max_consecutive = 0
        current_consecutive = 0
        for s in sessions:
            if s.get('preset') == preset:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        return max_consecutive

    elif ach_type == 'daily_category_combo':
        # Multiple specific categories in one day
        required = definition.get('required_categories', ['Coding', 'Learning'])
        pipeline = [
            {'$match': {'completed': True}},
            {'$group': {
                '_id': '$date',
                'categories': {'$addToSet': '$category'}
            }}
        ]
        days = list(database.sessions.aggregate(pipeline))
        count = 0
        for day in days:
            cats = set(day.get('categories', []))
            if all(c in cats for c in required):
                count += 1
        return count

    elif ach_type == 'daily_category_variety':
        # X+ different categories in one day
        category_count = definition.get('category_count', 4)
        pipeline = [
            {'$match': {'completed': True}},
            {'$group': {
                '_id': '$date',
                'categories': {'$addToSet': '$category'}
            }},
            {'$addFields': {'cat_count': {'$size': '$categories'}}},
            {'$match': {'cat_count': {'$gte': category_count}}},
            {'$count': 'total'}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return result[0]['total'] if result else 0

    elif ach_type == 'triple_category':
        # 3 sessions in 3 different categories (same day)
        pipeline = [
            {'$match': {'completed': True}},
            {'$group': {
                '_id': {'date': '$date', 'category': '$category'},
                'count': {'$sum': 1}
            }},
            {'$group': {
                '_id': '$_id.date',
                'categories_with_sessions': {
                    '$sum': {'$cond': [{'$gte': ['$count', 1]}, 1, 0]}
                }
            }},
            {'$match': {'categories_with_sessions': {'$gte': 3}}},
            {'$count': 'total'}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return result[0]['total'] if result else 0

    # ==========================================================================
    # SECRET/HIDDEN ACHIEVEMENT TYPES
    # ==========================================================================

    elif ach_type == 'secret_midnight':
        # Session completed at midnight (hour = 0)
        return database.sessions.count_documents({
            'completed': True,
            'hour': 0
        })

    elif ach_type == 'secret_early':
        # Session before 5 AM
        hour_max = definition.get('hour_max', 5)
        return database.sessions.count_documents({
            'completed': True,
            'hour': {'$lt': hour_max}
        })

    elif ach_type == 'secret_time':
        # Session completed at specific time (e.g., 11:11)
        hour = definition.get('hour', 11)
        minute = definition.get('minute', 11)
        time_str = f"{hour:02d}:{minute:02d}"
        return database.sessions.count_documents({
            'completed': True,
            'time': time_str
        })

    elif ach_type == 'secret_date':
        # Session on specific date (month/day)
        month = definition.get('month', 1)
        day = definition.get('day', 1)
        # Match dates ending with -MM-DD
        pattern = f"-{month:02d}-{day:02d}"
        pipeline = [
            {'$match': {'completed': True}},
            {'$match': {'date': {'$regex': pattern + '$'}}}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return len(result)

    elif ach_type == 'secret_exact_count':
        # Exactly X sessions in one day
        exact = definition.get('exact_sessions', 7)
        pipeline = [
            {'$match': {'completed': True}},
            {'$group': {'_id': '$date', 'count': {'$sum': 1}}},
            {'$match': {'count': exact}},
            {'$count': 'total'}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return result[0]['total'] if result else 0

    elif ach_type == 'secret_total':
        # Total sessions milestone
        return database.sessions.count_documents({'completed': True})

    elif ach_type == 'secret_minutes':
        # Total minutes milestone
        pipeline = [
            {'$match': {'completed': True}},
            {'$group': {'_id': None, 'total': {'$sum': '$duration_minutes'}}}
        ]
        result = list(database.sessions.aggregate(pipeline))
        return result[0]['total'] if result else 0

    elif ach_type == 'secret_breaks':
        # Count of breaks taken (estimate from sessions)
        return database.sessions.count_documents({'completed': True})

    elif ach_type == 'secret_fibonacci':
        # Fibonacci pattern in daily sessions (1,1,2,3,5,8)
        pipeline = [
            {'$match': {'completed': True}},
            {'$group': {'_id': '$date', 'count': {'$sum': 1}}},
            {'$sort': {'_id': 1}}
        ]
        days = list(database.sessions.aggregate(pipeline))
        if len(days) < 6:
            return 0

        counts = [d['count'] for d in days]
        fib = [1, 1, 2, 3, 5, 8]

        # Check if any 6 consecutive days match fibonacci
        for i in range(len(counts) - 5):
            if counts[i:i+6] == fib:
                return 1
        return 0

    # ==========================================================================
    # CATEGORY MASTERY TYPES
    # ==========================================================================

    elif ach_type == 'category_mastery':
        # Sessions in specific category
        target_category = definition.get('target_category', 'Coding')
        return database.sessions.count_documents({
            'completed': True,
            'category': target_category
        })

    elif ach_type == 'all_categories_level':
        # Level X+ in all categories
        min_level = definition.get('min_level', 2)
        categories = ['Coding', 'Learning', 'Writing', 'Planning', 'Design', 'Review', 'Meeting']
        level_thresholds = [10, 50, 100, 250, 500]

        count_at_level = 0
        for cat in categories:
            cat_count = database.sessions.count_documents({
                'completed': True,
                'category': cat
            })
            cat_level = 0
            for i, threshold in enumerate(level_thresholds):
                if cat_count >= threshold:
                    cat_level = i + 1
            if cat_level >= min_level:
                count_at_level += 1

        return count_at_level

    elif ach_type == 'max_category_level':
        # Highest level achieved in any category
        categories = ['Coding', 'Learning', 'Writing', 'Planning', 'Design', 'Review', 'Meeting']
        level_thresholds = [10, 50, 100, 250, 500]

        max_level = 0
        for cat in categories:
            cat_count = database.sessions.count_documents({
                'completed': True,
                'category': cat
            })
            for i, threshold in enumerate(level_thresholds):
                if cat_count >= threshold:
                    max_level = max(max_level, i + 1)

        return max_level

    elif ach_type == 'multi_category_level':
        # X categories at level Y+
        min_level = definition.get('min_level', 3)
        categories = ['Coding', 'Learning', 'Writing', 'Planning', 'Design', 'Review', 'Meeting']
        level_thresholds = [10, 50, 100, 250, 500]

        count_at_level = 0
        for cat in categories:
            cat_count = database.sessions.count_documents({
                'completed': True,
                'category': cat
            })
            cat_level = 0
            for i, threshold in enumerate(level_thresholds):
                if cat_count >= threshold:
                    cat_level = i + 1
            if cat_level >= min_level:
                count_at_level += 1

        return count_at_level

    return 0


def get_all_achievements():
    """Get all achievements with their current progress"""
    database = get_db()

    achievements = []
    for ach_id, definition in ACHIEVEMENTS_DEFINITIONS.items():
        # Get stored progress
        stored = database.achievements.find_one({'achievement_id': ach_id})

        # Calculate current progress
        progress = _calculate_achievement_progress(ach_id, definition)
        target = definition['target']
        percentage = min(100, round((progress / target) * 100)) if target > 0 else 0
        unlocked = stored.get('unlocked', False) if stored else False

        achievements.append({
            'id': ach_id,
            'name': definition['name'],
            'icon': definition['icon'],
            'rarity': definition['rarity'],
            'description': definition['description'],
            'category': definition['category'],
            'points': definition.get('points', 10),
            'progress': progress,
            'target': target,
            'percentage': percentage,
            'unlocked': unlocked,
            'unlocked_at': stored.get('unlocked_at') if stored else None
        })

    # Sort: unlocked first, then by percentage desc
    achievements.sort(key=lambda x: (not x['unlocked'], -x['percentage']))

    return achievements


def check_and_unlock_achievements():
    """Check all achievements and unlock newly completed ones"""
    database = get_db()
    newly_unlocked = []

    for ach_id, definition in ACHIEVEMENTS_DEFINITIONS.items():
        # Check if already unlocked
        stored = database.achievements.find_one({'achievement_id': ach_id})
        if stored and stored.get('unlocked'):
            continue

        # Calculate progress
        progress = _calculate_achievement_progress(ach_id, definition)
        target = definition['target']

        # Check if should unlock
        if progress >= target:
            now = datetime.now()
            database.achievements.update_one(
                {'achievement_id': ach_id},
                {
                    '$set': {
                        'progress': progress,
                        'unlocked': True,
                        'unlocked_at': now,
                        'notified': False,
                        'updated_at': now
                    }
                },
                upsert=True
            )

            newly_unlocked.append({
                'id': ach_id,
                'name': definition['name'],
                'icon': definition['icon'],
                'rarity': definition['rarity'],
                'description': definition['description'],
                'points': definition.get('points', 10)
            })
        else:
            # Update progress
            database.achievements.update_one(
                {'achievement_id': ach_id},
                {
                    '$set': {
                        'progress': progress,
                        'updated_at': datetime.now()
                    }
                },
                upsert=True
            )

    return newly_unlocked


def get_achievements_summary():
    """Get achievement statistics summary"""
    database = get_db()

    total = len(ACHIEVEMENTS_DEFINITIONS)
    unlocked = database.achievements.count_documents({'unlocked': True})

    # Calculate total points
    total_points = sum(d.get('points', 10) for d in ACHIEVEMENTS_DEFINITIONS.values())

    # Calculate earned points
    unlocked_docs = list(database.achievements.find({'unlocked': True}))
    earned_points = sum(
        ACHIEVEMENTS_DEFINITIONS.get(d['achievement_id'], {}).get('points', 10)
        for d in unlocked_docs
        if d['achievement_id'] in ACHIEVEMENTS_DEFINITIONS
    )

    # Count by rarity
    by_rarity = {'common': 0, 'rare': 0, 'epic': 0, 'legendary': 0}
    for d in unlocked_docs:
        if d['achievement_id'] in ACHIEVEMENTS_DEFINITIONS:
            rarity = ACHIEVEMENTS_DEFINITIONS[d['achievement_id']].get('rarity', 'common')
            by_rarity[rarity] += 1

    # Get recent unlocks
    recent = list(database.achievements.find(
        {'unlocked': True}
    ).sort('unlocked_at', -1).limit(5))

    recent_achievements = []
    for r in recent:
        if r['achievement_id'] in ACHIEVEMENTS_DEFINITIONS:
            definition = ACHIEVEMENTS_DEFINITIONS[r['achievement_id']]
            recent_achievements.append({
                'id': r['achievement_id'],
                'name': definition['name'],
                'icon': definition['icon'],
                'rarity': definition['rarity'],
                'unlocked_at': r.get('unlocked_at').isoformat() if r.get('unlocked_at') else None
            })

    return {
        'total': total,
        'unlocked': unlocked,
        'percentage': round((unlocked / total) * 100) if total > 0 else 0,
        'total_points': total_points,
        'earned_points': earned_points,
        'by_rarity': by_rarity,
        'recent': recent_achievements
    }


# =============================================================================
# XP / LEVELING SYSTEM
# =============================================================================

# Level progression table
LEVEL_TITLES = {
    1: 'Zacatecnik',
    2: 'Novacek',
    3: 'Ucedlik',
    4: 'Praktikant',
    5: 'Pokrocily',
    6: 'Zkuseny',
    7: 'Zdatny',
    8: 'Ostrileny',
    9: 'Schopny',
    10: 'Expert',
    11: 'Specialist',
    12: 'Profesional',
    13: 'Adept',
    14: 'Virtuoz',
    15: 'Mistr',
    16: 'Velmistr',
    17: 'Guru',
    18: 'Sage',
    19: 'Grandmaster',
    20: 'Legenda',
    25: 'Mytus',
    30: 'Titan'
}

# XP required for each level
LEVEL_XP_REQUIREMENTS = {
    1: 0,
    2: 100,
    3: 250,
    4: 500,
    5: 1000,
    6: 1750,
    7: 2750,
    8: 4000,
    9: 5500,
    10: 7500,
    11: 10000,
    12: 13000,
    13: 17000,
    14: 22000,
    15: 28000,
    16: 35000,
    17: 43000,
    18: 52000,
    19: 62000,
    20: 75000,
    25: 150000,
    30: 300000
}


def calculate_level_from_xp(xp):
    """Calculate level, title, and XP to next level from total XP

    Returns: (level, title, xp_to_next, current_level_xp, next_level_xp)
    """
    level = 1
    for lvl, required in sorted(LEVEL_XP_REQUIREMENTS.items()):
        if xp >= required:
            level = lvl
        else:
            break

    # Find title (use closest lower or equal level)
    title = 'Zacatecnik'
    for lvl, t in sorted(LEVEL_TITLES.items()):
        if level >= lvl:
            title = t

    # Find XP to next level
    next_level = level + 1
    current_level_xp = LEVEL_XP_REQUIREMENTS.get(level, 0)
    next_level_xp = LEVEL_XP_REQUIREMENTS.get(next_level)

    if next_level_xp is None:
        # Find next defined level
        for lvl in sorted(LEVEL_XP_REQUIREMENTS.keys()):
            if lvl > level:
                next_level_xp = LEVEL_XP_REQUIREMENTS[lvl]
                break

    if next_level_xp is None:
        next_level_xp = current_level_xp + 50000  # Default increment

    xp_to_next = next_level_xp - xp

    return level, title, max(0, xp_to_next), current_level_xp, next_level_xp


def get_user_profile():
    """Get or create user profile with XP and leveling info"""
    database = get_db()

    profile = database.user_profile.find_one({'user_id': 'default'})

    if not profile:
        # Create default profile
        profile = {
            'user_id': 'default',
            'xp': 0,
            'total_xp_earned': 0,
            'level': 1,
            'title': 'Zacatecnik',
            'streak_freezes_available': 1,
            'streak_freeze_used_dates': [],
            'vacation_mode': False,
            'vacation_days_remaining': 0,
            'vacation_start_date': None,
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        database.user_profile.insert_one(profile)

    # Calculate current level info
    level, title, xp_to_next, current_xp, next_xp = calculate_level_from_xp(profile.get('xp', 0))

    # Calculate progress percentage within current level
    level_progress = 0
    if next_xp > current_xp:
        progress_in_level = profile.get('xp', 0) - current_xp
        level_range = next_xp - current_xp
        level_progress = round((progress_in_level / level_range) * 100)

    return {
        'user_id': profile['user_id'],
        'xp': profile.get('xp', 0),
        'total_xp_earned': profile.get('total_xp_earned', 0),
        'level': level,
        'title': title,
        'xp_to_next_level': xp_to_next,
        'level_progress': level_progress,
        'streak_freezes_available': profile.get('streak_freezes_available', 0),
        'vacation_mode': profile.get('vacation_mode', False),
        'vacation_days_remaining': profile.get('vacation_days_remaining', 0)
    }


def add_xp(amount, source='session'):
    """Add XP to user profile and check for level up

    Args:
        amount: XP amount to add
        source: Source of XP ('session', 'achievement', 'challenge', 'quest')

    Returns: dict with new XP, level, and whether leveled up
    """
    database = get_db()

    # Get current profile
    profile = database.user_profile.find_one({'user_id': 'default'})
    old_xp = profile.get('xp', 0) if profile else 0
    old_level, _, _, _, _ = calculate_level_from_xp(old_xp)

    # Update XP
    new_xp = old_xp + amount
    new_level, new_title, xp_to_next, _, _ = calculate_level_from_xp(new_xp)

    # Check for level up rewards
    levels_gained = new_level - old_level
    streak_freezes_earned = levels_gained // 5  # +1 freeze every 5 levels

    update_data = {
        'xp': new_xp,
        'total_xp_earned': (profile.get('total_xp_earned', 0) if profile else 0) + amount,
        'level': new_level,
        'title': new_title,
        'updated_at': datetime.now()
    }

    if streak_freezes_earned > 0:
        current_freezes = profile.get('streak_freezes_available', 0) if profile else 0
        update_data['streak_freezes_available'] = min(3, current_freezes + streak_freezes_earned)

    database.user_profile.update_one(
        {'user_id': 'default'},
        {
            '$set': update_data,
            '$setOnInsert': {'created_at': datetime.now()}
        },
        upsert=True
    )

    # Log XP gain
    database.xp_history.insert_one({
        'amount': amount,
        'source': source,
        'old_xp': old_xp,
        'new_xp': new_xp,
        'created_at': datetime.now()
    })

    return {
        'xp_gained': amount,
        'new_xp': new_xp,
        'new_level': new_level,
        'new_title': new_title,
        'xp_to_next_level': xp_to_next,
        'leveled_up': new_level > old_level,
        'levels_gained': levels_gained,
        'streak_freezes_earned': streak_freezes_earned
    }


# =============================================================================
# STREAK PROTECTION
# =============================================================================

def use_streak_freeze():
    """Use a streak freeze to protect streak

    Returns: dict with success status and remaining freezes
    """
    database = get_db()

    profile = database.user_profile.find_one({'user_id': 'default'})
    if not profile:
        return {'success': False, 'error': 'No profile found'}

    freezes = profile.get('streak_freezes_available', 0)
    if freezes <= 0:
        return {'success': False, 'error': 'No freezes available'}

    today = date.today().isoformat()
    used_dates = profile.get('streak_freeze_used_dates', [])

    if today in used_dates:
        return {'success': False, 'error': 'Freeze already used today'}

    used_dates.append(today)

    database.user_profile.update_one(
        {'user_id': 'default'},
        {
            '$set': {
                'streak_freezes_available': freezes - 1,
                'streak_freeze_used_dates': used_dates,
                'updated_at': datetime.now()
            }
        }
    )

    return {
        'success': True,
        'freezes_remaining': freezes - 1,
        'freeze_date': today
    }


def toggle_vacation_mode(enable=True, days=7):
    """Enable or disable vacation mode

    Args:
        enable: True to enable, False to disable
        days: Number of vacation days (max 14)

    Returns: dict with vacation mode status
    """
    database = get_db()

    days = min(14, max(0, days))  # Cap at 14 days

    if enable:
        database.user_profile.update_one(
            {'user_id': 'default'},
            {
                '$set': {
                    'vacation_mode': True,
                    'vacation_days_remaining': days,
                    'vacation_start_date': date.today().isoformat(),
                    'updated_at': datetime.now()
                }
            },
            upsert=True
        )
    else:
        database.user_profile.update_one(
            {'user_id': 'default'},
            {
                '$set': {
                    'vacation_mode': False,
                    'vacation_days_remaining': 0,
                    'vacation_start_date': None,
                    'updated_at': datetime.now()
                }
            }
        )

    return {
        'vacation_mode': enable,
        'days_remaining': days if enable else 0
    }


def check_streak_with_protection():
    """Check streak status with protection mechanisms

    Returns: dict with streak info and protection status
    """
    database = get_db()

    # Get basic streak stats
    streak_stats = get_streak_stats()

    # Get user profile for protection info
    profile = database.user_profile.find_one({'user_id': 'default'})

    protection_active = False
    protection_type = None

    if profile:
        # Check vacation mode
        if profile.get('vacation_mode'):
            protection_active = True
            protection_type = 'vacation'

            # Check if vacation expired
            start_date = profile.get('vacation_start_date')
            days_remaining = profile.get('vacation_days_remaining', 0)

            if start_date:
                start = datetime.strptime(start_date, '%Y-%m-%d').date()
                days_passed = (date.today() - start).days

                if days_passed >= days_remaining:
                    # Vacation expired
                    toggle_vacation_mode(enable=False)
                    protection_active = False
                    protection_type = None

        # Check freeze usage
        freeze_dates = profile.get('streak_freeze_used_dates', [])
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        if yesterday in freeze_dates:
            protection_active = True
            protection_type = 'freeze'

    return {
        'current_streak': streak_stats['current_streak'],
        'longest_streak': streak_stats['longest_streak'],
        'total_days': streak_stats['total_days'],
        'protection_active': protection_active,
        'protection_type': protection_type,
        'freezes_available': profile.get('streak_freezes_available', 0) if profile else 0,
        'vacation_mode': profile.get('vacation_mode', False) if profile else False
    }


# =============================================================================
# CATEGORY SKILLS
# =============================================================================

def update_category_skill(category, minutes):
    """Update category skill progress

    Args:
        category: Category name
        minutes: Duration of session in minutes

    Returns: dict with updated skill info
    """
    database = get_db()

    # Calculate XP for this category (1 XP per minute)
    xp_earned = minutes

    skill = database.category_skills.find_one({'category': category})

    if skill:
        new_xp = skill.get('xp', 0) + xp_earned
        new_sessions = skill.get('sessions_count', 0) + 1
        new_minutes = skill.get('total_minutes', 0) + minutes
    else:
        new_xp = xp_earned
        new_sessions = 1
        new_minutes = minutes

    # Calculate level (same thresholds as mastery achievements)
    level_thresholds = [10, 50, 100, 250, 500]  # Sessions, not XP
    level = 0
    for i, threshold in enumerate(level_thresholds):
        if new_sessions >= threshold:
            level = i + 1

    database.category_skills.update_one(
        {'category': category},
        {
            '$set': {
                'category': category,
                'xp': new_xp,
                'level': level,
                'sessions_count': new_sessions,
                'total_minutes': new_minutes,
                'updated_at': datetime.now()
            },
            '$setOnInsert': {'created_at': datetime.now()}
        },
        upsert=True
    )

    return {
        'category': category,
        'xp': new_xp,
        'level': level,
        'sessions_count': new_sessions,
        'total_minutes': new_minutes
    }


def get_category_skills():
    """Get all category skills

    Returns: list of category skill objects
    """
    database = get_db()

    skills = list(database.category_skills.find())

    # Add level titles
    level_titles = {
        0: 'Nezacal',
        1: 'Novacek',
        2: 'Praktikant',
        3: 'Expert',
        4: 'Mistr',
        5: 'Legenda'
    }

    result = []
    for skill in skills:
        level = skill.get('level', 0)
        sessions = skill.get('sessions_count', 0)

        # Calculate progress to next level
        level_thresholds = [0, 10, 50, 100, 250, 500]
        current_threshold = level_thresholds[level] if level < len(level_thresholds) else 500
        next_threshold = level_thresholds[level + 1] if level + 1 < len(level_thresholds) else 1000

        progress = 0
        if next_threshold > current_threshold:
            progress = round(((sessions - current_threshold) / (next_threshold - current_threshold)) * 100)

        result.append({
            'category': skill['category'],
            'xp': skill.get('xp', 0),
            'level': level,
            'level_title': level_titles.get(level, 'Unknown'),
            'sessions_count': sessions,
            'total_minutes': skill.get('total_minutes', 0),
            'total_hours': round(skill.get('total_minutes', 0) / 60, 1),
            'progress_to_next': min(100, max(0, progress)),
            'sessions_to_next': max(0, next_threshold - sessions)
        })

    # Sort by level desc, then sessions desc
    result.sort(key=lambda x: (-x['level'], -x['sessions_count']))

    return result


# =============================================================================
# DAILY CHALLENGES
# =============================================================================

def get_or_create_daily_challenge(target_date=None):
    """Get or create daily challenge for a date

    Args:
        target_date: Date string or None for today

    Returns: dict with challenge info
    """
    database = get_db()

    if target_date is None:
        target_date = date.today().isoformat()
    elif isinstance(target_date, date):
        target_date = target_date.isoformat()

    # Check if challenge exists
    challenge = database.daily_challenges.find_one({'date': target_date})

    if challenge:
        challenge['_id'] = str(challenge['_id'])
        return challenge

    # Create new challenge (fallback - normally AI generates this)
    import random

    challenge_templates = [
        {
            'title': 'Ranni produktivita',
            'description': 'Dokoncete 3 sessions pred polednem',
            'target': 3,
            'condition_type': 'morning_sessions',
            'hour_max': 12,
            'difficulty': 'medium',
            'xp_reward': 50
        },
        {
            'title': 'Deep Focus',
            'description': 'Dokoncete 2 deep_work sessions',
            'target': 2,
            'condition_type': 'preset_count',
            'preset': 'deep_work',
            'difficulty': 'medium',
            'xp_reward': 40
        },
        {
            'title': 'Vysoce produktivni',
            'description': 'Dokoncete 3 sessions s hodnocenim 80%+',
            'target': 3,
            'condition_type': 'high_rating',
            'min_rating': 80,
            'difficulty': 'hard',
            'xp_reward': 75
        },
        {
            'title': 'Konzistence',
            'description': 'Dokoncete 5 sessions dnes',
            'target': 5,
            'condition_type': 'daily_sessions',
            'difficulty': 'medium',
            'xp_reward': 60
        },
        {
            'title': 'Rozmanitost',
            'description': 'Pracujte ve 3 ruznych kategoriich',
            'target': 3,
            'condition_type': 'unique_categories',
            'difficulty': 'easy',
            'xp_reward': 30
        }
    ]

    template = random.choice(challenge_templates)

    new_challenge = {
        'date': target_date,
        'challenge_id': f"dc_{target_date.replace('-', '')}",
        'title': template['title'],
        'description': template['description'],
        'target': template['target'],
        'condition_type': template['condition_type'],
        'difficulty': template['difficulty'],
        'xp_reward': template['xp_reward'],
        'progress': 0,
        'completed': False,
        'ai_generated': False,
        'created_at': datetime.now()
    }

    # Copy condition params
    for key in ['hour_max', 'hour_min', 'preset', 'min_rating']:
        if key in template:
            new_challenge[key] = template[key]

    database.daily_challenges.insert_one(new_challenge)
    new_challenge['_id'] = str(new_challenge['_id'])

    return new_challenge


def update_daily_challenge_progress():
    """Update daily challenge progress based on today's sessions

    Returns: dict with updated challenge and whether completed
    """
    database = get_db()
    today = date.today().isoformat()

    challenge = get_or_create_daily_challenge(today)
    if challenge.get('completed'):
        return {'challenge': challenge, 'newly_completed': False}

    # Calculate progress based on condition type
    condition = challenge.get('condition_type', 'daily_sessions')
    progress = 0

    if condition == 'daily_sessions':
        progress = database.sessions.count_documents({
            'date': today,
            'completed': True
        })

    elif condition == 'morning_sessions':
        hour_max = challenge.get('hour_max', 12)
        progress = database.sessions.count_documents({
            'date': today,
            'completed': True,
            'hour': {'$lt': hour_max}
        })

    elif condition == 'preset_count':
        preset = challenge.get('preset', 'deep_work')
        progress = database.sessions.count_documents({
            'date': today,
            'completed': True,
            'preset': preset
        })

    elif condition == 'high_rating':
        min_rating = challenge.get('min_rating', 80)
        progress = database.sessions.count_documents({
            'date': today,
            'completed': True,
            'productivity_rating': {'$gte': min_rating}
        })

    elif condition == 'unique_categories':
        pipeline = [
            {'$match': {'date': today, 'completed': True}},
            {'$group': {'_id': '$category'}},
            {'$count': 'total'}
        ]
        result = list(database.sessions.aggregate(pipeline))
        progress = result[0]['total'] if result else 0

    # Check completion
    target = challenge.get('target', 1)
    newly_completed = progress >= target and not challenge.get('completed')

    # Update challenge
    update_data = {
        'progress': progress,
        'updated_at': datetime.now()
    }

    if newly_completed:
        update_data['completed'] = True
        update_data['completed_at'] = datetime.now()

        # Award XP
        xp_reward = challenge.get('xp_reward', 50)
        add_xp(xp_reward, 'challenge')

    database.daily_challenges.update_one(
        {'date': today},
        {'$set': update_data}
    )

    challenge['progress'] = progress
    challenge['completed'] = newly_completed or challenge.get('completed', False)

    return {
        'challenge': challenge,
        'newly_completed': newly_completed,
        'xp_earned': challenge.get('xp_reward', 0) if newly_completed else 0
    }


# =============================================================================
# WEEKLY QUESTS
# =============================================================================

def get_or_create_weekly_quests(week_start=None):
    """Get or create weekly quests

    Args:
        week_start: Week start date (Monday) or None for current week

    Returns: list of quest objects
    """
    database = get_db()

    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    elif isinstance(week_start, str):
        week_start = datetime.strptime(week_start, '%Y-%m-%d').date()

    week_start_str = week_start.isoformat()

    # Check if quests exist
    quests_doc = database.weekly_quests.find_one({'week_start': week_start_str})

    if quests_doc:
        quests_doc['_id'] = str(quests_doc['_id'])
        return quests_doc.get('quests', [])

    # Create new quests (fallback - normally AI generates this)
    quests = [
        {
            'id': f"wq_sessions_{week_start_str.replace('-', '')}",
            'title': 'Tydenni maraton',
            'description': '20 sessions tento tyden',
            'target': 20,
            'condition_type': 'weekly_sessions',
            'progress': 0,
            'completed': False,
            'xp_reward': 150
        },
        {
            'id': f"wq_deep_{week_start_str.replace('-', '')}",
            'title': 'Deep Work tyden',
            'description': '10 deep_work sessions',
            'target': 10,
            'condition_type': 'weekly_preset',
            'preset': 'deep_work',
            'progress': 0,
            'completed': False,
            'xp_reward': 100
        },
        {
            'id': f"wq_streak_{week_start_str.replace('-', '')}",
            'title': 'Tydenni streak',
            'description': 'Session kazdy den',
            'target': 7,
            'condition_type': 'weekly_streak',
            'progress': 0,
            'completed': False,
            'xp_reward': 200
        }
    ]

    database.weekly_quests.insert_one({
        'week_start': week_start_str,
        'quests': quests,
        'ai_generated': False,
        'created_at': datetime.now()
    })

    return quests


def update_weekly_quest_progress(quest_id=None):
    """Update weekly quest progress

    Args:
        quest_id: Specific quest to update, or None for all

    Returns: dict with updated quests and completions
    """
    database = get_db()

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    week_start_str = week_start.isoformat()
    week_end_str = week_end.isoformat()

    quests = get_or_create_weekly_quests(week_start)
    newly_completed = []

    for quest in quests:
        if quest_id and quest['id'] != quest_id:
            continue

        if quest.get('completed'):
            continue

        condition = quest.get('condition_type', 'weekly_sessions')
        progress = 0

        if condition == 'weekly_sessions':
            progress = database.sessions.count_documents({
                'date': {'$gte': week_start_str, '$lte': week_end_str},
                'completed': True
            })

        elif condition == 'weekly_preset':
            preset = quest.get('preset', 'deep_work')
            progress = database.sessions.count_documents({
                'date': {'$gte': week_start_str, '$lte': week_end_str},
                'completed': True,
                'preset': preset
            })

        elif condition == 'weekly_streak':
            # Count unique days with sessions
            pipeline = [
                {'$match': {
                    'date': {'$gte': week_start_str, '$lte': week_end_str},
                    'completed': True
                }},
                {'$group': {'_id': '$date'}},
                {'$count': 'total'}
            ]
            result = list(database.sessions.aggregate(pipeline))
            progress = result[0]['total'] if result else 0

        quest['progress'] = progress

        # Check completion
        if progress >= quest['target'] and not quest.get('completed'):
            quest['completed'] = True
            quest['completed_at'] = datetime.now().isoformat()
            newly_completed.append(quest)

            # Award XP
            add_xp(quest.get('xp_reward', 100), 'quest')

    # Update in database
    database.weekly_quests.update_one(
        {'week_start': week_start_str},
        {
            '$set': {
                'quests': quests,
                'updated_at': datetime.now()
            }
        }
    )

    return {
        'quests': quests,
        'newly_completed': newly_completed,
        'total_xp_earned': sum(q.get('xp_reward', 0) for q in newly_completed)
    }
