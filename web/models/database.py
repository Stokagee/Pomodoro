"""
PostgreSQL Database Connection and Operations
Migrated from MongoDB to PostgreSQL + pgvector
"""

import os
import json
import logging
from datetime import datetime, date, timedelta
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Union

import psycopg2
from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor, Json
from pgvector.psycopg2 import register_vector

logger = logging.getLogger(__name__)

# Database connection pool
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://pomodoro:pomodoro_secret@localhost:5432/pomodoro')
_pool = None


def get_pool():
    """Get or create connection pool."""
    global _pool
    if _pool is None:
        _pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=DATABASE_URL
        )
    return _pool


def init_db():
    """Initialize PostgreSQL connection and verify schema."""
    try:
        conn = get_pool().getconn()
        try:
            register_vector(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                # Verify pgvector extension
                cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                if cur.fetchone():
                    logger.info("PostgreSQL + pgvector connected successfully")
                else:
                    logger.warning("pgvector extension not found")
            conn.commit()
            return True
        finally:
            get_pool().putconn(conn)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


@contextmanager
def get_cursor(cursor_factory=RealDictCursor):
    """Context manager for database cursor."""
    conn = get_pool().getconn()
    try:
        register_vector(conn)
        cur = conn.cursor(cursor_factory=cursor_factory)
        yield cur
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        get_pool().putconn(conn)


def get_db():
    """Legacy compatibility - returns pool for now."""
    return get_pool()


def normalize_rating(rating):
    """Convert old 1-5 ratings to 0-100%"""
    if rating is None:
        return None
    if 1 <= rating <= 5:
        return rating * 20
    return rating


# =============================================================================
# SESSION FUNCTIONS
# =============================================================================

def log_session(preset, category, task, duration_minutes, completed=True,
                productivity_rating=None, notes='', notes_embedding=None):
    """Log a completed session to database."""
    now = datetime.now()

    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO sessions
            (preset, category, task, duration_minutes, completed,
             productivity_rating, notes, notes_embedding, date, time, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            preset, category, task[:200] if task else '',
            duration_minutes, completed,
            productivity_rating, notes[:500] if notes else '',
            notes_embedding,
            date.today(), now.time(), now
        ))
        result = cur.fetchone()
        return str(result['id'])


def get_today_stats():
    """Get statistics for today."""
    today_str = date.today().isoformat()

    with get_cursor() as cur:
        # Get all sessions for today
        cur.execute("""
            SELECT id, date, time, preset, category, task, duration_minutes,
                   completed, productivity_rating, notes, hour, day_of_week, created_at
            FROM sessions
            WHERE date = %s
            ORDER BY time DESC
        """, (today_str,))
        sessions = [dict(row) for row in cur.fetchall()]

        total_minutes = sum(
            s['duration_minutes']
            for s in sessions
            if s.get('completed', False)
        )

        avg_rating = 0
        rated_sessions = [s for s in sessions if s.get('productivity_rating')]
        if rated_sessions:
            normalized_ratings = [normalize_rating(s['productivity_rating']) for s in rated_sessions]
            avg_rating = sum(normalized_ratings) / len(normalized_ratings)

        # Convert for JSON serialization
        for s in sessions:
            s['_id'] = str(s['id'])
            s['id'] = str(s['id'])
            if s.get('created_at'):
                s['created_at'] = s['created_at'].isoformat()
            if s.get('date'):
                s['date'] = s['date'].isoformat() if isinstance(s['date'], date) else s['date']
            if s.get('time'):
                s['time'] = str(s['time'])
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
    """Get statistics for current week."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    with get_cursor() as cur:
        cur.execute("""
            SELECT date, time, preset, category, duration_minutes,
                   productivity_rating, hour, day_of_week
            FROM sessions
            WHERE date >= %s AND completed = TRUE
            ORDER BY date, time
        """, (week_start,))
        sessions = [dict(row) for row in cur.fetchall()]

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
        session_date = session['date']
        if isinstance(session_date, str):
            session_date = datetime.strptime(session_date, '%Y-%m-%d').date()
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
    """Get session history."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, date, time, preset, category, task, duration_minutes,
                   completed, productivity_rating, notes, created_at
            FROM sessions
            ORDER BY created_at DESC
            LIMIT %s
        """, (limit,))
        sessions = [dict(row) for row in cur.fetchall()]

    for s in sessions:
        s['_id'] = str(s['id'])
        s['id'] = str(s['id'])
        if s.get('created_at'):
            s['created_at'] = s['created_at'].isoformat()
        if s.get('date'):
            s['date'] = s['date'].isoformat() if isinstance(s['date'], date) else s['date']
        if s.get('time'):
            s['time'] = str(s['time'])
        if s.get('productivity_rating'):
            s['productivity_rating'] = normalize_rating(s['productivity_rating'])

    return sessions


def get_all_sessions():
    """Get all sessions for ML analysis."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, date, time, preset, category, task, duration_minutes,
                   completed, productivity_rating, notes, hour, day_of_week, created_at
            FROM sessions
            WHERE completed = TRUE
            ORDER BY date DESC, time DESC
        """)
        sessions = [dict(row) for row in cur.fetchall()]

    for s in sessions:
        s['_id'] = str(s['id'])
        if s.get('created_at'):
            s['created_at'] = s['created_at'].isoformat()
        if s.get('date'):
            s['date'] = s['date'].isoformat() if isinstance(s['date'], date) else s['date']
        if s.get('time'):
            s['time'] = str(s['time'])

    return sessions


def clear_all_sessions():
    """Delete all sessions - for testing purposes."""
    with get_cursor() as cur:
        cur.execute("DELETE FROM sessions")
        return cur.rowcount


def get_streak_stats():
    """Calculate current and longest streak."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT date
            FROM sessions
            WHERE completed = TRUE
            ORDER BY date DESC
        """)
        dates = [row['date'] for row in cur.fetchall()]

    if not dates:
        return {'current_streak': 0, 'longest_streak': 0, 'total_days': 0}

    # Convert to date objects
    date_objects = []
    for d in dates:
        if isinstance(d, str):
            try:
                date_objects.append(datetime.strptime(d, '%Y-%m-%d').date())
            except (ValueError, TypeError):
                continue
        elif isinstance(d, date):
            date_objects.append(d)

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
# INSIGHT & PREDICTION FUNCTIONS
# =============================================================================

def save_insight(insight_type, data):
    """Save ML insight to database."""
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO insights (type, data, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (type) DO UPDATE
            SET data = EXCLUDED.data, updated_at = EXCLUDED.updated_at
        """, (insight_type, Json(data), datetime.now()))


def get_insight(insight_type):
    """Get ML insight from database."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT type, data, created_at, updated_at
            FROM insights
            WHERE type = %s
        """, (insight_type,))
        row = cur.fetchone()
        if row:
            return dict(row)
    return None


def save_prediction(prediction_data):
    """Save prediction to database."""
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO predictions (date, data, created_at)
            VALUES (%s, %s, %s)
        """, (date.today(), Json(prediction_data), datetime.now()))


def get_latest_prediction():
    """Get latest prediction."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT date, data, created_at
            FROM predictions
            WHERE date = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (date.today(),))
        row = cur.fetchone()
        if row:
            result = dict(row)
            if result.get('date'):
                result['date'] = result['date'].isoformat()
            return result
    return None


# =============================================================================
# DAILY FOCUS FUNCTIONS
# =============================================================================

