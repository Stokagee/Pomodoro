-- Migration: Add System State table for auto end-day feature
-- Date: 2025-01-14
-- Description: Create system_state table for tracking persistent system flags
--              (auto end-day completion state tracking)

-- Create system_state table for persistent state tracking
CREATE TABLE IF NOT EXISTS system_state (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for queries by updated timestamp
CREATE INDEX IF NOT EXISTS idx_system_state_updated_at ON system_state(updated_at DESC);

-- Initialize auto end-day state
INSERT INTO system_state (key, value, updated_at)
VALUES ('auto_end_day',
        '{"enabled": true, "last_completed_date": null, "last_run_at": null}'::jsonb,
        NOW())
ON CONFLICT (key) DO NOTHING;

-- Create trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_system_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_system_state_updated_at ON system_state;
CREATE TRIGGER trigger_update_system_state_updated_at
    BEFORE UPDATE ON system_state
    FOR EACH ROW
    EXECUTE FUNCTION update_system_state_updated_at();

COMMENT ON TABLE system_state IS 'Persistent system state tracking for various features (auto end-day, etc.)';
COMMENT ON COLUMN system_state.key IS 'Unique identifier for the state (e.g., "auto_end_day")';
COMMENT ON COLUMN system_state.value IS 'JSONB state data';
COMMENT ON COLUMN system_state.updated_at IS 'Last update timestamp';
