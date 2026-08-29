CREATE TABLE IF NOT EXISTS control.usage_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id uuid NOT NULL
        REFERENCES control.executions(id) ON DELETE CASCADE,
    span_id uuid,
    provider_attempt_id uuid,
    source_type text NOT NULL
        CHECK (source_type IN ('provider_reported', 'locally_estimated', 'configured')),
    provider text,
    model text,
    input_tokens integer NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens integer NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    total_tokens integer GENERATED ALWAYS AS (input_tokens + output_tokens) STORED,
    cost_amount numeric(18, 8) NOT NULL DEFAULT 0 CHECK (cost_amount >= 0),
    currency char(3) NOT NULL DEFAULT 'USD',
    latency_ms integer CHECK (latency_ms IS NULL OR latency_ms >= 0),
    observed_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (execution_id, span_id)
        REFERENCES control.spans(execution_id, id) ON DELETE CASCADE,
    FOREIGN KEY (execution_id, provider_attempt_id)
        REFERENCES control.provider_attempts(execution_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS control.budget_policies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_type text NOT NULL
        CHECK (scope_type IN ('organization', 'user', 'project', 'application', 'agent')),
    scope_id uuid NOT NULL,
    name text NOT NULL,
    period_type text NOT NULL
        CHECK (period_type IN ('execution', 'daily', 'monthly', 'rolling')),
    window_seconds integer CHECK (window_seconds IS NULL OR window_seconds > 0),
    mode text NOT NULL DEFAULT 'observe'
        CHECK (mode IN ('observe', 'warn', 'enforce')),
    max_requests bigint CHECK (max_requests IS NULL OR max_requests > 0),
    max_tokens bigint CHECK (max_tokens IS NULL OR max_tokens > 0),
    max_cost numeric(18, 8) CHECK (max_cost IS NULL OR max_cost > 0),
    currency char(3) NOT NULL DEFAULT 'USD',
    is_enabled boolean NOT NULL DEFAULT true,
    starts_at timestamptz NOT NULL DEFAULT now(),
    ends_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (scope_type, scope_id, name),
    CHECK (max_requests IS NOT NULL OR max_tokens IS NOT NULL OR max_cost IS NOT NULL),
    CHECK (period_type = 'rolling' OR window_seconds IS NULL),
    CHECK (period_type <> 'rolling' OR window_seconds IS NOT NULL),
    CHECK (ends_at IS NULL OR ends_at > starts_at)
);

CREATE TABLE IF NOT EXISTS control.budget_reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_policy_id uuid NOT NULL
        REFERENCES control.budget_policies(id) ON DELETE CASCADE,
    execution_id uuid NOT NULL
        REFERENCES control.executions(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'reconciled', 'released', 'expired')),
    reserved_requests bigint NOT NULL DEFAULT 0 CHECK (reserved_requests >= 0),
    claimed_requests bigint NOT NULL DEFAULT 0 CHECK (claimed_requests >= 0),
    reserved_tokens bigint NOT NULL DEFAULT 0 CHECK (reserved_tokens >= 0),
    reserved_cost numeric(18, 8) NOT NULL DEFAULT 0 CHECK (reserved_cost >= 0),
    actual_requests bigint CHECK (actual_requests IS NULL OR actual_requests >= 0),
    actual_tokens bigint CHECK (actual_tokens IS NULL OR actual_tokens >= 0),
    actual_cost numeric(18, 8) CHECK (actual_cost IS NULL OR actual_cost >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    reconciled_at timestamptz,
    UNIQUE (budget_policy_id, execution_id),
    CHECK (expires_at > created_at)
);

CREATE TABLE IF NOT EXISTS control.budget_ledger (
    id bigserial PRIMARY KEY,
    budget_policy_id uuid NOT NULL
        REFERENCES control.budget_policies(id) ON DELETE CASCADE,
    execution_id uuid REFERENCES control.executions(id) ON DELETE SET NULL,
    reservation_id uuid
        REFERENCES control.budget_reservations(id) ON DELETE SET NULL,
    event_type text NOT NULL
        CHECK (event_type IN ('reserve', 'reconcile', 'release', 'charge', 'reject')),
    idempotency_key text NOT NULL UNIQUE,
    request_delta bigint NOT NULL DEFAULT 0,
    token_delta bigint NOT NULL DEFAULT 0,
    cost_delta numeric(18, 8) NOT NULL DEFAULT 0,
    usage_source text
        CHECK (usage_source IS NULL OR usage_source IN (
            'provider_reported', 'locally_estimated', 'configured'
        )),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(evidence) = 'object')
);

COMMENT ON COLUMN control.budget_policies.scope_type IS
    'User scope aggregates a person across projects; lower scopes isolate individual workloads';
