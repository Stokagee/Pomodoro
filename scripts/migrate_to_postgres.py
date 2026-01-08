"""
MongoDB to PostgreSQL Migration Script

Migrates all collections from MongoDB to PostgreSQL with pgvector embeddings.
Generates embeddings for session notes using sentence-transformers.

Usage:
    # Start MongoDB with migration profile
    docker-compose --profile migration up -d mongodb postgres

    # Run migration
    python scripts/migrate_to_postgres.py

    # Or with custom connections
    python scripts/migrate_to_postgres.py \
        --mongo-uri mongodb://localhost:27017/pomodoro \
        --postgres-url postgresql://pomodoro:pomodoro_secret@localhost:5432/pomodoro
"""

import os
import sys
import argparse
import logging
from datetime import datetime, date, time
from typing import Optional, List, Dict, Any
import json

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_mongo_connection(uri: str):
    """Connect to MongoDB."""
    try:
        from pymongo import MongoClient
        client = MongoClient(uri)
        # Test connection
        client.admin.command('ping')
        logger.info(f"Connected to MongoDB: {uri}")
        return client
    except ImportError:
        logger.error("pymongo not installed. Run: pip install pymongo")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)


def get_postgres_connection(url: str):
    """Connect to PostgreSQL."""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(url)
        logger.info(f"Connected to PostgreSQL")
        return conn
    except ImportError:
        logger.error("psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        sys.exit(1)


def get_embedding_model():
    """Load sentence-transformers model for embeddings."""
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np

        model_name = os.getenv('EMBEDDING_MODEL', 'paraphrase-multilingual-MiniLM-L12-v2')
        logger.info(f"Loading embedding model: {model_name}")

        model = SentenceTransformer(model_name)
        logger.info(f"Model loaded. Dimensions: {model.get_sentence_embedding_dimension()}")

        return model
    except ImportError:
        logger.warning("sentence-transformers not installed. Embeddings will be skipped.")
        return None
    except Exception as e:
        logger.warning(f"Failed to load embedding model: {e}. Embeddings will be skipped.")
        return None


def generate_embedding(model, text: str) -> Optional[List[float]]:
    """Generate embedding for text."""
    if model is None or not text or not text.strip():
        return None

    try:
        import numpy as np
        embedding = model.encode(text, convert_to_numpy=True)
        # Normalize for cosine similarity
        embedding = embedding / np.linalg.norm(embedding)
        return embedding.tolist()
    except Exception as e:
        logger.warning(f"Failed to generate embedding: {e}")
        return None


def parse_date(value) -> Optional[date]:
    """Parse date from various formats."""
    if value is None:
        return None

    if isinstance(value, date):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            # Try ISO format first
            return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
        except:
            pass

        try:
            # Try YYYY-MM-DD
            return datetime.strptime(value, '%Y-%m-%d').date()
        except:
            pass

    return None


def parse_time(value) -> Optional[time]:
    """Parse time from various formats."""
    if value is None:
        return None

    if isinstance(value, time):
        return value

    if isinstance(value, datetime):
        return value.time()

    if isinstance(value, str):
        try:
            return datetime.strptime(value, '%H:%M').time()
        except:
            pass

        try:
            return datetime.strptime(value, '%H:%M:%S').time()
        except:
            pass

    return None


def migrate_sessions(mongo_db, pg_conn, embedding_model):
    """Migrate sessions collection."""
    logger.info("Migrating sessions...")

    cursor = pg_conn.cursor()
    sessions = list(mongo_db.sessions.find())

    if not sessions:
        logger.info("No sessions to migrate")
        return 0

    logger.info(f"Found {len(sessions)} sessions to migrate")

    # Generate embeddings in batch for efficiency
    notes_list = [s.get('notes', '') for s in sessions]
    embeddings = []

    if embedding_model:
        logger.info("Generating embeddings for session notes...")
        for i, notes in enumerate(notes_list):
            if i % 50 == 0:
                logger.info(f"  Processing {i}/{len(notes_list)}...")
            embeddings.append(generate_embedding(embedding_model, notes))
    else:
        embeddings = [None] * len(sessions)

    migrated = 0
    for i, session in enumerate(sessions):
        try:
            session_date = parse_date(session.get('date')) or date.today()
            session_time = parse_time(session.get('time')) or time(12, 0)

            # Get timestamp for created_at
            created_at = session.get('timestamp') or session.get('created_at')
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                except:
                    created_at = datetime.now()
            elif not isinstance(created_at, datetime):
                created_at = datetime.now()

            cursor.execute("""
                INSERT INTO sessions
                (preset, category, task, duration_minutes, completed,
                 productivity_rating, notes, notes_embedding, date, time, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                session.get('preset', 'deep_work'),
                session.get('category', 'Other'),
                session.get('task', ''),
                session.get('duration_minutes', 52),
                session.get('completed', True),
                session.get('productivity_rating'),
                session.get('notes', ''),
                embeddings[i],
                session_date,
                session_time,
                created_at
            ))
            migrated += 1

        except Exception as e:
            pg_conn.rollback()
            logger.warning(f"Failed to migrate session {i}: {e}")

    pg_conn.commit()
    logger.info(f"Migrated {migrated} sessions")
    return migrated


def migrate_daily_focus(mongo_db, pg_conn):
    """Migrate daily_focus collection."""
    logger.info("Migrating daily_focus...")

    cursor = pg_conn.cursor()
    records = list(mongo_db.daily_focus.find())

    if not records:
        logger.info("No daily_focus records to migrate")
        return 0

    migrated = 0
    for record in records:
        try:
            focus_date = parse_date(record.get('date'))
            if not focus_date:
                continue

            cursor.execute("""
                INSERT INTO daily_focus
                (date, themes, notes, planned_sessions, actual_sessions, productivity_score)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    themes = EXCLUDED.themes,
                    notes = EXCLUDED.notes,
                    planned_sessions = EXCLUDED.planned_sessions,
                    actual_sessions = EXCLUDED.actual_sessions,
                    productivity_score = EXCLUDED.productivity_score
            """, (
                focus_date,
                json.dumps(record.get('themes', [])),
                record.get('notes', ''),
                record.get('planned_sessions', 0),
                record.get('actual_sessions', 0),
                record.get('productivity_score', 0)
            ))
            migrated += 1

        except Exception as e:
            pg_conn.rollback()
            logger.warning(f"Failed to migrate daily_focus: {e}")

    pg_conn.commit()
    logger.info(f"Migrated {migrated} daily_focus records")
    return migrated


def migrate_weekly_plans(mongo_db, pg_conn):
    """Migrate weekly_plans collection."""
    logger.info("Migrating weekly_plans...")

    cursor = pg_conn.cursor()
    records = list(mongo_db.weekly_plans.find())

    if not records:
        logger.info("No weekly_plans to migrate")
        return 0

    migrated = 0
    for record in records:
        try:
            week_start = parse_date(record.get('week_start'))
            if not week_start:
                continue

            cursor.execute("""
                INSERT INTO weekly_plans
                (week_start, week_number, year, goals, days)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (week_start) DO UPDATE SET
                    week_number = EXCLUDED.week_number,
                    year = EXCLUDED.year,
                    goals = EXCLUDED.goals,
                    days = EXCLUDED.days
            """, (
                week_start,
                record.get('week_number'),
                record.get('year'),
                json.dumps(record.get('goals', [])),
                json.dumps(record.get('days', []))
            ))
            migrated += 1

        except Exception as e:
            pg_conn.rollback()
            logger.warning(f"Failed to migrate weekly_plan: {e}")

    pg_conn.commit()
    logger.info(f"Migrated {migrated} weekly_plans")
    return migrated


def migrate_weekly_reviews(mongo_db, pg_conn):
    """Migrate weekly_reviews collection."""
    logger.info("Migrating weekly_reviews...")

    cursor = pg_conn.cursor()
    records = list(mongo_db.weekly_reviews.find())

    if not records:
        logger.info("No weekly_reviews to migrate")
        return 0

    migrated = 0
    for record in records:
        try:
            week_start = parse_date(record.get('week_start'))
            if not week_start:
                continue

            cursor.execute("""
                INSERT INTO weekly_reviews
                (week_start, stats, reflections)
                VALUES (%s, %s, %s)
                ON CONFLICT (week_start) DO UPDATE SET
                    stats = EXCLUDED.stats,
                    reflections = EXCLUDED.reflections
            """, (
                week_start,
                json.dumps(record.get('stats', {})),
                json.dumps(record.get('reflections', {}))
            ))
            migrated += 1

        except Exception as e:
            pg_conn.rollback()
            logger.warning(f"Failed to migrate weekly_review: {e}")

    pg_conn.commit()
    logger.info(f"Migrated {migrated} weekly_reviews")
    return migrated


def migrate_user_profile(mongo_db, pg_conn):
    """Migrate user_profile collection."""
    logger.info("Migrating user_profile...")

    cursor = pg_conn.cursor()

    # Try different collection names
    profile = mongo_db.user_profile.find_one() or mongo_db.users.find_one()

    if not profile:
        logger.info("No user_profile to migrate")
        return 0

    try:
        cursor.execute("""
            INSERT INTO user_profile
            (user_id, xp, level, title, streak_freezes_available)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                xp = EXCLUDED.xp,
                level = EXCLUDED.level,
                title = EXCLUDED.title,
                streak_freezes_available = EXCLUDED.streak_freezes_available
        """, (
            profile.get('user_id', 'default'),
            profile.get('xp', 0),
            profile.get('level', 1),
            profile.get('title', 'Začátečník'),
            profile.get('streak_freezes', 1)
        ))
        pg_conn.commit()
        logger.info("Migrated user_profile")
        return 1

    except Exception as e:
        pg_conn.rollback()
        logger.warning(f"Failed to migrate user_profile: {e}")
        return 0


def migrate_achievements(mongo_db, pg_conn):
    """Migrate achievements collection."""
    logger.info("Migrating achievements...")

    cursor = pg_conn.cursor()
    records = list(mongo_db.achievements.find())

    if not records:
        logger.info("No achievements to migrate")
        return 0

    migrated = 0
    for record in records:
        try:
            achievement_id = record.get('achievement_id') or record.get('id')
            if not achievement_id:
                continue

            unlocked_at = record.get('unlocked_at')
            if isinstance(unlocked_at, str):
                try:
                    unlocked_at = datetime.fromisoformat(unlocked_at.replace('Z', '+00:00'))
                except:
                    unlocked_at = None

            cursor.execute("""
                INSERT INTO achievements
                (achievement_id, progress, unlocked, unlocked_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (achievement_id) DO UPDATE SET
                    progress = EXCLUDED.progress,
                    unlocked = EXCLUDED.unlocked,
                    unlocked_at = EXCLUDED.unlocked_at
            """, (
                achievement_id,
                record.get('progress', 0),
                record.get('unlocked', False),
                unlocked_at
            ))
            migrated += 1

        except Exception as e:
            pg_conn.rollback()
            logger.warning(f"Failed to migrate achievement: {e}")

    pg_conn.commit()
    logger.info(f"Migrated {migrated} achievements")
    return migrated


def migrate_category_skills(mongo_db, pg_conn):
    """Migrate category_skills collection."""
    logger.info("Migrating category_skills...")

    cursor = pg_conn.cursor()
    records = list(mongo_db.category_skills.find())

    if not records:
        logger.info("No category_skills to migrate")
        return 0

    migrated = 0
    for record in records:
        try:
            category = record.get('category')
            if not category:
                continue

            cursor.execute("""
                INSERT INTO category_skills
                (category, xp, level, sessions_count)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (category) DO UPDATE SET
                    xp = EXCLUDED.xp,
                    level = EXCLUDED.level,
                    sessions_count = EXCLUDED.sessions_count
            """, (
                category,
                record.get('xp', 0),
                record.get('level', 0),
                record.get('sessions_count', 0)
            ))
            migrated += 1

        except Exception as e:
            pg_conn.rollback()
            logger.warning(f"Failed to migrate category_skill: {e}")

    pg_conn.commit()
    logger.info(f"Migrated {migrated} category_skills")
    return migrated


def migrate_daily_challenges(mongo_db, pg_conn):
    """Migrate daily_challenges collection."""
    logger.info("Migrating daily_challenges...")

    cursor = pg_conn.cursor()
    records = list(mongo_db.daily_challenges.find())

    if not records:
        logger.info("No daily_challenges to migrate")
        return 0

    migrated = 0
    for record in records:
        try:
            challenge_date = parse_date(record.get('date'))
            if not challenge_date:
                continue

            # Handle both old format (challenge as object) and direct fields
            challenge = record.get('challenge', {})
            if isinstance(challenge, str):
                challenge = {'description': challenge}

            # Extract fields from challenge object or directly from record
            challenge_id = challenge.get('id') or record.get('challenge_id', 'migrated')
            title = challenge.get('title') or record.get('title', 'Migrated Challenge')
            description = challenge.get('description') or record.get('description', '')
            target = challenge.get('target') or record.get('target', 1)
            condition_type = challenge.get('condition_type') or record.get('condition_type', 'sessions')
            difficulty = challenge.get('difficulty') or record.get('difficulty', 'medium')
            xp_reward = challenge.get('xp_reward') or record.get('xp_reward', 50)

            cursor.execute("""
                INSERT INTO daily_challenges
                (date, challenge_id, title, description, target, condition_type,
                 difficulty, xp_reward, progress, completed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    challenge_id = EXCLUDED.challenge_id,
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    target = EXCLUDED.target,
                    condition_type = EXCLUDED.condition_type,
                    difficulty = EXCLUDED.difficulty,
                    xp_reward = EXCLUDED.xp_reward,
                    progress = EXCLUDED.progress,
                    completed = EXCLUDED.completed
            """, (
                challenge_date,
                challenge_id,
                title,
                description,
                target,
                condition_type,
                difficulty,
                xp_reward,
                record.get('progress', 0),
                record.get('completed', False)
            ))
            migrated += 1

        except Exception as e:
            pg_conn.rollback()
            logger.warning(f"Failed to migrate daily_challenge: {e}")

    pg_conn.commit()
    logger.info(f"Migrated {migrated} daily_challenges")
    return migrated


def migrate_ai_cache(mongo_db, pg_conn):
    """Migrate ai_cache collection."""
    logger.info("Migrating ai_cache...")

    cursor = pg_conn.cursor()
    records = list(mongo_db.ai_cache.find())

    if not records:
        logger.info("No ai_cache to migrate")
        return 0

    migrated = 0
    for record in records:
        try:
            cache_key = record.get('cache_key') or record.get('key')
            if not cache_key:
                continue

            expires_at = record.get('expires_at')
            if isinstance(expires_at, str):
                try:
                    expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                except:
                    expires_at = datetime.now()
            elif not isinstance(expires_at, datetime):
                expires_at = datetime.now()

            response = record.get('response', {})
            if isinstance(response, str):
                try:
                    response = json.loads(response)
                except:
                    response = {'data': response}

            cursor.execute("""
                INSERT INTO ai_cache
                (cache_key, endpoint, response, expires_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (cache_key) DO UPDATE SET
                    endpoint = EXCLUDED.endpoint,
                    response = EXCLUDED.response,
                    expires_at = EXCLUDED.expires_at
            """, (
                cache_key,
                record.get('endpoint', ''),
                json.dumps(response),
                expires_at
            ))
            migrated += 1

        except Exception as e:
            pg_conn.rollback()
            logger.warning(f"Failed to migrate ai_cache: {e}")

    pg_conn.commit()
    logger.info(f"Migrated {migrated} ai_cache records")
    return migrated


def verify_migration(mongo_db, pg_conn):
    """Verify migration by comparing record counts."""
    logger.info("\n=== Migration Verification ===")

    cursor = pg_conn.cursor()

    collections = [
        ('sessions', 'sessions'),
        ('daily_focus', 'daily_focus'),
        ('weekly_plans', 'weekly_plans'),
        ('weekly_reviews', 'weekly_reviews'),
        ('achievements', 'achievements'),
        ('category_skills', 'category_skills'),
        ('daily_challenges', 'daily_challenges'),
    ]

    all_ok = True
    for mongo_coll, pg_table in collections:
        mongo_count = mongo_db[mongo_coll].count_documents({})
        cursor.execute(f"SELECT COUNT(*) FROM {pg_table}")
        pg_count = cursor.fetchone()[0]

        status = "✓" if pg_count >= mongo_count else "✗"
        if pg_count < mongo_count:
            all_ok = False

        logger.info(f"  {status} {pg_table}: MongoDB={mongo_count}, PostgreSQL={pg_count}")

    # Check embeddings
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE notes_embedding IS NOT NULL")
    embeddings_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE notes IS NOT NULL AND notes != ''")
    notes_count = cursor.fetchone()[0]
    logger.info(f"  Embeddings: {embeddings_count}/{notes_count} sessions with notes have embeddings")

    return all_ok


def main():
    parser = argparse.ArgumentParser(description='Migrate Pomodoro data from MongoDB to PostgreSQL')
    parser.add_argument('--mongo-uri', default=os.getenv('MONGO_URI', 'mongodb://localhost:27017/pomodoro'),
                        help='MongoDB connection URI')
    parser.add_argument('--postgres-url', default=os.getenv('DATABASE_URL', 'postgresql://pomodoro:pomodoro_secret@localhost:5432/pomodoro'),
                        help='PostgreSQL connection URL')
    parser.add_argument('--skip-embeddings', action='store_true',
                        help='Skip generating embeddings (faster migration)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Only show what would be migrated')

    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("Pomodoro MongoDB to PostgreSQL Migration")
    logger.info("=" * 50)

    # Connect to databases
    mongo_client = get_mongo_connection(args.mongo_uri)
    mongo_db = mongo_client.pomodoro

    pg_conn = get_postgres_connection(args.postgres_url)

    # Load embedding model
    embedding_model = None
    if not args.skip_embeddings:
        embedding_model = get_embedding_model()

    if args.dry_run:
        logger.info("\n=== DRY RUN - No data will be migrated ===")
        logger.info(f"Sessions: {mongo_db.sessions.count_documents({})}")
        logger.info(f"Daily Focus: {mongo_db.daily_focus.count_documents({})}")
        logger.info(f"Weekly Plans: {mongo_db.weekly_plans.count_documents({})}")
        logger.info(f"Weekly Reviews: {mongo_db.weekly_reviews.count_documents({})}")
        logger.info(f"Achievements: {mongo_db.achievements.count_documents({})}")
        logger.info(f"Category Skills: {mongo_db.category_skills.count_documents({})}")
        logger.info(f"Daily Challenges: {mongo_db.daily_challenges.count_documents({})}")
        logger.info(f"AI Cache: {mongo_db.ai_cache.count_documents({})}")
        return

    # Run migrations
    logger.info("\n=== Starting Migration ===\n")

    total_migrated = 0
    total_migrated += migrate_sessions(mongo_db, pg_conn, embedding_model)
    total_migrated += migrate_daily_focus(mongo_db, pg_conn)
    total_migrated += migrate_weekly_plans(mongo_db, pg_conn)
    total_migrated += migrate_weekly_reviews(mongo_db, pg_conn)
    total_migrated += migrate_user_profile(mongo_db, pg_conn)
    total_migrated += migrate_achievements(mongo_db, pg_conn)
    total_migrated += migrate_category_skills(mongo_db, pg_conn)
    total_migrated += migrate_daily_challenges(mongo_db, pg_conn)
    total_migrated += migrate_ai_cache(mongo_db, pg_conn)

    # Verify
    all_ok = verify_migration(mongo_db, pg_conn)

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info(f"Migration complete! Total records migrated: {total_migrated}")
    if all_ok:
        logger.info("All collections migrated successfully!")
    else:
        logger.warning("Some records may not have been migrated. Check warnings above.")
    logger.info("=" * 50)

    # Cleanup
    mongo_client.close()
    pg_conn.close()


if __name__ == '__main__':
    main()
