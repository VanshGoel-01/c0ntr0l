ALTER TABLE control.provider_attempts
    DROP CONSTRAINT IF EXISTS provider_attempts_status_check;

ALTER TABLE control.provider_attempts
    ADD CONSTRAINT provider_attempts_status_check
    CHECK (status IN (
        'started', 'streaming', 'completed', 'timed_out', 'failed', 'skipped'
    ));
