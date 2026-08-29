CREATE TABLE IF NOT EXISTS control.loop_observations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id uuid NOT NULL
        REFERENCES control.executions(id) ON DELETE CASCADE,
    span_id uuid NOT NULL,
    operation_fingerprint text NOT NULL,
    occurrence_no integer NOT NULL CHECK (occurrence_no > 0),
    window_size integer NOT NULL CHECK (window_size > 0),
    action text NOT NULL CHECK (action IN ('allow', 'warn', 'block', 'cancel')),
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(evidence) = 'object'),
    observed_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (execution_id, span_id)
        REFERENCES control.spans(execution_id, id) ON DELETE CASCADE,
    UNIQUE (execution_id, operation_fingerprint, occurrence_no)
);

CREATE TABLE IF NOT EXISTS control.policy_decisions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id uuid NOT NULL
        REFERENCES control.executions(id) ON DELETE CASCADE,
    triggering_span_id uuid,
    budget_policy_id uuid
        REFERENCES control.budget_policies(id) ON DELETE SET NULL,
    policy_code text NOT NULL,
    policy_version text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('observe', 'warn', 'enforce')),
    outcome text NOT NULL
        CHECK (outcome IN ('allow', 'observe', 'warn', 'block', 'cancel', 'handoff')),
    final_execution_state text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(evidence) = 'object'),
    decided_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (execution_id, triggering_span_id)
        REFERENCES control.spans(execution_id, id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS control.incidents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id uuid NOT NULL
        REFERENCES control.executions(id) ON DELETE CASCADE,
    policy_decision_id uuid
        REFERENCES control.policy_decisions(id) ON DELETE SET NULL,
    triggering_span_id uuid,
    incident_type text NOT NULL
        CHECK (incident_type IN (
            'budget_exceeded', 'runaway_loop', 'provider_failure',
            'handoff_failure', 'manual_intervention'
        )),
    severity text NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    status text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'acknowledged', 'resolved')),
    title text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(evidence) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    acknowledged_at timestamptz,
    resolved_at timestamptz,
    FOREIGN KEY (execution_id, triggering_span_id)
        REFERENCES control.spans(execution_id, id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS control.provider_handoffs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id uuid NOT NULL
        REFERENCES control.executions(id) ON DELETE CASCADE,
    policy_decision_id uuid NOT NULL
        REFERENCES control.policy_decisions(id) ON DELETE RESTRICT,
    triggering_span_id uuid NOT NULL,
    source_provider text NOT NULL,
    source_model text NOT NULL,
    target_provider text NOT NULL,
    target_model text NOT NULL,
    reason_code text NOT NULL,
    status text NOT NULL DEFAULT 'approved'
        CHECK (status IN ('approved', 'summarizing', 'transferring', 'completed', 'failed')),
    summary_fingerprint text,
    summary_token_count integer
        CHECK (summary_token_count IS NULL OR summary_token_count >= 0),
    context_manifest jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(context_manifest) = 'object'),
    raw_context_stored boolean NOT NULL DEFAULT false,
    initiated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    expires_at timestamptz,
    failure_code text,
    FOREIGN KEY (execution_id, triggering_span_id)
        REFERENCES control.spans(execution_id, id) ON DELETE RESTRICT,
    CHECK (source_provider <> target_provider OR source_model <> target_model),
    CHECK (completed_at IS NULL OR completed_at >= initiated_at)
);

COMMENT ON COLUMN control.provider_handoffs.context_manifest IS
    'Sanitized context metadata; raw conversation content is not stored by default';