def get_daily_focus(target_date=None):
    """Get daily focus for a specific date."""
    if target_date is None:
        target_date = date.today()
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, date, themes, notes, planned_sessions,
                   actual_sessions, productivity_score, created_at, updated_at
            FROM daily_focus
            WHERE date = %s
        """, (target_date,))
        focus = cur.fetchone()

    if focus:
        focus = dict(focus)
        focus['_id'] = str(focus['id'])
        focus['date'] = focus['date'].isoformat() if isinstance(focus['date'], date) else focus['date']
        if focus.get('created_at'):
            focus['created_at'] = focus['created_at'].isoformat()
        if focus.get('updated_at'):
            focus['updated_at'] = focus['updated_at'].isoformat()

        # Ensure themes is a list
        if focus.get('themes') is None:
            focus['themes'] = []

        # Calculate total planned sessions
        focus['total_planned'] = sum(t.get('planned_sessions', 0) for t in focus.get('themes', []))

        # Backward compatibility
        if focus.get('themes') and len(focus['themes']) > 0:
            focus['theme'] = focus['themes'][0].get('theme')
            if not focus.get('planned_sessions'):
                focus['planned_sessions'] = focus['total_planned']
        else:
            focus['theme'] = None
            if not focus.get('planned_sessions'):
                focus['planned_sessions'] = 0

    return focus


def set_daily_focus(target_date, themes, notes=''):
    """Set or update daily focus for a specific date."""
    if isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

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

    with get_cursor() as cur:
        # Get actual sessions count
        cur.execute("""
            SELECT COUNT(*) as count
            FROM sessions
            WHERE date = %s AND completed = TRUE
        """, (target_date,))
        actual_sessions = cur.fetchone()['count']

        # Get productivity score
        cur.execute("""
            SELECT AVG(productivity_rating) as avg_rating
            FROM sessions
            WHERE date = %s AND completed = TRUE AND productivity_rating IS NOT NULL
        """, (target_date,))
        result = cur.fetchone()
        productivity_score = normalize_rating(result['avg_rating']) if result['avg_rating'] else 0

        # Upsert daily focus
        cur.execute("""
            INSERT INTO daily_focus
            (date, themes, notes, planned_sessions, actual_sessions, productivity_score, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date) DO UPDATE SET
                themes = EXCLUDED.themes,
                notes = EXCLUDED.notes,
                planned_sessions = EXCLUDED.planned_sessions,
                actual_sessions = EXCLUDED.actual_sessions,
                productivity_score = EXCLUDED.productivity_score,
                updated_at = EXCLUDED.updated_at
            RETURNING id
        """, (
            target_date, Json(clean_themes), str(notes)[:1000],
            total_planned, actual_sessions, round(productivity_score, 1),
            now, now
        ))

        return cur.fetchone() is not None


def update_daily_focus_stats(target_date):
    """Update actual_sessions and productivity_score for a date."""
    if isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    with get_cursor() as cur:
        # Get actual sessions count
        cur.execute("""
            SELECT COUNT(*) as count
            FROM sessions
            WHERE date = %s AND completed = TRUE
        """, (target_date,))
        actual_sessions = cur.fetchone()['count']

        # Get productivity score
        cur.execute("""
            SELECT AVG(productivity_rating) as avg_rating
            FROM sessions
            WHERE date = %s AND completed = TRUE AND productivity_rating IS NOT NULL
        """, (target_date,))
        result = cur.fetchone()
        productivity_score = normalize_rating(result['avg_rating']) if result['avg_rating'] else 0

        # Update
        cur.execute("""
            UPDATE daily_focus
            SET actual_sessions = %s, productivity_score = %s, updated_at = %s
            WHERE date = %s
        """, (actual_sessions, round(productivity_score, 1), datetime.now(), target_date))


# =============================================================================
# END DAY / DAILY RECAP FUNCTIONS
# =============================================================================

def get_completed_categories(target_date=None):
    """Get list of categories from completed sessions for a date.

    Returns: [{'category': 'Coding', 'sessions': 3, 'minutes': 156}, ...]
    """
    if target_date is None:
        target_date = date.today()
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    with get_cursor() as cur:
        cur.execute("""
            SELECT category,
                   COUNT(*) as sessions,
                   COALESCE(SUM(duration_minutes), 0) as minutes
            FROM sessions
            WHERE date = %s AND completed = TRUE
            GROUP BY category
            ORDER BY sessions DESC
        """, (target_date,))
        results = cur.fetchall()

    return [dict(r) for r in results] if results else []


def complete_day(target_date, end_mood, end_notes=''):
    """Complete a day with end-of-day recap and auto-finalize categories.

    This function:
    1. Gets today's completed sessions and their categories
    2. Merges with existing daily_focus themes (doesn't overwrite morning plan)
    3. Adds categories that were actually worked on
    4. Saves end_mood, end_notes, marks day_completed=TRUE

    Returns: dict with updated daily_focus data
    """
    if isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
    elif target_date is None:
        target_date = date.today()

    now = datetime.now()

    # Get completed categories for the day
    completed_cats = get_completed_categories(target_date)

    with get_cursor() as cur:
        # Get existing daily_focus
        cur.execute("""
            SELECT id, themes, notes, planned_sessions, actual_sessions,
                   productivity_score, end_mood, end_notes, day_completed
            FROM daily_focus
            WHERE date = %s
        """, (target_date,))
        existing = cur.fetchone()

        # Prepare themes array
        existing_themes = existing['themes'] if existing and existing.get('themes') else []
        if isinstance(existing_themes, str):
            import json
            existing_themes = json.loads(existing_themes)

        # Create a map of existing theme names to their planned sessions
        existing_theme_map = {
            t.get('theme', ''): t
            for t in existing_themes
            if t.get('theme')
        }

        # Merge: keep morning planned sessions, add actual session categories
        merged_themes = []
        seen_categories = set()

        # First, add existing morning themes (with their planned sessions)
        for theme_obj in existing_themes:
            if theme_obj.get('theme'):
                theme_name = theme_obj['theme']
                seen_categories.add(theme_name)

                # Check if this category was actually worked on today
                actual_data = next((c for c in completed_cats if c['category'] == theme_name), None)

                merged_theme = {
                    'theme': theme_name,
                    'planned_sessions': theme_obj.get('planned_sessions', 1),
                    'actual_sessions': actual_data['sessions'] if actual_data else 0,
                    'notes': theme_obj.get('notes', '')
                }
                merged_themes.append(merged_theme)

        # Then, add categories that were worked on but weren't in morning plan
        for cat in completed_cats:
            if cat['category'] not in seen_categories:
                merged_themes.append({
                    'theme': cat['category'],
                    'planned_sessions': 0,  # Wasn't planned
                    'actual_sessions': cat['sessions'],
                    'notes': ''
                })
                seen_categories.add(cat['category'])

        # Get actual sessions count and productivity score
        cur.execute("""
            SELECT COUNT(*) as count
            FROM sessions
            WHERE date = %s AND completed = TRUE
        """, (target_date,))
        actual_sessions = cur.fetchone()['count']

        cur.execute("""
            SELECT AVG(productivity_rating) as avg_rating
            FROM sessions
            WHERE date = %s AND completed = TRUE AND productivity_rating IS NOT NULL
        """, (target_date,))
        result = cur.fetchone()
        productivity_score = normalize_rating(result['avg_rating']) if result['avg_rating'] else 0

        # Import json for JSON serialization
        import json

        # UPSERT into daily_focus
        cur.execute("""
            INSERT INTO daily_focus
            (date, themes, notes, planned_sessions, actual_sessions, productivity_score,
             end_mood, end_notes, day_completed, completed_at, created_at, updated_at)
            VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date) DO UPDATE SET
                themes = EXCLUDED.themes,
                actual_sessions = EXCLUDED.actual_sessions,
                productivity_score = EXCLUDED.productivity_score,
                end_mood = EXCLUDED.end_mood,
                end_notes = EXCLUDED.end_notes,
                day_completed = EXCLUDED.day_completed,
                completed_at = EXCLUDED.completed_at,
                updated_at = EXCLUDED.updated_at
            RETURNING id, date, themes, notes, planned_sessions, actual_sessions,
                      productivity_score, end_mood, end_notes, day_completed, completed_at
        """, (
            target_date,
            json.dumps(merged_themes) if merged_themes else '[]',
            existing['notes'] if existing and existing.get('notes') else '',
            sum(t.get('planned_sessions', 0) for t in merged_themes),
            actual_sessions,
            round(productivity_score, 1),
            round(float(end_mood), 2) if end_mood is not None else None,
            str(end_notes)[:500] if end_notes else '',
            True,
            now,
            now if not existing else existing['created_at'],
            now
        ))

        result = cur.fetchone()

    return dict(result) if result else None


# =============================================================================
# SYSTEM STATE FUNCTIONS
# =============================================================================

def get_system_state(key: str) -> Optional[Dict[str, Any]]:
    """Get system state value by key.

    Args:
        key: State key (e.g., 'auto_end_day')

    Returns:
        dict with 'value' and 'updated_at', or None if not found
    """
    with get_cursor() as cur:
        cur.execute("""
            SELECT value, updated_at
            FROM system_state
            WHERE key = %s
        """, (key,))
        result = cur.fetchone()

        if result:
            state = dict(result)
            # Parse JSONB if it's a string
            if isinstance(state['value'], str):
                state['value'] = json.loads(state['value'])
            return state
        return None


def set_system_state(key: str, value: Dict[str, Any]) -> bool:
    """Set system state value (upsert).

    Args:
        key: State key
        value: Dictionary value to store

    Returns:
        True if successful
    """
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO system_state (key, value, updated_at)
            VALUES (%s, %s::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = NOW()
            RETURNING key
        """, (key, json.dumps(value)))
        return cur.fetchone() is not None


def get_auto_end_day_state() -> Dict[str, Any]:
    """Get auto end-day state.

    Returns:
        dict with 'enabled', 'last_completed_date', 'last_run_at'
    """
    state = get_system_state('auto_end_day')
    if not state:
        # Initialize if doesn't exist
        default_state = {
            'enabled': True,
            'last_completed_date': None,
            'last_run_at': None
        }
        set_system_state('auto_end_day', default_state)
        return default_state
    return state['value']


def update_auto_end_day_state(**kwargs) -> bool:
    """Update auto end-day state fields.

    Args:
        **kwargs: Fields to update (e.g., last_completed_date='2025-01-13')

    Returns:
        True if successful
    """
    current_state = get_auto_end_day_state()
    current_state.update(kwargs)
    return set_system_state('auto_end_day', current_state)


def check_and_complete_previous_day(target_date: date) -> Optional[Dict[str, Any]]:
    """Check if previous day needs to be completed and do it.

    This function checks if the target date is already completed,
    and if not, automatically completes it with calculated stats.

    Args:
        target_date: The date to check/complete (typically yesterday)

    Returns:
        dict with completion result and 'auto_completed': True flag,
        or None if already completed
    """
    # Check if already completed
    with get_cursor() as cur:
        cur.execute("""
            SELECT day_completed, completed_at
            FROM daily_focus
            WHERE date = %s
        """, (target_date,))
        result = cur.fetchone()

        if result and result['day_completed']:
            logger.info(f"Day {target_date} already completed at {result['completed_at']}")
            return None

    # Not completed, auto-complete it
    logger.info(f"Auto-completing previous day: {target_date}")

    # Calculate end_mood from sessions (or use neutral 50 if no sessions)
    with get_cursor() as cur:
        cur.execute("""
            SELECT AVG(productivity_rating) as avg_rating
            FROM sessions
            WHERE date = %s AND completed = TRUE AND productivity_rating IS NOT NULL
        """, (target_date,))
        rating_result = cur.fetchone()
        end_mood = normalize_rating(rating_result['avg_rating']) if rating_result and rating_result['avg_rating'] else 50.0

    end_notes = "Auto-completed by system"

    # Complete the day
    result = complete_day(target_date, end_mood, end_notes)

    if result:
        # Mark as auto-completed
        with get_cursor() as cur:
            cur.execute("""
                UPDATE daily_focus
                SET completed_at = NOW()
                WHERE date = %s
            """, (target_date,))

        # Update state
        update_auto_end_day_state(
            last_completed_date=str(target_date),
            last_run_at=datetime.now().isoformat()
        )

        logger.info(f"Successfully auto-completed day {target_date}")
        return {**result, 'auto_completed': True}

    return None


