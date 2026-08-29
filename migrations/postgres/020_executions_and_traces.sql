CREATE TABLE IF NOT EXISTS control.executions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id text NOT NULL,
    organization_id uuid NOT NULL
        REFERENCES control.organizations(id) ON DELETE RESTRICT,
    project_id uuid NOT NULL REFERENCES control.projects(id) ON DELETE RESTRICT,
    user_id uuid REFERENCES control.users(id) ON DELETE SET NULL,
    application_id uuid REFERENCES control.applications(id) ON DELETE SET NULL,
    agent_id uuid REFERENCES control.agents(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'accepted'
        CHECK (status IN (
            'accepted', 'running', 'completed', 'blocked', 'cancelled',
            'failed', 'handed_off'
        )),
    requested_model text NOT NULL,
    active_provider text,
    active_model text,
    is_streaming boolean NOT NULL DEFAULT true,
    input_fingerprint text,
    output_fingerprint text,
    final_reason text,
    error_code text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(metadata) = 'object'),
    CHECK (completed_at IS NULL OR completed_at >= started_at)
);

CREATE TABLE IF NOT EXISTS control.spans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id uuid NOT NULL
        REFERENCES control.executions(id) ON DELETE CASCADE,
    parent_span_id uuid,
    sequence_no integer NOT NULL CHECK (sequence_no > 0),
    kind text NOT NULL
        CHECK (kind IN ('gateway', 'provider', 'tool', 'policy', 'handoff')),
    name text NOT NULL,
    status text NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'blocked', 'cancelled', 'failed')),
    operation_fingerprint text,
    tool_name text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    duration_ms integer CHECK (duration_ms IS NULL OR duration_ms >= 0),
    error_code text,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(attributes) = 'object'),
    UNIQUE (execution_id, sequence_no),
    UNIQUE (execution_id, id),
    FOREIGN KEY (execution_id, parent_span_id)
        REFERENCES control.spans(execution_id, id) ON DELETE CASCADE,
    CHECK (completed_at IS NULL OR completed_at >= started_at)
);

CREATE TABLE IF NOT EXISTS control.provider_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id uuid NOT NULL
        REFERENCES control.executions(id) ON DELETE CASCADE,
    span_id uuid NOT NULL,
    attempt_no integer NOT NULL CHECK (attempt_no > 0),
    provider text NOT NULL,
    model text NOT NULL,
    status text NOT NULL DEFAULT 'started'
        CHECK (status IN ('started', 'streaming', 'completed', 'timed_out', 'failed')),
    circuit_state text NOT NULL DEFAULT 'closed'
        CHECK (circuit_state IN ('closed', 'open', 'half_open')),
    retryable boolean,
    error_category text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (execution_id, attempt_no),
    UNIQUE (execution_id, id),
    FOREIGN KEY (execution_id, span_id)
        REFERENCES control.spans(execution_id, id) ON DELETE CASCADE,
    CHECK (completed_at IS NULL OR completed_at >= started_at)
);

COMMENT ON COLUMN control.spans.attributes IS
    'Sanitized metadata only; raw authorization headers and tool arguments are forbidden';
