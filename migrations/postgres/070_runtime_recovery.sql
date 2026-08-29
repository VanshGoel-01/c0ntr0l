CREATE TABLE IF NOT EXISTS control.continuity_checkpoints (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id uuid NOT NULL
        REFERENCES control.executions(id) ON DELETE CASCADE,
    policy_decision_id uuid
        REFERENCES control.policy_decisions(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'available'
        CHECK (status IN ('available', 'consumed', 'superseded', 'failed')),
    content_fingerprint text NOT NULL,
    packet jsonb NOT NULL CHECK (jsonb_typeof(packet) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    consumed_at timestamptz,
    CHECK (consumed_at IS NULL OR consumed_at >= created_at)
);

CREATE INDEX IF NOT EXISTS continuity_checkpoints_execution_created_idx
    ON control.continuity_checkpoints (execution_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS continuity_checkpoints_available_idx
    ON control.continuity_checkpoints (execution_id)
    WHERE status = 'available';

CREATE TABLE IF NOT EXISTS control.recovery_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_execution_id uuid NOT NULL
        REFERENCES control.executions(id) ON DELETE CASCADE,
    resumed_execution_id uuid
        REFERENCES control.executions(id) ON DELETE SET NULL,
    checkpoint_id uuid NOT NULL
        REFERENCES control.continuity_checkpoints(id) ON DELETE RESTRICT,
    strategy text NOT NULL
        CHECK (strategy IN (
            'retry_modified', 'model_handoff', 'manual_resume', 'stop'
        )),
    target_provider text,
    target_model text,
    status text NOT NULL
        CHECK (status IN ('prepared', 'completed', 'failed', 'stopped')),
    details jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(details) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CHECK (completed_at IS NULL OR completed_at >= created_at),
    CHECK (
        strategy <> 'model_handoff'
        OR (target_provider IS NOT NULL AND target_model IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS recovery_attempts_source_created_idx
    ON control.recovery_attempts (source_execution_id, created_at DESC);

COMMENT ON COLUMN control.continuity_checkpoints.packet IS
    'Sanitized execution state only; credentials and raw provider context are forbidden';

UPDATE control.continuity_checkpoints checkpoint
SET packet = jsonb_set(
    checkpoint.packet,
    '{source_provider}',
    to_jsonb(COALESCE(execution.active_provider, 'custom')),
    true
)
FROM control.executions execution
WHERE execution.id = checkpoint.execution_id
  AND NOT checkpoint.packet ? 'source_provider';