# =============================================================================
# WELLNESS CHECKIN FUNCTIONS
# =============================================================================

def calculate_overall_wellness(sleep, energy, mood, stress, motivation, focus):
    """Calculate weighted overall wellness score."""
    # Stress is inverse: lower stress = higher wellness contribution
    stress_contribution = (100 - stress) if stress is not None else 50

    values = {
        'sleep': (sleep, 0.20),
        'energy': (energy, 0.20),
        'mood': (mood, 0.15),
        'stress': (stress_contribution, 0.15),
        'motivation': (motivation, 0.15),
        'focus': (focus, 0.15)
    }

    total_weight = 0
    weighted_sum = 0

    for key, (value, weight) in values.items():
        if value is not None:
            weighted_sum += value * weight
            total_weight += weight

    if total_weight > 0:
        return round(weighted_sum / total_weight * (1 / 1), 1)  # Normalize if not all provided
    return None


def save_wellness_checkin(target_date, sleep_quality=None, energy_level=None,
                          mood=None, stress_level=None, motivation=None,
                          focus_ability=None, notes=''):
    """Save or update wellness check-in for a date."""
    if isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    overall = calculate_overall_wellness(
        sleep_quality, energy_level, mood, stress_level, motivation, focus_ability
    )

    now = datetime.now()

    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO wellness_checkins
            (date, sleep_quality, energy_level, mood, stress_level,
             motivation, focus_ability, overall_wellness, notes, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date) DO UPDATE SET
                sleep_quality = EXCLUDED.sleep_quality,
                energy_level = EXCLUDED.energy_level,
                mood = EXCLUDED.mood,
                stress_level = EXCLUDED.stress_level,
                motivation = EXCLUDED.motivation,
                focus_ability = EXCLUDED.focus_ability,
                overall_wellness = EXCLUDED.overall_wellness,
                notes = EXCLUDED.notes,
                updated_at = EXCLUDED.updated_at
            RETURNING id
        """, (
            target_date, sleep_quality, energy_level, mood, stress_level,
            motivation, focus_ability, overall, notes[:500] if notes else '',
            now, now
        ))
        result = cur.fetchone()
        return str(result['id']) if result else None


def get_wellness_checkin(target_date=None):
    """Get wellness check-in for a specific date (default: today)."""
    if target_date is None:
        target_date = date.today()
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, date, sleep_quality, energy_level, mood, stress_level,
                   motivation, focus_ability, overall_wellness, notes,
                   created_at, updated_at
            FROM wellness_checkins
            WHERE date = %s
        """, (target_date,))
        wellness = cur.fetchone()

    if wellness:
        wellness = dict(wellness)
        wellness['_id'] = str(wellness['id'])
        wellness['id'] = str(wellness['id'])
        wellness['date'] = wellness['date'].isoformat() if isinstance(wellness['date'], date) else wellness['date']
        if wellness.get('created_at'):
            wellness['created_at'] = wellness['created_at'].isoformat()
        if wellness.get('updated_at'):
            wellness['updated_at'] = wellness['updated_at'].isoformat()

        # Convert Decimal to float for JSON serialization
        for key in ['sleep_quality', 'energy_level', 'mood', 'stress_level',
                    'motivation', 'focus_ability', 'overall_wellness']:
            if wellness.get(key) is not None:
                wellness[key] = float(wellness[key])

    return wellness


def get_wellness_history(days=30):
    """Get wellness check-in history for trend analysis."""
    start_date = date.today() - timedelta(days=days)

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, date, sleep_quality, energy_level, mood, stress_level,
                   motivation, focus_ability, overall_wellness, notes,
                   created_at
            FROM wellness_checkins
            WHERE date >= %s
            ORDER BY date DESC
        """, (start_date,))
        history = [dict(row) for row in cur.fetchall()]

    for w in history:
        w['_id'] = str(w['id'])
        w['id'] = str(w['id'])
        w['date'] = w['date'].isoformat() if isinstance(w['date'], date) else w['date']
        if w.get('created_at'):
            w['created_at'] = w['created_at'].isoformat()

        # Convert Decimal to float
        for key in ['sleep_quality', 'energy_level', 'mood', 'stress_level',
                    'motivation', 'focus_ability', 'overall_wellness']:
            if w.get(key) is not None:
                w[key] = float(w[key])

    return history


def get_wellness_average(days=7):
    """Get average wellness scores for ML integration."""
    start_date = date.today() - timedelta(days=days)

    with get_cursor() as cur:
        cur.execute("""
            SELECT
                AVG(sleep_quality) as avg_sleep,
                AVG(energy_level) as avg_energy,
                AVG(mood) as avg_mood,
                AVG(stress_level) as avg_stress,
                AVG(motivation) as avg_motivation,
                AVG(focus_ability) as avg_focus,
                AVG(overall_wellness) as avg_overall,
                COUNT(*) as checkin_count
            FROM wellness_checkins
            WHERE date >= %s
        """, (start_date,))
        result = cur.fetchone()

    if result:
        return {
            'avg_sleep': float(result['avg_sleep']) if result['avg_sleep'] else None,
            'avg_energy': float(result['avg_energy']) if result['avg_energy'] else None,
            'avg_mood': float(result['avg_mood']) if result['avg_mood'] else None,
            'avg_stress': float(result['avg_stress']) if result['avg_stress'] else None,
            'avg_motivation': float(result['avg_motivation']) if result['avg_motivation'] else None,
            'avg_focus': float(result['avg_focus']) if result['avg_focus'] else None,
            'avg_overall': float(result['avg_overall']) if result['avg_overall'] else None,
            'checkin_count': result['checkin_count'],
            'days': days
        }
    return None


# =============================================================================
# CALENDAR FUNCTIONS
# =============================================================================

def get_calendar_month(year, month):
    """Get all daily focus data for a month."""
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    with get_cursor() as cur:
        # Get daily focus data (including end_mood, day_completed)
        cur.execute("""
            SELECT date, themes, notes, planned_sessions, end_mood, day_completed
            FROM daily_focus
            WHERE date >= %s AND date <= %s
        """, (first_day, last_day))
        focus_data = {row['date'].isoformat() if isinstance(row['date'], date) else row['date']: dict(row)
                      for row in cur.fetchall()}

        # Get sessions aggregated by date
        cur.execute("""
            SELECT date,
                   COUNT(*) as sessions,
                   SUM(duration_minutes) as total_minutes,
                   ARRAY_AGG(productivity_rating) FILTER (WHERE productivity_rating IS NOT NULL) as ratings
            FROM sessions
            WHERE date >= %s AND date <= %s AND completed = TRUE
            GROUP BY date
        """, (first_day, last_day))
        sessions_data = {row['date'].isoformat() if isinstance(row['date'], date) else row['date']: dict(row)
                         for row in cur.fetchall()}

    # Build result
    result = {}
    current = first_day
    while current <= last_day:
        date_str = current.isoformat()
        focus = focus_data.get(date_str, {})
        session_info = sessions_data.get(date_str, {})

        # Calculate avg rating
        ratings = session_info.get('ratings', []) or []
        avg_rating = 0
        if ratings:
            normalized = [normalize_rating(r) for r in ratings if r is not None]
            avg_rating = sum(normalized) / len(normalized) if normalized else 0

        # Handle themes
        themes = focus.get('themes', []) or []
        total_planned = sum(t.get('planned_sessions', 0) for t in themes) if themes else 0

        result[date_str] = {
            'date': date_str,
            'day_of_week': current.weekday(),
            'themes': themes,
            'theme': themes[0]['theme'] if themes else None,
            'notes': focus.get('notes', ''),
            'total_planned': total_planned,
            'planned_sessions': total_planned,
            'actual_sessions': session_info.get('sessions', 0),
            'total_minutes': session_info.get('total_minutes', 0) or 0,
            'productivity_score': round(avg_rating, 1),
            'end_mood': focus.get('end_mood'),
            'day_completed': focus.get('day_completed', False)
        }
        current += timedelta(days=1)

    return result


def get_calendar_week(week_start_date):
    """Get daily focus data for a week."""
    if isinstance(week_start_date, str):
        week_start_date = datetime.strptime(week_start_date, '%Y-%m-%d').date()

    # Adjust to Monday
    days_since_monday = week_start_date.weekday()
    week_start = week_start_date - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=6)

    with get_cursor() as cur:
        # Get daily focus data (including end_mood, day_completed)
        cur.execute("""
            SELECT date, themes, notes, planned_sessions, end_mood, day_completed
            FROM daily_focus
            WHERE date >= %s AND date <= %s
        """, (week_start, week_end))
        focus_data = {row['date'].isoformat() if isinstance(row['date'], date) else row['date']: dict(row)
                      for row in cur.fetchall()}

        # Get sessions data
        cur.execute("""
            SELECT date,
                   COUNT(*) as sessions,
                   SUM(duration_minutes) as total_minutes,
                   ARRAY_AGG(productivity_rating) FILTER (WHERE productivity_rating IS NOT NULL) as ratings,
                   ARRAY_AGG(category) as categories
            FROM sessions
            WHERE date >= %s AND date <= %s AND completed = TRUE
            GROUP BY date
        """, (week_start, week_end))
        sessions_data = {row['date'].isoformat() if isinstance(row['date'], date) else row['date']: dict(row)
                         for row in cur.fetchall()}

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
        focus = focus_data.get(date_str, {})
        session_info = sessions_data.get(date_str, {})

        ratings = session_info.get('ratings', []) or []
        avg_rating = 0
        if ratings:
            normalized = [normalize_rating(r) for r in ratings if r is not None]
            avg_rating = sum(normalized) / len(normalized) if normalized else 0

        themes = focus.get('themes', []) or []
        total_planned = sum(t.get('planned_sessions', 0) for t in themes) if themes else 0

        result['days'][date_str] = {
            'date': date_str,
            'day_name': day_names[i],
            'day_of_week': i,
            'themes': themes,
            'theme': themes[0]['theme'] if themes else None,
            'notes': focus.get('notes', ''),
            'total_planned': total_planned,
            'planned_sessions': total_planned,
            'actual_sessions': session_info.get('sessions', 0),
            'total_minutes': session_info.get('total_minutes', 0) or 0,
            'productivity_score': round(avg_rating, 1),
            'categories': session_info.get('categories', []) or [],
            'end_mood': focus.get('end_mood'),
            'day_completed': focus.get('day_completed', False)
        }
        current += timedelta(days=1)

    return result


# =============================================================================
# WEEKLY PLAN FUNCTIONS
# =============================================================================

def get_weekly_plan(week_start_date):
    """Get weekly plan for a specific week."""
    if isinstance(week_start_date, str):
        week_start_date = datetime.strptime(week_start_date, '%Y-%m-%d').date()

    # Adjust to Monday
    days_since_monday = week_start_date.weekday()
    week_start = week_start_date - timedelta(days=days_since_monday)

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, week_start, week_number, year, goals, days, created_at, updated_at
            FROM weekly_plans
            WHERE week_start = %s
        """, (week_start,))
        plan = cur.fetchone()

    if plan:
        plan = dict(plan)
        plan['_id'] = str(plan['id'])
        plan['week_start'] = plan['week_start'].isoformat() if isinstance(plan['week_start'], date) else plan['week_start']
        if plan.get('created_at'):
            plan['created_at'] = plan['created_at'].isoformat()
        if plan.get('updated_at'):
            plan['updated_at'] = plan['updated_at'].isoformat()

    return plan


