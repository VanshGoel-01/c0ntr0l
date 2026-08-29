ALTER TABLE control.executions
    DROP CONSTRAINT IF EXISTS executions_request_id_key;

CREATE INDEX IF NOT EXISTS executions_project_request_idx
    ON control.executions (project_id, request_id);

COMMENT ON COLUMN control.executions.request_id IS
    'Caller correlation identifier; retries may create multiple executions with the same value';
