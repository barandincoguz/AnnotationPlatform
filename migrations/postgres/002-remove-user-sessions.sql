-- One-time security migration: bearer session tokens are local-only.
-- Run after deploying SQLite migration v0009 and the updated mirror code.
BEGIN;

ALTER TABLE IF EXISTS baran_activity_events
    DROP CONSTRAINT IF EXISTS baran_activity_events_session_id_fkey;

DROP TABLE IF EXISTS baran_user_sessions;

COMMIT;