def save_weekly_plan(week_start_date, days, goals=None):
    """Save or update weekly plan."""
    if isinstance(week_start_date, str):
        week_start_date = datetime.strptime(week_start_date, '%Y-%m-%d').date()

    # Adjust to Monday
    days_since_monday = week_start_date.weekday()
    week_start = week_start_date - timedelta(days=days_since_monday)

    # Calculate ISO week number
    iso_calendar = week_start.isocalendar()
    now = datetime.now()

    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO weekly_plans
            (week_start, week_number, year, days, goals, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (week_start) DO UPDATE SET
                days = EXCLUDED.days,
                goals = EXCLUDED.goals,
                updated_at = EXCLUDED.updated_at
            RETURNING id
        """, (
            week_start, iso_calendar[1], iso_calendar[0],
            Json(days), Json(goals or []), now, now
        ))

    # Update daily_focus for each day
    for day in days:
        if day.get('themes'):
            set_daily_focus(day['date'], day['themes'], day.get('notes', ''))

    return True


# =============================================================================
# WEEKLY REVIEW FUNCTIONS
# =============================================================================

def get_weekly_review(week_start_date):
    """Get weekly review for a specific week."""
    if isinstance(week_start_date, str):
        week_start_date = datetime.strptime(week_start_date, '%Y-%m-%d').date()

    days_since_monday = week_start_date.weekday()
    week_start = week_start_date - timedelta(days=days_since_monday)

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, week_start, week_number, year, stats, theme_breakdown,
                   reflections, next_week_goals, ml_insights, created_at
            FROM weekly_reviews
            WHERE week_start = %s
        """, (week_start,))
        review = cur.fetchone()

    if review:
        review = dict(review)
        review['_id'] = str(review['id'])
        review['week_start'] = review['week_start'].isoformat() if isinstance(review['week_start'], date) else review['week_start']
        if review.get('created_at'):
            review['created_at'] = review['created_at'].isoformat()

    return review


