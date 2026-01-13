-- Migration: Add wellness_checkins table
-- Run this on existing databases to add wellness tracking

-- Create wellness_checkins table if not exists
CREATE TABLE IF NOT EXISTS wellness_checkins (
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

-- Create indexes if not exists
CREATE INDEX IF NOT EXISTS idx_wellness_date ON wellness_checkins(date DESC);
CREATE INDEX IF NOT EXISTS idx_wellness_overall ON wellness_checkins(overall_wellness);

-- Create trigger for updated_at (drop first to avoid conflicts)
DROP TRIGGER IF EXISTS update_wellness_checkins_updated_at ON wellness_checkins;
CREATE TRIGGER update_wellness_checkins_updated_at BEFORE UPDATE ON wellness_checkins
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
