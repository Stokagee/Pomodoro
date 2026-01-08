# MongoDB to PostgreSQL Migration Guide

This document describes the migration from MongoDB to PostgreSQL + pgvector.

## Overview

The Pomodoro Timer has been migrated from MongoDB to PostgreSQL with the pgvector extension for:
- **Vector similarity search** using embeddings (RAG)
- **Better SQL aggregations** for analytics
- **Semantic search** on session notes
- **Single database** for all data (relational + vectors)

## Architecture Changes

### Before (MongoDB)
```
web-service → MongoDB
ml-service  → MongoDB
```

### After (PostgreSQL + pgvector)
```
web-service → PostgreSQL (with pgvector)
ml-service  → PostgreSQL + Embedding Service (sentence-transformers)
```

## New Components

1. **PostgreSQL with pgvector** - Vector-enabled database
2. **Embedding Service** (`ml-service/services/embedding_service.py`)
   - Uses `paraphrase-multilingual-MiniLM-L12-v2` model
   - 384-dimensional embeddings
   - Supports 50+ languages including Czech
3. **Semantic Search** - Search session notes by meaning
4. **RAG Integration** - AI responses enhanced with relevant session context

## Migration Steps

### 1. Start Services with Migration Profile

```bash
# Start both MongoDB (for reading) and PostgreSQL (for writing)
docker-compose --profile migration up -d mongodb postgres pgadmin
```

### 2. Run Migration Script

```bash
# From project root
cd scripts

# Dry run first
python migrate_to_postgres.py --dry-run

# Run actual migration
python migrate_to_postgres.py

# Or with custom URIs
python migrate_to_postgres.py \
    --mongo-uri mongodb://localhost:27017/pomodoro \
    --postgres-url postgresql://pomodoro:pomodoro_secret@localhost:5432/pomodoro
```

### 3. Verify Migration

```bash
# Check PostgreSQL data
docker exec -it pomodoro-postgres psql -U pomodoro -c "SELECT COUNT(*) FROM sessions;"

# Check pgvector extension
docker exec -it pomodoro-postgres psql -U pomodoro -c "SELECT * FROM pg_extension WHERE extname = 'vector';"

# Check embeddings
docker exec -it pomodoro-postgres psql -U pomodoro -c "SELECT COUNT(*) FROM sessions WHERE notes_embedding IS NOT NULL;"
```

### 4. Start Full Stack

```bash
# Stop migration mode
docker-compose --profile migration down

# Start production mode (without MongoDB)
docker-compose up -d
```

## New API Endpoints

### Semantic Search
```http
GET /api/semantic-search?query=productivity&limit=10
```

### Embedding Service Health
```http
GET /api/embedding/health
```

## Environment Variables

### Web Service
```env
DATABASE_URL=postgresql://pomodoro:pomodoro_secret@postgres:5432/pomodoro
```

### ML Service
```env
DATABASE_URL=postgresql://pomodoro:pomodoro_secret@postgres:5432/pomodoro
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_CACHE_DIR=/app/models
```

## Database Schema

Key tables:
- `sessions` - Work sessions with `notes_embedding VECTOR(384)`
- `daily_focus` - Daily themes and focus areas
- `weekly_plans` / `weekly_reviews` - Weekly planning data
- `user_profile` - User XP, level, streaks
- `achievements` - Unlocked achievements
- `category_skills` - Per-category skill levels
- `ai_cache` - Cached AI responses

## Rollback

If you need to rollback to MongoDB:

1. Restore `docker-compose.yml` from git
2. Restore `web/models/database.py` from git
3. Restore `ml-service/app.py` and `ml-service/models/ai_analyzer.py` from git
4. Remove PostgreSQL containers and volumes

```bash
docker-compose down -v
git checkout docker-compose.yml web/models/database.py ml-service/
docker-compose up -d
```

## Troubleshooting

### Embedding model download fails
```bash
# Pre-download model manually
docker exec -it pomodoro-ml-service python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

### pgvector extension not available
```bash
# Verify using pgvector image
docker exec -it pomodoro-postgres psql -U pomodoro -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Connection pool exhausted
Check if all connections are being properly returned:
```python
# Always use context managers
with get_cursor() as cur:
    cur.execute("SELECT ...")
```