def generate_weekly_stats(week_start_date):
    """Generate statistics for weekly review."""
    if isinstance(week_start_date, str):
        week_start_date = datetime.strptime(week_start_date, '%Y-%m-%d').date()

    days_since_monday = week_start_date.weekday()
    week_start = week_start_date - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=6)

    with get_cursor() as cur:
        # Get all sessions for the week
        cur.execute("""
            SELECT date, category, duration_minutes, productivity_rating
            FROM sessions
            WHERE date >= %s AND date <= %s AND completed = TRUE
        """, (week_start, week_end))
        sessions = [dict(row) for row in cur.fetchall()]

        # Get total session count including incomplete
        cur.execute("""
            SELECT COUNT(*) as count
            FROM sessions
            WHERE date >= %s AND date <= %s
        """, (week_start, week_end))
        all_sessions_count = cur.fetchone()['count']

    if not sessions:
        return {
            'total_sessions': 0,
            'total_hours': 0,
            'avg_productivity': 0,
            'completed_ratio': 0,
            'best_day': None,
            'best_theme': None,
            'theme_breakdown': []
        }

    total_sessions = len(sessions)
    total_minutes = sum(s.get('duration_minutes', 0) for s in sessions)

    ratings = [normalize_rating(s['productivity_rating'])
               for s in sessions
               if s.get('productivity_rating') is not None]
    avg_productivity = sum(ratings) / len(ratings) if ratings else 0

    completed_ratio = (total_sessions / all_sessions_count * 100) if all_sessions_count > 0 else 0

    # Find best day
    day_stats = {}
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    for s in sessions:
        d = s['date'].isoformat() if isinstance(s['date'], date) else s['date']
        if d not in day_stats:
            day_stats[d] = {'sessions': 0, 'ratings': []}
        day_stats[d]['sessions'] += 1
        if s.get('productivity_rating'):
            day_stats[d]['ratings'].append(normalize_rating(s['productivity_rating']))

    best_day = None
    best_day_score = 0
    for d, stats in day_stats.items():
        if stats['ratings']:
            score = sum(stats['ratings']) / len(stats['ratings'])
            if score > best_day_score:
                best_day_score = score
                day_date = datetime.strptime(d, '%Y-%m-%d').date() if isinstance(d, str) else d
                best_day = day_names[day_date.weekday()]

    # Theme/category breakdown
    category_stats = {}
    for s in sessions:
        cat = s.get('category', 'Other')
        if cat not in category_stats:
            category_stats[cat] = {'sessions': 0, 'ratings': []}
        category_stats[cat]['sessions'] += 1
        if s.get('productivity_rating'):
            category_stats[cat]['ratings'].append(normalize_rating(s['productivity_rating']))

    theme_breakdown = []
    best_theme = None
    best_theme_score = 0

    for theme, stats in category_stats.items():
        avg_rating = sum(stats['ratings']) / len(stats['ratings']) if stats['ratings'] else 0
        theme_breakdown.append({
            'theme': theme,
            'sessions': stats['sessions'],
            'avg_rating': round(avg_rating, 1)
        })
        if avg_rating > best_theme_score:
            best_theme_score = avg_rating
            best_theme = theme

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
    """Save weekly review."""
    if isinstance(week_start_date, str):
        week_start_date = datetime.strptime(week_start_date, '%Y-%m-%d').date()

    days_since_monday = week_start_date.weekday()
    week_start = week_start_date - timedelta(days=days_since_monday)

    stats = generate_weekly_stats(week_start)
    iso_calendar = week_start.isocalendar()
    now = datetime.now()

    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO weekly_reviews
            (week_start, week_number, year, stats, theme_breakdown, reflections,
             next_week_goals, ml_insights, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (week_start) DO UPDATE SET
                stats = EXCLUDED.stats,
                theme_breakdown = EXCLUDED.theme_breakdown,
                reflections = EXCLUDED.reflections,
                next_week_goals = EXCLUDED.next_week_goals,
                ml_insights = EXCLUDED.ml_insights
            RETURNING id
        """, (
            week_start, iso_calendar[1], iso_calendar[0],
            Json({
                'total_sessions': stats['total_sessions'],
                'total_hours': stats['total_hours'],
                'avg_productivity': stats['avg_productivity'],
                'completed_ratio': stats['completed_ratio'],
                'best_day': stats['best_day'],
                'best_theme': stats['best_theme']
            }),
            Json(stats.get('theme_breakdown', [])),
            Json({
                'what_worked': str(reflections.get('what_worked', ''))[:2000],
                'what_to_improve': str(reflections.get('what_to_improve', ''))[:2000],
                'lessons_learned': str(reflections.get('lessons_learned', ''))[:2000]
            }),
            Json(next_week_goals or []),
            Json(ml_insights or {}),
            now
        ))

    return True


def get_latest_weekly_review():
    """Get the most recent weekly review."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, week_start, week_number, year, stats, theme_breakdown,
                   reflections, next_week_goals, ml_insights, created_at
            FROM weekly_reviews
            ORDER BY week_start DESC
            LIMIT 1
        """)
        review = cur.fetchone()

    if review:
        review = dict(review)
        review['_id'] = str(review['id'])
        review['week_start'] = review['week_start'].isoformat() if isinstance(review['week_start'], date) else review['week_start']
        if review.get('created_at'):
            review['created_at'] = review['created_at'].isoformat()

    return review


def check_pending_weekly_reviews():
    """Check if there are any weeks that need a review.

    Returns:
        dict: {
            'has_pending': bool,
            'pending_weeks': [
                {
                    'week_start': 'YYYY-MM-DD',
                    'week_end': 'YYYY-MM-DD',
                    'week_number': int,
                    'is_current_week': bool
                }
            ],
            'last_review_week': 'YYYY-MM-DD' or None
        }
    """
    from datetime import date, timedelta

    today = date.today()
    current_week_start = today - timedelta(days=today.weekday())

    # Get latest review
    latest_review = get_latest_weekly_review()

    pending_weeks = []

    if not latest_review:
        # No reviews ever - don't force review for new users
        # Only trigger if there's actual session data
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM sessions WHERE completed = TRUE")
            session_count = cur.fetchone()['count']

        if session_count < 5:  # At least 5 sessions before requiring review
            return {'has_pending': False, 'pending_weeks': [], 'last_review_week': None}

        # Check if there are sessions from a completed week
        with get_cursor() as cur:
            cur.execute("""
                SELECT MIN(date) as first_date
                FROM sessions
                WHERE completed = TRUE
            """)
            first_session = cur.fetchone()

        if first_session and first_session['first_date']:
            first_date = first_session['first_date']
            if isinstance(first_date, str):
                first_date = datetime.strptime(first_date, '%Y-%m-%d').date()

            # If first session was before current week, there's a pending review
            if first_date < current_week_start:
                # Find the earliest week with sessions
                week_to_review = current_week_start - timedelta(days=7)
                pending_weeks.append({
                    'week_start': week_to_review.isoformat(),
                    'week_end': (week_to_review + timedelta(days=6)).isoformat(),
                    'week_number': week_to_review.isocalendar()[1],
                    'is_current_week': False
                })

    else:
        # Has previous reviews - check if any week is missing
        last_review_week = latest_review.get('week_start')
        if isinstance(last_review_week, str):
            last_review_week = datetime.strptime(last_review_week, '%Y-%m-%d').date()

        # Check if at least one full week has passed since last review
        week_after_last_review = last_review_week + timedelta(days=7)

        if week_after_last_review < current_week_start:
            # There's at least one week between last review and current week
            pending_weeks.append({
                'week_start': week_after_last_review.isoformat(),
                'week_end': (week_after_last_review + timedelta(days=6)).isoformat(),
                'week_number': week_after_last_review.isocalendar()[1],
                'is_current_week': False
            })

    return {
        'has_pending': len(pending_weeks) > 0,
        'pending_weeks': pending_weeks[:1],  # Only return the most recent pending week
        'last_review_week': latest_review.get('week_start') if latest_review else None
    }


# =============================================================================
# THEME ANALYTICS
# =============================================================================

def get_theme_analytics():
    """Get analytics for all themes/categories."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT category,
                   COUNT(*) as sessions,
                   SUM(duration_minutes) as total_minutes,
                   AVG(productivity_rating) FILTER (WHERE productivity_rating IS NOT NULL) as avg_rating
            FROM sessions
            WHERE completed = TRUE
            GROUP BY category
            ORDER BY sessions DESC
        """)
        results = [dict(row) for row in cur.fetchall()]

    analytics = []
    for row in results:
        avg_rating = normalize_rating(row['avg_rating']) if row['avg_rating'] else 0
        analytics.append({
            'theme': row['category'],
            'sessions': row['sessions'],
            'total_minutes': row['total_minutes'] or 0,
            'total_hours': round((row['total_minutes'] or 0) / 60, 1),
            'avg_productivity': round(avg_rating, 1)
        })

    return analytics


# =============================================================================
# GAMIFICATION - USER PROFILE
# =============================================================================

def get_user_profile():
    """Get user profile with gamification data."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, user_id, xp, total_xp_earned, level, title,
                   streak_freezes_available, streak_freeze_used_dates,
                   vacation_mode, vacation_days_remaining, vacation_start_date,
                   created_at, updated_at
            FROM user_profile
            WHERE user_id = 'default'
        """)
        profile = cur.fetchone()

    if profile:
        profile = dict(profile)
        profile['_id'] = str(profile['id'])

        # Vypočítat level prahy pro progress bar
        total_xp = profile.get('total_xp_earned') or profile.get('xp') or 0
        level = profile.get('level') or 1

        # XP prahy: level N vyžaduje ((N-1)^2 * 100) XP, level N+1 vyžaduje (N^2 * 100) XP
        profile['current_level_xp'] = ((level - 1) ** 2) * 100
        profile['next_level_xp'] = (level ** 2) * 100
        profile['xp_to_next_level'] = max(0, profile['next_level_xp'] - total_xp)

        # Zajistit že total_xp_earned má hodnotu pro zobrazení
        if profile.get('total_xp_earned') is None:
            profile['total_xp_earned'] = profile.get('xp') or 0

    return profile


def add_xp(amount, source='session'):
    """Add XP to user profile."""
    with get_cursor() as cur:
        # Get current XP
        cur.execute("""
            SELECT xp, total_xp_earned, level
            FROM user_profile
            WHERE user_id = 'default'
        """)
        profile = cur.fetchone()

        if not profile:
            # Create profile if not exists
            cur.execute("""
                INSERT INTO user_profile (user_id, xp, total_xp_earned, level)
                VALUES ('default', %s, %s, 1)
                RETURNING xp, level
            """, (amount, amount))
            profile = cur.fetchone()
            old_xp = 0
        else:
            old_xp = profile['xp']

        new_xp = old_xp + amount

        # Bezpečné zpracování NULL - fallback na xp pole pokud total_xp_earned je NULL
        current_total = profile.get('total_xp_earned')
        if current_total is None:
            current_total = profile.get('xp', 0) or 0
        total_xp = current_total + amount

        # Calculate new level (simple formula: level = sqrt(total_xp / 100) + 1)
        import math
        new_level = int(math.sqrt(total_xp / 100)) + 1

        # Update profile
        cur.execute("""
            UPDATE user_profile
            SET xp = %s, total_xp_earned = %s, level = %s, updated_at = %s
            WHERE user_id = 'default'
        """, (new_xp, total_xp, new_level, datetime.now()))

        # Log XP history
        cur.execute("""
            INSERT INTO xp_history (amount, source, old_xp, new_xp, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (amount, source, old_xp, new_xp, datetime.now()))

    return {'old_xp': old_xp, 'new_xp': new_xp, 'amount': amount, 'level': new_level}


def calculate_level_from_xp(xp: int) -> dict:
    """Calculate level and progress from XP."""
    import math
    level = int(math.sqrt(xp / 100)) + 1
    xp_for_current_level = ((level - 1) ** 2) * 100
    xp_for_next_level = (level ** 2) * 100
    xp_in_level = xp - xp_for_current_level
    xp_needed = xp_for_next_level - xp_for_current_level
    progress = (xp_in_level / xp_needed * 100) if xp_needed > 0 else 100

    return {
        'level': level,
        'xp': xp,
        'xp_in_level': xp_in_level,
        'xp_for_next_level': xp_needed,
        'progress': round(progress, 1)
    }


def fix_user_profile_data():
    """Oprava nekonzistentních XP/level dat.

    Použije se při startu aplikace k opravě případných nekonzistencí:
    - Pokud total_xp_earned je NULL, nastaví se na hodnotu xp
    - Přepočítá level podle vzorce sqrt(total_xp/100) + 1
    """
    import math
    with get_cursor() as cur:
        # Nejdřív získáme aktuální data
        cur.execute("""
            SELECT xp, total_xp_earned, level
            FROM user_profile
            WHERE user_id = 'default'
        """)
        profile = cur.fetchone()

        if profile:
            # Určíme správnou hodnotu total_xp - použijeme větší z obou hodnot
            xp_field = profile['xp'] or 0
            total_field = profile['total_xp_earned'] or 0
            total_xp = max(xp_field, total_field)

            # Vypočítáme správný level
            correct_level = int(math.sqrt(total_xp / 100)) + 1

            # Aktualizujeme data pokud je potřeba
            cur.execute("""
                UPDATE user_profile
                SET
                    total_xp_earned = %s,
                    level = %s,
                    updated_at = %s
                WHERE user_id = 'default'
            """, (total_xp, correct_level, datetime.now()))

            return {
                'fixed': True,
                'total_xp': total_xp,
                'new_level': correct_level,
                'old_level': profile['level']
            }

    return {'fixed': False, 'reason': 'No profile found'}


# =============================================================================
# STREAK PROTECTION
# =============================================================================

def use_streak_freeze() -> dict:
    """Use a streak freeze to prevent streak loss."""
    today = date.today()

    with get_cursor() as cur:
        # Get current profile
        cur.execute("""
            SELECT streak_freezes_available, streak_freeze_used_dates
            FROM user_profile WHERE user_id = 'default'
        """)
        profile = cur.fetchone()

        if not profile:
            return {'success': False, 'error': 'No profile found'}

        freezes_available = profile.get('streak_freezes_available', 0) or 0
        used_dates = profile.get('streak_freeze_used_dates', []) or []

        # Check if already used today
        today_str = today.isoformat()
        if today_str in used_dates:
            return {'success': False, 'error': 'Already used today', 'freezes_left': freezes_available}

        if freezes_available <= 0:
            return {'success': False, 'error': 'No freezes available', 'freezes_left': 0}

        # Use freeze
        used_dates.append(today_str)
        new_freezes = freezes_available - 1

        cur.execute("""
            UPDATE user_profile
            SET streak_freezes_available = %s, streak_freeze_used_dates = %s, updated_at = %s
            WHERE user_id = 'default'
        """, (new_freezes, Json(used_dates), datetime.now()))

    return {'success': True, 'freezes_left': new_freezes, 'used_on': today_str}


def toggle_vacation_mode(enable: bool, days: int = 7) -> dict:
    """Enable or disable vacation mode."""
    today = date.today()

    with get_cursor() as cur:
        if enable:
            cur.execute("""
                UPDATE user_profile
                SET vacation_mode = TRUE, vacation_start_date = %s,
                    vacation_days_remaining = %s, updated_at = %s
                WHERE user_id = 'default'
            """, (today, days, datetime.now()))
            return {'success': True, 'vacation_mode': True, 'days': days, 'start_date': today.isoformat()}
        else:
            cur.execute("""
                UPDATE user_profile
                SET vacation_mode = FALSE, vacation_start_date = NULL,
                    vacation_days_remaining = 0, updated_at = %s
                WHERE user_id = 'default'
            """, (datetime.now(),))
            return {'success': True, 'vacation_mode': False}


def check_streak_with_protection() -> dict:
    """Check streak status with freeze/vacation protection."""
    today = date.today()
    yesterday = today - timedelta(days=1)

    with get_cursor() as cur:
        # Get profile
        cur.execute("""
            SELECT vacation_mode, vacation_start_date, vacation_days_remaining,
                   streak_freezes_available, streak_freeze_used_dates
            FROM user_profile WHERE user_id = 'default'
        """)
        profile = cur.fetchone()

        # Get last session date
        cur.execute("""
            SELECT MAX(date) as last_date
            FROM sessions WHERE completed = TRUE
        """)
        result = cur.fetchone()
        last_session_date = result['last_date'] if result else None

    if not profile:
        return {'streak_protected': False, 'reason': 'no_profile'}

    # Check vacation mode
    if profile.get('vacation_mode'):
        start_date = profile.get('vacation_start_date')
        days_remaining = profile.get('vacation_days_remaining', 0)
        if start_date:
            days_elapsed = (today - start_date).days
            if days_elapsed <= days_remaining:
                return {
                    'streak_protected': True,
                    'protection_type': 'vacation',
                    'days_remaining': days_remaining - days_elapsed
                }

    # Check freeze usage
    used_dates = profile.get('streak_freeze_used_dates', []) or []
    yesterday_str = yesterday.isoformat()
    if yesterday_str in used_dates:
        return {
            'streak_protected': True,
            'protection_type': 'freeze',
            'used_on': yesterday_str
        }

    # Check if session exists yesterday or today
    if last_session_date:
        if isinstance(last_session_date, str):
            last_session_date = datetime.strptime(last_session_date, '%Y-%m-%d').date()
        if last_session_date >= yesterday:
            return {'streak_protected': True, 'protection_type': 'session'}

    return {
        'streak_protected': False,
        'freezes_available': profile.get('streak_freezes_available', 0)
    }


# =============================================================================
# GAMIFICATION - ACHIEVEMENTS
# =============================================================================

# Achievement definitions
ACHIEVEMENTS_DEFINITIONS = {
    'first_session': {'name': 'First Step', 'description': 'Complete your first session', 'target': 1, 'xp': 50, 'icon': '🎯'},
    'sessions_10': {'name': 'Getting Started', 'description': 'Complete 10 sessions', 'target': 10, 'xp': 100, 'icon': '📈'},
    'sessions_50': {'name': 'Dedicated', 'description': 'Complete 50 sessions', 'target': 50, 'xp': 250, 'icon': '🔥'},
    'sessions_100': {'name': 'Centurion', 'description': 'Complete 100 sessions', 'target': 100, 'xp': 500, 'icon': '💯'},
    'sessions_500': {'name': 'Master', 'description': 'Complete 500 sessions', 'target': 500, 'xp': 1000, 'icon': '👑'},
    'streak_3': {'name': 'Consistency', 'description': '3 day streak', 'target': 3, 'xp': 75, 'icon': '🔗'},
    'streak_7': {'name': 'Week Warrior', 'description': '7 day streak', 'target': 7, 'xp': 150, 'icon': '📅'},
    'streak_30': {'name': 'Monthly Master', 'description': '30 day streak', 'target': 30, 'xp': 500, 'icon': '🏆'},
    'deep_work_10': {'name': 'Deep Diver', 'description': '10 Deep Work sessions', 'target': 10, 'xp': 150, 'icon': '🧠'},
    'early_bird': {'name': 'Early Bird', 'description': 'Session before 7 AM', 'target': 1, 'xp': 100, 'icon': '🌅'},
    'night_owl': {'name': 'Night Owl', 'description': 'Session after 10 PM', 'target': 1, 'xp': 100, 'icon': '🦉'},
    'perfect_day': {'name': 'Perfect Day', 'description': '5 sessions with 80%+ rating', 'target': 5, 'xp': 200, 'icon': '⭐'},
    'category_master': {'name': 'Specialist', 'description': '50 sessions in one category', 'target': 50, 'xp': 300, 'icon': '🎓'},
    'variety': {'name': 'Renaissance', 'description': 'Use 5 different categories', 'target': 5, 'xp': 100, 'icon': '🌈'},
    'hours_10': {'name': 'Time Investor', 'description': 'Log 10 hours total', 'target': 600, 'xp': 150, 'icon': '⏰'},
    'hours_100': {'name': 'Time Lord', 'description': 'Log 100 hours total', 'target': 6000, 'xp': 750, 'icon': '⌛'},
}


def init_achievements():
    """Initialize achievements from definitions."""
    with get_cursor() as cur:
        for achievement_id, definition in ACHIEVEMENTS_DEFINITIONS.items():
            cur.execute("""
                INSERT INTO achievements (achievement_id, progress, unlocked, created_at)
                VALUES (%s, 0, FALSE, %s)
                ON CONFLICT (achievement_id) DO NOTHING
            """, (achievement_id, datetime.now()))


def check_and_unlock_achievements():
    """Check and unlock achievements based on current stats."""
    unlocked = []

    with get_cursor() as cur:
        # Get total sessions
        cur.execute("SELECT COUNT(*) as count FROM sessions WHERE completed = TRUE")
        total_sessions = cur.fetchone()['count']

        # Get streak
        streak_stats = get_streak_stats()
        current_streak = streak_stats.get('current_streak', 0)
        longest_streak = streak_stats.get('longest_streak', 0)

        # Get deep work sessions
        cur.execute("SELECT COUNT(*) as count FROM sessions WHERE completed = TRUE AND preset = 'deep_work'")
        deep_work_sessions = cur.fetchone()['count']

        # Get early/late sessions
        cur.execute("SELECT COUNT(*) as count FROM sessions WHERE completed = TRUE AND hour < 7")
        early_sessions = cur.fetchone()['count']
        cur.execute("SELECT COUNT(*) as count FROM sessions WHERE completed = TRUE AND hour >= 22")
        late_sessions = cur.fetchone()['count']

        # Get total hours
        cur.execute("SELECT COALESCE(SUM(duration_minutes), 0) as total FROM sessions WHERE completed = TRUE")
        total_minutes = cur.fetchone()['total']

        # Get category count
        cur.execute("SELECT COUNT(DISTINCT category) as count FROM sessions WHERE completed = TRUE")
        category_count = cur.fetchone()['count']

        # Get max category sessions
        cur.execute("""
            SELECT category, COUNT(*) as count FROM sessions
            WHERE completed = TRUE
            GROUP BY category ORDER BY count DESC LIMIT 1
        """)
        max_cat = cur.fetchone()
        max_category_sessions = max_cat['count'] if max_cat else 0

        # Check each achievement
        checks = {
            'first_session': total_sessions >= 1,
            'sessions_10': total_sessions >= 10,
            'sessions_50': total_sessions >= 50,
            'sessions_100': total_sessions >= 100,
            'sessions_500': total_sessions >= 500,
            'streak_3': longest_streak >= 3,
            'streak_7': longest_streak >= 7,
            'streak_30': longest_streak >= 30,
            'deep_work_10': deep_work_sessions >= 10,
            'early_bird': early_sessions >= 1,
            'night_owl': late_sessions >= 1,
            'category_master': max_category_sessions >= 50,
            'variety': category_count >= 5,
            'hours_10': total_minutes >= 600,
            'hours_100': total_minutes >= 6000,
        }

        progress_values = {
            'first_session': min(total_sessions, 1),
            'sessions_10': min(total_sessions, 10),
            'sessions_50': min(total_sessions, 50),
            'sessions_100': min(total_sessions, 100),
            'sessions_500': min(total_sessions, 500),
            'streak_3': min(longest_streak, 3),
            'streak_7': min(longest_streak, 7),
            'streak_30': min(longest_streak, 30),
            'deep_work_10': min(deep_work_sessions, 10),
            'early_bird': min(early_sessions, 1),
            'night_owl': min(late_sessions, 1),
            'category_master': min(max_category_sessions, 50),
            'variety': min(category_count, 5),
            'hours_10': min(total_minutes, 600),
            'hours_100': min(total_minutes, 6000),
        }

        now = datetime.now()
        for achievement_id, should_unlock in checks.items():
            progress = progress_values.get(achievement_id, 0)
            target = ACHIEVEMENTS_DEFINITIONS.get(achievement_id, {}).get('target', 1)
            progress_pct = min(100, int(progress / target * 100)) if target > 0 else 0

            # Check if already unlocked
            cur.execute("SELECT unlocked FROM achievements WHERE achievement_id = %s", (achievement_id,))
            row = cur.fetchone()
            was_unlocked = row['unlocked'] if row else False

            cur.execute("""
                INSERT INTO achievements (achievement_id, progress, unlocked, unlocked_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (achievement_id) DO UPDATE SET
                    progress = GREATEST(achievements.progress, EXCLUDED.progress),
                    unlocked = achievements.unlocked OR EXCLUDED.unlocked,
                    unlocked_at = CASE WHEN EXCLUDED.unlocked AND NOT achievements.unlocked
                                  THEN EXCLUDED.unlocked_at ELSE achievements.unlocked_at END,
                    updated_at = EXCLUDED.updated_at
            """, (achievement_id, progress_pct, should_unlock, now if should_unlock else None, now, now))

            if should_unlock and not was_unlocked:
                definition = ACHIEVEMENTS_DEFINITIONS.get(achievement_id, {})
                unlocked.append({
                    'id': achievement_id,
                    'name': definition.get('name', achievement_id),
                    'description': definition.get('description', ''),
                    'xp': definition.get('xp', 0),
                    'icon': definition.get('icon', '🏆')
                })

    return unlocked


def get_all_achievements():
    """Get all achievements with progress, merged with definitions."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, achievement_id, progress, unlocked, unlocked_at, notified
            FROM achievements
            ORDER BY unlocked DESC, progress DESC
        """)
        achievements = [dict(row) for row in cur.fetchall()]

    for a in achievements:
        a['_id'] = str(a['id'])
        if a.get('unlocked_at'):
            a['unlocked_at'] = a['unlocked_at'].isoformat()

        # Merge definition data
        definition = ACHIEVEMENTS_DEFINITIONS.get(a['achievement_id'], {})
        a['name'] = definition.get('name', a['achievement_id'])
        a['description'] = definition.get('description', '')
        a['icon'] = definition.get('icon', '🏆')
        a['target'] = definition.get('target', 1)
        a['points'] = definition.get('xp', 0)

        # Calculate percentage
        target = a['target']
        a['percentage'] = min(100, round((a['progress'] / target) * 100)) if target > 0 else 0

        # Calculate rarity from XP
        a['rarity'] = _get_rarity_from_xp(a['points'])

        # Default category (could be enhanced later)
        a['category'] = 'general'

    return achievements


