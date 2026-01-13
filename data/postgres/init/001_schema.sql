-- Pomodoro Timer PostgreSQL Schema
-- Migration from MongoDB to PostgreSQL + pgvector

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- =============================================================================
-- SESSIONS - Main table with vector embeddings for semantic search
-- =============================================================================
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    preset VARCHAR(50) NOT NULL DEFAULT 'deep_work',
    category VARCHAR(100) NOT NULL DEFAULT 'Other',
    task VARCHAR(200),
    duration_minutes INTEGER NOT NULL DEFAULT 52,
    completed BOOLEAN NOT NULL DEFAULT TRUE,
    productivity_rating NUMERIC(5,2),  -- 0-100 scale
    notes TEXT,
    notes_embedding VECTOR(384),  -- paraphrase-multilingual-MiniLM-L12-v2
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    time TIME NOT NULL DEFAULT CURRENT_TIME,
    hour SMALLINT GENERATED ALWAYS AS (EXTRACT(HOUR FROM time)::smallint) STORED,
    day_of_week SMALLINT GENERATED ALWAYS AS (EXTRACT(DOW FROM date)::smallint) STORED,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Session indexes
CREATE INDEX idx_sessions_date ON sessions(date DESC);
CREATE INDEX idx_sessions_date_completed ON sessions(date DESC, completed);
CREATE INDEX idx_sessions_completed ON sessions(completed);
CREATE INDEX idx_sessions_category ON sessions(category);
CREATE INDEX idx_sessions_preset ON sessions(preset);
CREATE INDEX idx_sessions_hour ON sessions(hour);
CREATE INDEX idx_sessions_day_of_week ON sessions(day_of_week);
CREATE INDEX idx_sessions_created_at ON sessions(created_at DESC);

