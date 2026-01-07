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

        # Create indexes for calendar collections
        db.daily_focus.create_index([("date", -1)], unique=True)
        db.daily_focus.create_index([("theme", 1)])
        db.weekly_plans.create_index([("week_start", -1)], unique=True)
        db.weekly_plans.create_index([("year", 1), ("week_number", 1)])
        db.weekly_reviews.create_index([("week_start", -1)], unique=True)

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