def update_achievement_progress(achievement_id, progress, unlocked=False):
    """Update achievement progress."""
    now = datetime.now()

    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO achievements (achievement_id, progress, unlocked, unlocked_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (achievement_id) DO UPDATE SET
                progress = GREATEST(achievements.progress, EXCLUDED.progress),
                unlocked = achievements.unlocked OR EXCLUDED.unlocked,
                unlocked_at = CASE WHEN EXCLUDED.unlocked AND NOT achievements.unlocked
                              THEN EXCLUDED.unlocked_at ELSE achievements.unlocked_at END,
                updated_at = EXCLUDED.updated_at
        """, (achievement_id, progress, unlocked, now if unlocked else None, now, now))


def _get_rarity_from_xp(xp):
    """Determine achievement rarity based on XP value."""
    if xp <= 100:
        return 'common'
    elif xp <= 200:
        return 'rare'
    elif xp <= 500:
        return 'epic'
    else:
        return 'legendary'


def get_achievements_summary():
    """Get achievements summary including percentage, points, and rarity breakdown."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE unlocked) as unlocked,
                COALESCE(AVG(progress) FILTER (WHERE NOT unlocked), 0) as avg_progress
            FROM achievements
        """)
        result = cur.fetchone()

        # Get unlocked achievement IDs to calculate points
        cur.execute("SELECT achievement_id FROM achievements WHERE unlocked = TRUE")
        unlocked_ids = [row['achievement_id'] for row in cur.fetchall()]

    total = result['total']
    unlocked = result['unlocked']

    # Calculate percentage
    percentage = (unlocked / total * 100) if total > 0 else 0

    # Calculate points from unlocked achievements
    points = sum(
        ACHIEVEMENTS_DEFINITIONS.get(aid, {}).get('xp', 0)
        for aid in unlocked_ids
    )

    # Calculate rarity breakdown
    by_rarity = {
        'common': {'total': 0, 'unlocked': 0},
        'rare': {'total': 0, 'unlocked': 0},
        'epic': {'total': 0, 'unlocked': 0},
        'legendary': {'total': 0, 'unlocked': 0}
    }

    for aid, definition in ACHIEVEMENTS_DEFINITIONS.items():
        rarity = _get_rarity_from_xp(definition.get('xp', 0))
        by_rarity[rarity]['total'] += 1
        if aid in unlocked_ids:
            by_rarity[rarity]['unlocked'] += 1

    return {
        'total': total,
        'unlocked': unlocked,
        'avg_progress': round(result['avg_progress'] or 0, 1),
        'percentage': round(percentage, 1),
        'points': points,
        'by_rarity': by_rarity
    }


# =============================================================================
# GAMIFICATION - CATEGORY SKILLS
# =============================================================================

def update_category_skill(category, minutes):
    """Update category skill XP."""
    xp_per_minute = 1

    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO category_skills (category, xp, level, sessions_count, total_minutes)
            VALUES (%s, %s, 1, 1, %s)
            ON CONFLICT (category) DO UPDATE SET
                xp = category_skills.xp + %s,
                sessions_count = category_skills.sessions_count + 1,
                total_minutes = category_skills.total_minutes + %s,
                level = GREATEST(1, (category_skills.xp + %s) / 1000 + 1),
                updated_at = NOW()
        """, (category, minutes * xp_per_minute, minutes,
              minutes * xp_per_minute, minutes, minutes * xp_per_minute))


