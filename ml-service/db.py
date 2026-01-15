"""
PostgreSQL database module for ML Service.
Provides connection pooling and query helpers.
"""

import os
import json
import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Connection pool (initialized lazily)
_pool: Optional[ThreadedConnectionPool] = None


def get_pool() -> ThreadedConnectionPool:
    """Get or create connection pool."""
    global _pool
    if _pool is None:
        database_url = os.getenv('DATABASE_URL', 'postgresql://pomodoro:pomodoro_secret@localhost:5432/pomodoro')
        _pool = ThreadedConnectionPool(2, 10, database_url)
        logger.info("PostgreSQL connection pool created")
    return _pool


@contextmanager
def get_cursor():
    """Context manager for database cursor."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        pool.putconn(conn)


def init_db() -> bool:
    """Test database connection."""
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
        logger.info("PostgreSQL connection successful")
        return True
    except Exception as e:
        logger.error(f"PostgreSQL connection failed: {e}")
        return False


def close_pool():
    """Close connection pool."""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("PostgreSQL connection pool closed")


# =============================================================================
# SESSION QUERIES
# =============================================================================

def get_sessions(completed_only: bool = True) -> List[Dict]:
    """Get all sessions."""
    try:
        with get_cursor() as cur:
            if completed_only:
                cur.execute("""
                    SELECT id, preset, category, task, duration_minutes, completed,
                           productivity_rating, notes, date, time, hour, day_of_week, created_at
                    FROM sessions
                    WHERE completed = TRUE
                    ORDER BY date DESC, time DESC
                """)
            else:
                cur.execute("""
                    SELECT id, preset, category, task, duration_minutes, completed,
                           productivity_rating, notes, date, time, hour, day_of_week, created_at
                    FROM sessions
                    ORDER BY date DESC, time DESC
                """)

            results = cur.fetchall()
            return [_format_session(dict(row)) for row in results]
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        return []


def get_sessions_with_notes(days: int = 30) -> List[Dict]:
    """Get sessions with notes from specified period."""
    try:
        cutoff = datetime.now() - timedelta(days=days)
        with get_cursor() as cur:
            cur.execute("""
                SELECT id, preset, category, task, duration_minutes, completed,
                       productivity_rating, notes, date, time, hour, day_of_week, created_at
                FROM sessions
                WHERE completed = TRUE
                  AND created_at >= %s
                ORDER BY created_at DESC
            """, (cutoff,))

            results = cur.fetchall()
            return [_format_session(dict(row)) for row in results]
    except Exception as e:
        logger.error(f"Error fetching sessions with notes: {e}")
        return []


def get_today_sessions() -> List[Dict]:
    """Get today's completed sessions."""
    today = datetime.now().strftime('%Y-%m-%d')
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT id, preset, category, task, duration_minutes, completed,
                       productivity_rating, notes, date, time, hour, day_of_week, created_at
                FROM sessions
                WHERE date = %s AND completed = TRUE
                ORDER BY time ASC
            """, (today,))

            results = cur.fetchall()
            return [_format_session(dict(row)) for row in results]
    except Exception as e:
        logger.error(f"Error fetching today's sessions: {e}")
        return []


def get_sessions_by_date_range(start_date: str, end_date: str) -> List[Dict]:
    """Get sessions in date range."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT id, preset, category, task, duration_minutes, completed,
                       productivity_rating, notes, date, time, hour, day_of_week, created_at
                FROM sessions
                WHERE date >= %s AND date < %s AND completed = TRUE
                ORDER BY date DESC, time DESC
            """, (start_date, end_date))

            results = cur.fetchall()
            return [_format_session(dict(row)) for row in results]
    except Exception as e:
        logger.error(f"Error fetching sessions by date range: {e}")
        return []


def _format_session(row: Dict) -> Dict:
    """Format session row for API response."""
    return {
        '_id': str(row.get('id', '')),
        'id': str(row.get('id', '')),
        'preset': row.get('preset', 'standard'),
        'category': row.get('category', 'Other'),
        'task': row.get('task', ''),
        'duration_minutes': row.get('duration_minutes', 25),
        'completed': row.get('completed', True),
        'productivity_rating': float(row.get('productivity_rating')) if row.get('productivity_rating') is not None else None,
        'notes': row.get('notes', ''),
        'date': str(row.get('date', '')) if row.get('date') else '',
        'time': str(row.get('time', ''))[:5] if row.get('time') else '',
        'hour': row.get('hour', 12),
        'day_of_week': row.get('day_of_week', 0),
        'created_at': row.get('created_at').isoformat() if row.get('created_at') else None
    }


# =============================================================================
# USER PROFILE QUERIES
# =============================================================================

def get_user_profile() -> Dict:
    """Get user profile."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT user_id, xp, level, title, streak_freezes_available, created_at
                FROM user_profile
                WHERE user_id = 'default'
            """)
            row = cur.fetchone()
            if row:
                return {
                    'user_id': row['user_id'],
                    'level': row.get('level', 1),
                    'total_xp': row.get('xp', 0),
                    'xp': row.get('xp', 0),
                    'title': row.get('title', 'Začátečník'),
                    'streak': 0,  # Calculate from sessions if needed
                    'streak_freezes': row.get('streak_freezes_available', 1)
                }
            return {'level': 1, 'total_xp': 0, 'xp': 0, 'streak': 0}
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        return {'level': 1, 'total_xp': 0, 'xp': 0, 'streak': 0}


# =============================================================================
# SKILLS QUERIES
# =============================================================================

def get_skill_levels() -> List[Dict]:
    """Get all skill levels."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT category, xp, level, sessions_count
                FROM category_skills
                ORDER BY xp DESC
            """)
            results = cur.fetchall()
            return [{
                'category': row['category'],
                'level': row.get('level', 0),
                'xp': row.get('xp', 0),
                'current_xp': row.get('xp', 0),
                'sessions_count': row.get('sessions_count', 0)
            } for row in results]
    except Exception as e:
        logger.error(f"Error fetching skill levels: {e}")
        return []


# =============================================================================
# ACHIEVEMENTS QUERIES
# =============================================================================

def get_achievements() -> List[Dict]:
    """Get all achievements."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT id, achievement_id, progress, unlocked, unlocked_at, created_at
                FROM achievements
                ORDER BY unlocked DESC, progress DESC
            """)
            results = cur.fetchall()
            return [{
                '_id': str(row['id']),
                'id': row['achievement_id'],
                'achievement_id': row['achievement_id'],
                'progress': row.get('progress', 0),
                'unlocked': row.get('unlocked', False),
                'unlocked_at': row['unlocked_at'].isoformat() if row.get('unlocked_at') else None
            } for row in results]
    except Exception as e:
        logger.error(f"Error fetching achievements: {e}")
        return []


# =============================================================================
# CACHE QUERIES (for CacheManager)
# =============================================================================

def get_cached(cache_type: str, cache_key: str = None) -> Optional[Dict]:
    """Get cached response if valid."""
    try:
        with get_cursor() as cur:
            if cache_key:
                cur.execute("""
                    SELECT response, created_at
                    FROM ai_cache
                    WHERE cache_type = %s
                      AND cache_key = %s
                      AND expires_at > NOW()
                """, (cache_type, cache_key))
            else:
                cur.execute("""
                    SELECT response, created_at
                    FROM ai_cache
                    WHERE cache_type = %s
                      AND (cache_key IS NULL OR cache_key = '')
                      AND expires_at > NOW()
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (cache_type,))

            row = cur.fetchone()
            if row:
                data = row['response']
                if isinstance(data, str):
                    data = json.loads(data)
                data['from_cache'] = True
                data['cached_at'] = row['created_at'].isoformat() if row.get('created_at') else None
                return data
            return None
    except Exception as e:
        logger.error(f"Cache get error: {e}")
        return None