-- HNSW index for semantic search (cosine similarity)
CREATE INDEX idx_sessions_embedding ON sessions
    USING hnsw (notes_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text search on notes
CREATE INDEX idx_sessions_notes_fts ON sessions
    USING GIN (to_tsvector('simple', COALESCE(notes, '')));

-- =============================================================================
-- DAILY FOCUS - Daily themes and planning
-- =============================================================================
CREATE TABLE daily_focus (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date DATE UNIQUE NOT NULL,
    themes JSONB DEFAULT '[]'::jsonb,  -- [{theme, planned_sessions, notes}]
    notes TEXT,
    planned_sessions INTEGER DEFAULT 0,
    actual_sessions INTEGER DEFAULT 0,
    productivity_score NUMERIC(5,2) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_daily_focus_date ON daily_focus(date DESC);

-- =============================================================================
-- WEEKLY PLANS
-- =============================================================================
CREATE TABLE weekly_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    week_start DATE UNIQUE NOT NULL,
    week_number SMALLINT,
    year SMALLINT,
    goals JSONB DEFAULT '[]'::jsonb,  -- Array of goal strings
    days JSONB DEFAULT '[]'::jsonb,   -- Array of {date, themes, notes}
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_weekly_plans_week_start ON weekly_plans(week_start DESC);
CREATE INDEX idx_weekly_plans_year_week ON weekly_plans(year, week_number);

-- =============================================================================
-- WEEKLY REVIEWS
-- =============================================================================
CREATE TABLE weekly_reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    week_start DATE UNIQUE NOT NULL,
    week_number SMALLINT,
    year SMALLINT,
    stats JSONB DEFAULT '{}'::jsonb,
    theme_breakdown JSONB DEFAULT '[]'::jsonb,
    reflections JSONB DEFAULT '{}'::jsonb,  -- {what_worked, what_to_improve, lessons_learned}
    next_week_goals JSONB DEFAULT '[]'::jsonb,
    ml_insights JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_weekly_reviews_week_start ON weekly_reviews(week_start DESC);

-- =============================================================================
-- ACHIEVEMENTS
-- =============================================================================
CREATE TABLE achievements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    achievement_id VARCHAR(100) UNIQUE NOT NULL,
    progress INTEGER DEFAULT 0,
    unlocked BOOLEAN DEFAULT FALSE,
    unlocked_at TIMESTAMPTZ,
    notified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_achievements_achievement_id ON achievements(achievement_id);
CREATE INDEX idx_achievements_unlocked ON achievements(unlocked);

-- =============================================================================
-- USER PROFILE (single row for gamification)
-- =============================================================================
CREATE TABLE user_profile (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(50) UNIQUE NOT NULL DEFAULT 'default',
    xp INTEGER DEFAULT 0,
    total_xp_earned INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    title VARCHAR(100) DEFAULT 'Zacatecnik',
    streak_freezes_available INTEGER DEFAULT 1,
    streak_freeze_used_dates JSONB DEFAULT '[]'::jsonb,
    vacation_mode BOOLEAN DEFAULT FALSE,
    vacation_days_remaining INTEGER DEFAULT 0,
    vacation_start_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- CATEGORY SKILLS
-- =============================================================================
CREATE TABLE category_skills (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category VARCHAR(100) UNIQUE NOT NULL,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 0,
    sessions_count INTEGER DEFAULT 0,
    total_minutes INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_category_skills_category ON category_skills(category);

-- =============================================================================
-- XP HISTORY
-- =============================================================================
CREATE TABLE xp_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    amount INTEGER NOT NULL,
    source VARCHAR(50) NOT NULL,
    old_xp INTEGER NOT NULL,
    new_xp INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_xp_history_created_at ON xp_history(created_at DESC);

-- =============================================================================
-- DAILY CHALLENGES
-- =============================================================================
CREATE TABLE daily_challenges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date DATE UNIQUE NOT NULL,
    challenge_id VARCHAR(100) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    target INTEGER DEFAULT 1,
    condition_type VARCHAR(50) NOT NULL,
    difficulty VARCHAR(20) DEFAULT 'medium',
    xp_reward INTEGER DEFAULT 50,
    progress INTEGER DEFAULT 0,
    completed BOOLEAN DEFAULT FALSE,
    completed_at TIMESTAMPTZ,
    ai_generated BOOLEAN DEFAULT FALSE,
    extra_conditions JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_daily_challenges_date ON daily_challenges(date DESC);

-- =============================================================================
-- WEEKLY QUESTS
-- =============================================================================
CREATE TABLE weekly_quests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    week_start DATE NOT NULL,
    quests JSONB NOT NULL DEFAULT '[]'::jsonb,
    ai_generated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_weekly_quests_week_start ON weekly_quests(week_start DESC);

-- =============================================================================
-- INSIGHTS (ML insights cache)
-- =============================================================================
CREATE TABLE insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type VARCHAR(100) UNIQUE NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_insights_type ON insights(type);

-- =============================================================================
-- PREDICTIONS
-- =============================================================================
CREATE TABLE predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date DATE NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_predictions_date ON predictions(date DESC);
CREATE INDEX idx_predictions_created_at ON predictions(created_at DESC);

-- =============================================================================
-- WELLNESS CHECKINS - Morning wellness check-in data
-- =============================================================================
CREATE TABLE wellness_checkins (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date DATE UNIQUE NOT NULL,
    sleep_quality NUMERIC(5,2),       -- 0-100 scale
    energy_level NUMERIC(5,2),        -- 0-100 scale
    mood NUMERIC(5,2),                -- 0-100 scale
    stress_level NUMERIC(5,2),        -- 0-100 scale (inverse: low = good)
    motivation NUMERIC(5,2),          -- 0-100 scale
    focus_ability NUMERIC(5,2),       -- 0-100 scale
    overall_wellness NUMERIC(5,2),    -- Calculated weighted average
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_wellness_date ON wellness_checkins(date DESC);
CREATE INDEX idx_wellness_overall ON wellness_checkins(overall_wellness);

-- =============================================================================
-- AI CACHE (for Ollama responses)
-- =============================================================================
CREATE TABLE ai_cache (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cache_key VARCHAR(255) UNIQUE NOT NULL,
    cache_type VARCHAR(100) NOT NULL,
    params_hash VARCHAR(64),
    response JSONB NOT NULL,
    ttl_hours NUMERIC(5,2) NOT NULL DEFAULT 4,
    expires_at TIMESTAMPTZ NOT NULL,
    invalidated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ai_cache_key ON ai_cache(cache_key);
CREATE INDEX idx_ai_cache_type ON ai_cache(cache_type);
CREATE INDEX idx_ai_cache_expires ON ai_cache(expires_at);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Function to normalize old 1-5 ratings to 0-100
CREATE OR REPLACE FUNCTION normalize_rating(rating NUMERIC)
RETURNS NUMERIC AS $$
BEGIN
    IF rating IS NULL THEN
        RETURN NULL;
    END IF;
    IF rating >= 1 AND rating <= 5 THEN
        RETURN rating * 20;  -- Convert 1-5 to 20-100
    END IF;
    RETURN rating;  -- Already 0-100
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Function for semantic search on session notes
CREATE OR REPLACE FUNCTION search_sessions_semantic(
    query_embedding VECTOR(384),
    limit_count INTEGER DEFAULT 10,
    min_similarity FLOAT DEFAULT 0.4,
    days_back INTEGER DEFAULT 30
)
RETURNS TABLE (
    session_id UUID,
    session_date DATE,
    category VARCHAR,
    task VARCHAR,
    notes TEXT,
    productivity_rating NUMERIC,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.id,
        s.date,
        s.category,
        s.task,
        s.notes,
        s.productivity_rating,
        (1 - (s.notes_embedding <=> query_embedding))::FLOAT AS similarity
    FROM sessions s
    WHERE s.notes_embedding IS NOT NULL
      AND s.notes IS NOT NULL
      AND s.notes != ''
      AND s.date >= CURRENT_DATE - days_back
      AND (1 - (s.notes_embedding <=> query_embedding)) >= min_similarity
    ORDER BY s.notes_embedding <=> query_embedding
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- Function to get RAG context for AI
CREATE OR REPLACE FUNCTION get_rag_context(
    query_embedding VECTOR(384),
    context_limit INTEGER DEFAULT 5
)
RETURNS TEXT AS $$
DECLARE
    result TEXT := '';
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT
            s.date,
            s.category,
            LEFT(s.notes, 200) as notes_preview,
            s.productivity_rating
        FROM sessions s
        WHERE s.notes_embedding IS NOT NULL
          AND s.completed = TRUE
          AND s.date >= CURRENT_DATE - 30
        ORDER BY s.notes_embedding <=> query_embedding
        LIMIT context_limit
    LOOP
        result := result || '- [' || rec.date || '] ' || rec.category || ': ' ||
                  COALESCE(rec.notes_preview, '') || E'\n';
    END LOOP;

    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_sessions_updated_at BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_daily_focus_updated_at BEFORE UPDATE ON daily_focus
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_weekly_plans_updated_at BEFORE UPDATE ON weekly_plans
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_weekly_reviews_updated_at BEFORE UPDATE ON weekly_reviews
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_achievements_updated_at BEFORE UPDATE ON achievements
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_profile_updated_at BEFORE UPDATE ON user_profile
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_category_skills_updated_at BEFORE UPDATE ON category_skills
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_insights_updated_at BEFORE UPDATE ON insights
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_wellness_checkins_updated_at BEFORE UPDATE ON wellness_checkins
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- INITIAL DATA
-- =============================================================================

-- Create default user profile
INSERT INTO user_profile (user_id, xp, level, title)
VALUES ('default', 0, 1, 'Zacatecnik')
ON CONFLICT (user_id) DO NOTHING;

-- =============================================================================
-- VIEWS (optional helpers)
-- =============================================================================

-- Today's stats view
CREATE OR REPLACE VIEW v_today_stats AS
SELECT
    COUNT(*) as total_sessions,
    COUNT(*) FILTER (WHERE completed) as completed_sessions,
    COALESCE(SUM(duration_minutes) FILTER (WHERE completed), 0) as total_minutes,
    ROUND(COALESCE(AVG(productivity_rating) FILTER (WHERE completed AND productivity_rating IS NOT NULL), 0), 1) as avg_productivity
FROM sessions
WHERE date = CURRENT_DATE;

-- Weekly stats view
CREATE OR REPLACE VIEW v_weekly_stats AS
SELECT
    date,
    COUNT(*) as sessions,
    SUM(duration_minutes) as minutes,
    ROUND(AVG(productivity_rating) FILTER (WHERE productivity_rating IS NOT NULL), 1) as avg_rating
FROM sessions
WHERE date >= DATE_TRUNC('week', CURRENT_DATE)
  AND completed = TRUE
GROUP BY date
ORDER BY date;

-- Streak calculation view
CREATE OR REPLACE VIEW v_streak_days AS
SELECT DISTINCT date
FROM sessions
WHERE completed = TRUE
ORDER BY date DESC;