def get_category_skills():
    """Get all category skills."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT category, xp, level, sessions_count, total_minutes
            FROM category_skills
            ORDER BY xp DESC
        """)
        skills = [dict(row) for row in cur.fetchall()]

    return skills


# =============================================================================
# GAMIFICATION - DAILY CHALLENGES
# =============================================================================

def get_or_create_daily_challenge(target_date=None):
    """Get or create daily challenge."""
    if target_date is None:
        target_date = date.today()
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, date, challenge_id, title, description, target,
                   condition_type, difficulty, xp_reward, progress,
                   completed, completed_at, ai_generated, extra_conditions
            FROM daily_challenges
            WHERE date = %s
        """, (target_date,))
        challenge = cur.fetchone()

        if challenge:
            challenge = dict(challenge)
            challenge['_id'] = str(challenge['id'])
            challenge['date'] = challenge['date'].isoformat() if isinstance(challenge['date'], date) else challenge['date']
            if challenge.get('completed_at'):
                challenge['completed_at'] = challenge['completed_at'].isoformat()
            return challenge

        # Create new random challenge
        import random
        challenges = [
            {'id': 'complete_3', 'title': 'Complete 3 sessions', 'target': 3, 'type': 'sessions', 'xp': 50},
            {'id': 'deep_work_2', 'title': '2 Deep Work sessions', 'target': 2, 'type': 'preset_deep_work', 'xp': 75},
            {'id': 'high_rating', 'title': 'Rate 80%+ on 2 sessions', 'target': 2, 'type': 'high_rating', 'xp': 60},
            {'id': 'morning_start', 'title': 'Start before 9 AM', 'target': 1, 'type': 'morning_session', 'xp': 40},
            {'id': 'variety', 'title': '3 different categories', 'target': 3, 'type': 'categories', 'xp': 65},
        ]
        selected = random.choice(challenges)

        cur.execute("""
            INSERT INTO daily_challenges
            (date, challenge_id, title, description, target, condition_type,
             difficulty, xp_reward, progress, completed, ai_generated, extra_conditions)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, FALSE, FALSE, %s)
            RETURNING id
        """, (
            target_date, selected['id'], selected['title'], '',
            selected['target'], selected['type'], 'medium', selected['xp'], Json({})
        ))

        challenge = {
            'date': target_date.isoformat(),
            'challenge_id': selected['id'],
            'title': selected['title'],
            'target': selected['target'],
            'condition_type': selected['type'],
            'xp_reward': selected['xp'],
            'progress': 0,
            'completed': False
        }

    return challenge


def update_daily_challenge_progress():
    """Update daily challenge progress based on today's sessions."""
    today = date.today()

    with get_cursor() as cur:
        # Get today's challenge
        cur.execute("""
            SELECT id, challenge_id, condition_type, target, progress, completed
            FROM daily_challenges
            WHERE date = %s
        """, (today,))
        challenge = cur.fetchone()

        if not challenge or challenge['completed']:
            return

        # Calculate progress based on condition type
        condition = challenge['condition_type']
        progress = 0

        if condition == 'sessions':
            cur.execute("SELECT COUNT(*) as count FROM sessions WHERE date = %s AND completed = TRUE", (today,))
            progress = cur.fetchone()['count']
        elif condition == 'preset_deep_work':
            cur.execute("SELECT COUNT(*) as count FROM sessions WHERE date = %s AND completed = TRUE AND preset = 'deep_work'", (today,))
            progress = cur.fetchone()['count']
        elif condition == 'high_rating':
            cur.execute("SELECT COUNT(*) as count FROM sessions WHERE date = %s AND completed = TRUE AND productivity_rating >= 80", (today,))
            progress = cur.fetchone()['count']
        elif condition == 'morning_session':
            cur.execute("SELECT COUNT(*) as count FROM sessions WHERE date = %s AND completed = TRUE AND hour < 9", (today,))
            progress = 1 if cur.fetchone()['count'] > 0 else 0
        elif condition == 'categories':
            cur.execute("SELECT COUNT(DISTINCT category) as count FROM sessions WHERE date = %s AND completed = TRUE", (today,))
            progress = cur.fetchone()['count']

        completed = progress >= challenge['target']

        cur.execute("""
            UPDATE daily_challenges
            SET progress = %s, completed = %s, completed_at = %s, updated_at = %s
            WHERE id = %s
        """, (progress, completed, datetime.now() if completed else None, datetime.now(), challenge['id']))


# =============================================================================
# GAMIFICATION - WEEKLY QUESTS
# =============================================================================

