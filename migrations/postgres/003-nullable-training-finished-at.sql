-- Existing mirror databases created from an older 001 schema require this
-- before active training attempts (finished_at = NULL) can be dispatched.
ALTER TABLE baran_training_attempts
    ALTER COLUMN finished_at DROP NOT NULL;