def set_cache(cache_type: str, data: Dict, cache_key: str = None, ttl_hours: float = 1):
    """Store response in cache."""
    try:
        with get_cursor() as cur:
            # Generate unique key for upsert
            full_key = f"{cache_type}:{cache_key or 'default'}"

            cur.execute("""
                INSERT INTO ai_cache (cache_key, cache_type, response, expires_at)
                VALUES (%s, %s, %s, NOW() + INTERVAL '%s hours')
                ON CONFLICT (cache_key) DO UPDATE SET
                    cache_type = EXCLUDED.cache_type,
                    response = EXCLUDED.response,
                    expires_at = EXCLUDED.expires_at,
                    created_at = NOW()
            """, (full_key, cache_type, json.dumps(data, default=str), ttl_hours))

            logger.info(f"Cached {cache_type} for {ttl_hours} hours")
    except Exception as e:
        logger.error(f"Cache set error: {e}")


def invalidate_all_cache() -> int:
    """Invalidate all caches (set expires_at to past)."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                UPDATE ai_cache
                SET expires_at = NOW() - INTERVAL '1 second'
                WHERE expires_at > NOW()
            """)
            count = cur.rowcount
            logger.info(f"Invalidated {count} cache entries")
            return count
    except Exception as e:
        logger.error(f"Cache invalidation error: {e}")
        return 0