def get_or_create_weekly_quests(week_start=None):
    """Get or create weekly quests."""
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    elif isinstance(week_start, str):
        week_start = datetime.strptime(week_start, '%Y-%m-%d').date()

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, week_start, quests, ai_generated
            FROM weekly_quests
            WHERE week_start = %s
        """, (week_start,))
        result = cur.fetchone()

        if result:
            result = dict(result)
            result['_id'] = str(result['id'])
            result['week_start'] = result['week_start'].isoformat() if isinstance(result['week_start'], date) else result['week_start']
            return result

        # Create default quests
        quests = [
            {'id': 'weekly_20', 'title': 'Complete 20 sessions', 'target': 20, 'progress': 0, 'completed': False, 'xp': 200},
            {'id': 'weekly_streak', 'title': 'Work 5 days in a row', 'target': 5, 'progress': 0, 'completed': False, 'xp': 150},
            {'id': 'weekly_hours', 'title': 'Log 15 hours', 'target': 900, 'progress': 0, 'completed': False, 'xp': 175},
        ]

        cur.execute("""
            INSERT INTO weekly_quests (week_start, quests, ai_generated)
            VALUES (%s, %s, FALSE)
            RETURNING id
        """, (week_start, Json(quests)))

    return {'week_start': week_start.isoformat(), 'quests': quests}


def update_weekly_quest_progress(quest_id=None):
    """Update weekly quest progress."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, quests
            FROM weekly_quests
            WHERE week_start = %s
        """, (week_start,))
        result = cur.fetchone()

        if not result:
            return

        quests = result['quests']

        # Get stats for the week
        cur.execute("""
            SELECT
                COUNT(*) as sessions,
                COALESCE(SUM(duration_minutes), 0) as minutes,
                COUNT(DISTINCT date) as days
            FROM sessions
            WHERE date >= %s AND date <= %s AND completed = TRUE
        """, (week_start, week_end))
        stats = cur.fetchone()

        # Update each quest
        for quest in quests:
            if quest.get('completed'):
                continue

            if quest['id'] == 'weekly_20':
                quest['progress'] = stats['sessions']
            elif quest['id'] == 'weekly_streak':
                quest['progress'] = stats['days']
            elif quest['id'] == 'weekly_hours':
                quest['progress'] = stats['minutes']

            quest['completed'] = quest['progress'] >= quest['target']

        cur.execute("""
            UPDATE weekly_quests
            SET quests = %s, updated_at = %s
            WHERE id = %s
        """, (Json(quests), datetime.now(), result['id']))


# =============================================================================
# AI CACHE
# =============================================================================

def get_cached_ai_recommendation(rec_type: str) -> Optional[dict]:
    """Get cached AI recommendation if not expired."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT response, expires_at
            FROM ai_cache
            WHERE cache_type = %s AND expires_at > NOW() AND NOT invalidated
            ORDER BY created_at DESC
            LIMIT 1
        """, (rec_type,))
        result = cur.fetchone()

    if result:
        return result['response']
    return None


def cache_ai_recommendation(rec_type: str, response: dict, ttl_hours: float = 4):
    """Cache AI recommendation."""
    import hashlib
    cache_key = f"{rec_type}_{hashlib.md5(str(response).encode()).hexdigest()[:8]}"
    expires_at = datetime.now() + timedelta(hours=ttl_hours)

    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO ai_cache (cache_key, cache_type, response, ttl_hours, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (cache_key) DO UPDATE SET
                response = EXCLUDED.response,
                expires_at = EXCLUDED.expires_at,
                invalidated = FALSE
        """, (cache_key, rec_type, Json(response), ttl_hours, expires_at))


def invalidate_ai_cache(rec_type: str = None):
    """Invalidate AI cache."""
    with get_cursor() as cur:
        if rec_type:
            cur.execute("UPDATE ai_cache SET invalidated = TRUE WHERE cache_type = %s", (rec_type,))
        else:
            cur.execute("UPDATE ai_cache SET invalidated = TRUE")


# =============================================================================
# UTILITY FUNCTIONS FOR ML
# =============================================================================

def get_recent_tasks(limit: int = 100) -> list:
    """Get recent tasks for autocomplete."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT task
            FROM sessions
            WHERE task IS NOT NULL AND task != ''
            ORDER BY MAX(created_at) DESC
            LIMIT %s
        """, (limit,))
        return [row['task'] for row in cur.fetchall()]


def get_category_distribution() -> dict:
    """Get category distribution."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT category, COUNT(*) as count
            FROM sessions
            WHERE completed = TRUE
            GROUP BY category
            ORDER BY count DESC
        """)
        return {row['category']: row['count'] for row in cur.fetchall()}


def get_hourly_productivity() -> dict:
    """Get productivity by hour."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT hour,
                   COUNT(*) as sessions,
                   AVG(productivity_rating) FILTER (WHERE productivity_rating IS NOT NULL) as avg_rating
            FROM sessions
            WHERE completed = TRUE
            GROUP BY hour
            ORDER BY hour
        """)
        result = {}
        for row in cur.fetchall():
            result[row['hour']] = {
                'sessions': row['sessions'],
                'avg_rating': round(normalize_rating(row['avg_rating']) if row['avg_rating'] else 0, 1)
            }
        return result


def get_sessions_last_n_days(days: int = 30) -> list:
    """Get sessions from last N days."""
    start_date = date.today() - timedelta(days=days)

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, date, time, preset, category, task, duration_minutes,
                   completed, productivity_rating, notes, hour, day_of_week
            FROM sessions
            WHERE date >= %s AND completed = TRUE
            ORDER BY date DESC, time DESC
        """, (start_date,))
        sessions = [dict(row) for row in cur.fetchall()]

    for s in sessions:
        s['_id'] = str(s['id'])
        if s.get('date'):
            s['date'] = s['date'].isoformat() if isinstance(s['date'], date) else s['date']
        if s.get('time'):
            s['time'] = str(s['time'])

    return sessions


def get_near_completion_achievements(threshold: float = 50.0) -> list:
    """Get achievements near completion."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT achievement_id, progress
            FROM achievements
            WHERE NOT unlocked AND progress >= %s
            ORDER BY progress DESC
        """, (threshold,))
        return [dict(row) for row in cur.fetchall()]


def get_user_analytics_for_ai() -> dict:
    """Get comprehensive user analytics for AI."""
    stats = get_weekly_stats()
    streak = get_streak_stats()
    profile = get_user_profile()

    return {
        'weekly_stats': stats,
        'streak': streak,
        'profile': profile,
        'category_distribution': get_category_distribution(),
        'hourly_productivity': get_hourly_productivity()
    }


def get_last_session_context() -> dict:
    """Get context from last session."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, date, time, preset, category, task, duration_minutes,
                   productivity_rating, notes
            FROM sessions
            WHERE completed = TRUE
            ORDER BY created_at DESC
            LIMIT 1
        """)
        session = cur.fetchone()

    if session:
        session = dict(session)
        session['_id'] = str(session['id'])
        if session.get('date'):
            session['date'] = session['date'].isoformat() if isinstance(session['date'], date) else session['date']
        if session.get('time'):
            session['time'] = str(session['time'])

    return session or {}


# =============================================================================
# SEMANTIC SEARCH (pgvector)
# =============================================================================

def semantic_search_sessions(query_embedding: list, limit: int = 10,
                             min_similarity: float = 0.4, days_back: int = 30) -> list:
    """Search sessions by semantic similarity."""
    start_date = date.today() - timedelta(days=days_back)

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, date, category, task, notes, productivity_rating,
                   1 - (notes_embedding <=> %s::vector) as similarity
            FROM sessions
            WHERE notes_embedding IS NOT NULL
              AND date >= %s
              AND completed = TRUE
              AND 1 - (notes_embedding <=> %s::vector) >= %s
            ORDER BY notes_embedding <=> %s::vector
            LIMIT %s
        """, (query_embedding, start_date, query_embedding, min_similarity, query_embedding, limit))

        results = []
        for row in cur.fetchall():
            result = dict(row)
            result['id'] = str(result['id'])
            if result.get('date'):
                result['date'] = result['date'].isoformat() if isinstance(result['date'], date) else result['date']
            results.append(result)

        return results


def get_sessions_with_notes(days: int = 30) -> list:
    """Get sessions with notes for RAG context."""
    start_date = date.today() - timedelta(days=days)

    with get_cursor() as cur:
        cur.execute("""
            SELECT id, date, time, preset, category, task, duration_minutes,
                   productivity_rating, notes, hour
            FROM sessions
            WHERE date >= %s AND completed = TRUE AND notes IS NOT NULL AND notes != ''
            ORDER BY date DESC, time DESC
        """, (start_date,))
        sessions = [dict(row) for row in cur.fetchall()]

    for s in sessions:
        s['_id'] = str(s['id'])
        if s.get('date'):
            s['date'] = s['date'].isoformat() if isinstance(s['date'], date) else s['date']
        if s.get('time'):
            s['time'] = str(s['time'])

    return sessions


def rename_category_in_sessions(old_name: str, new_name: str) -> int:
    """Update all sessions with old category name to new name.

    Also updates related tables (category_skills, daily_focus).

    Args:
        old_name: Current category name
        new_name: New category name

    Returns:
        Number of sessions updated
    """
    total_updated = 0

    with get_cursor() as cur:
        # Update sessions table
        cur.execute("""
            UPDATE sessions
            SET category = %s, updated_at = NOW()
            WHERE category = %s
        """, (new_name, old_name))
        total_updated = cur.rowcount

        # Update category_skills table
        cur.execute("""
            UPDATE category_skills
            SET category = %s, updated_at = NOW()
            WHERE category = %s
        """, (new_name, old_name))

        # Update daily_focus themes (JSONB array)
        # This updates any theme entries that match old_name
        cur.execute("""
            UPDATE daily_focus
            SET themes = (
                SELECT COALESCE(
                    jsonb_agg(
                        CASE
                            WHEN elem->>'theme' = %s
                            THEN jsonb_set(elem, '{theme}', to_jsonb(%s::text))
                            ELSE elem
                        END
                    ),
                    '[]'::jsonb
                )
                FROM jsonb_array_elements(COALESCE(themes, '[]'::jsonb)) AS elem
            ),
            updated_at = NOW()
            WHERE themes::text LIKE %s
        """, (old_name, new_name, f'%"{old_name}"%'))

        logger.info(f"Renamed category '{old_name}' to '{new_name}': {total_updated} sessions updated")

    return total_updated
