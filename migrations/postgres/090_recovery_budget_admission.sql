ALTER TABLE control.recovery_attempts
    DROP CONSTRAINT IF EXISTS recovery_attempts_status_check;

ALTER TABLE control.recovery_attempts
    ADD CONSTRAINT recovery_attempts_status_check
    CHECK (status IN ('prepared', 'completed', 'failed', 'stopped', 'blocked'));

COMMENT ON CONSTRAINT recovery_attempts_status_check
    ON control.recovery_attempts IS
    'Blocked records are recoveries denied by context or budget admission before provider invocation';