def clear_all_cache() -> int:
    """Clear entire cache."""
    try:
        with get_cursor() as cur:
            cur.execute("DELETE FROM ai_cache")
            count = cur.rowcount
            logger.info(f"Cleared {count} cache entries")
            return count
    except Exception as e:
        logger.error(f"Cache clear error: {e}")
        return 0


def get_cache_status() -> Dict:
    """Get current cache status."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT
                    cache_type,
                    cache_key,
                    created_at,
                    expires_at,
                    expires_at > NOW() as valid
                FROM ai_cache
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()

            valid_count = sum(1 for r in rows if r.get('valid'))
            return {
                'total_cached': len(rows),
                'valid': valid_count,
                'invalidated': len(rows) - valid_count,
                'caches': [{
                    'type': r['cache_type'],
                    'key': r.get('cache_key'),
                    'generated_at': r['created_at'].isoformat() if r.get('created_at') else None,
                    'expires_at': r['expires_at'].isoformat() if r.get('expires_at') else None,
                    'valid': r.get('valid', False)
                } for r in rows]
            }
    except Exception as e:
        logger.error(f"Cache status error: {e}")
        return {'error': str(e)}


# =============================================================================
# SEMANTIC SEARCH (pgvector)
# =============================================================================

def semantic_search_sessions(query_embedding: List[float], limit: int = 10,
                             min_similarity: float = 0.4, days_back: int = 30) -> List[Dict]:
    """Search sessions by semantic similarity using pgvector."""
    try:
        cutoff = datetime.now() - timedelta(days=days_back)
        with get_cursor() as cur:
            cur.execute("""
                SELECT id, date, category, task, notes, productivity_rating,
                       1 - (notes_embedding <=> %s::vector) as similarity
                FROM sessions
                WHERE notes_embedding IS NOT NULL
                  AND created_at >= %s
                  AND 1 - (notes_embedding <=> %s::vector) >= %s
                ORDER BY notes_embedding <=> %s::vector
                LIMIT %s
            """, (query_embedding, cutoff, query_embedding, min_similarity, query_embedding, limit))

            results = cur.fetchall()
            return [{
                'id': str(row['id']),
                'date': str(row['date']) if row.get('date') else '',
                'category': row.get('category', 'Other'),
                'task': row.get('task', ''),
                'notes': row.get('notes', ''),
                'productivity_rating': float(row.get('productivity_rating')) if row.get('productivity_rating') is not None else None,
                'similarity': round(row.get('similarity', 0), 4)
            } for row in results]
    except Exception as e:
        logger.error(f"Semantic search error: {e}")
        return []


def get_rag_context(query_embedding: List[float], limit: int = 5) -> str:
    """Get RAG context from similar sessions."""
    similar = semantic_search_sessions(query_embedding, limit=limit)
    if not similar:
        return ""

    context = "Relevant past sessions:\n"
    for s in similar:
        context += f"- [{s['date']}] {s['category']}: {s['notes'][:150]}...\n"

    return context


# =============================================================================
# WELLNESS CHECK-IN QUERIES (for AI integration)
# =============================================================================

def get_wellness_checkin(target_date=None) -> Optional[Dict]:
    """Get wellness check-in for a specific date (default: today)."""
    if target_date is None:
        target_date = date.today()
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    try:
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
    except Exception as e:
        logger.error(f"Error fetching wellness check-in: {e}")
        return None


def get_wellness_history(days: int = 7) -> List[Dict]:
    """Get wellness check-in history for trend analysis."""
    start_date = date.today() - timedelta(days=days)

    try:
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
    except Exception as e:
        logger.error(f"Error fetching wellness history: {e}")
        return []


def get_wellness_average(days: int = 7) -> Optional[Dict]:
    """Get average wellness scores for ML integration."""
    start_date = date.today() - timedelta(days=days)

    try:
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
    except Exception as e:
        logger.error(f"Error calculating wellness average: {e}")
        return None
