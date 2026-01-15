-- Migration: Add End Day columns to daily_focus table
-- Date: 2025-01-14
-- Description: Add columns for end-of-day recap functionality

-- Add end-of-day columns to daily_focus table
ALTER TABLE daily_focus
    ADD COLUMN IF NOT EXISTS end_mood NUMERIC(5,2),           -- 0-100 mood at end of day
    ADD COLUMN IF NOT EXISTS end_notes TEXT,                   -- end of day notes/reflection
    ADD COLUMN IF NOT EXISTS day_completed BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

-- Add index for completed days queries
CREATE INDEX IF NOT EXISTS idx_daily_focus_day_completed ON daily_focus(day_completed, date DESC);
