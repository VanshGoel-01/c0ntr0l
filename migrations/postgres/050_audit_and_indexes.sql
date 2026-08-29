CREATE TABLE IF NOT EXISTS audit.events (
    id bigserial PRIMARY KEY,
    organization_id uuid,
    project_id uuid,
    execution_id uuid,
    actor_type text NOT NULL
        CHECK (actor_type IN ('system', 'user', 'api_key', 'operator')),
    actor_id text,
    event_type text NOT NULL,
    outcome text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(evidence) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE audit.events IS
    'Append-only sanitized audit evidence; never store secrets or raw tool arguments';

CREATE OR REPLACE FUNCTION audit.reject_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit.events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS audit_events_no_update ON audit.events;
CREATE TRIGGER audit_events_no_update
BEFORE UPDATE ON audit.events
FOR EACH ROW EXECUTE FUNCTION audit.reject_event_mutation();

DROP TRIGGER IF EXISTS audit_events_no_delete ON audit.events;
CREATE TRIGGER audit_events_no_delete
BEFORE DELETE ON audit.events
FOR EACH ROW EXECUTE FUNCTION audit.reject_event_mutation();

CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique
    ON control.users (lower(email)) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS organization_members_user_idx
    ON control.organization_members (user_id);
CREATE INDEX IF NOT EXISTS projects_organization_idx
    ON control.projects (organization_id);
CREATE INDEX IF NOT EXISTS applications_project_idx
    ON control.applications (project_id);
CREATE INDEX IF NOT EXISTS agents_application_idx
    ON control.agents (application_id);
CREATE INDEX IF NOT EXISTS executions_project_started_idx
    ON control.executions (project_id, started_at DESC);
CREATE INDEX IF NOT EXISTS executions_user_started_idx
    ON control.executions (user_id, started_at DESC) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS executions_status_idx
    ON control.executions (status, started_at DESC);
CREATE INDEX IF NOT EXISTS spans_execution_sequence_idx
    ON control.spans (execution_id, sequence_no);
CREATE INDEX IF NOT EXISTS spans_operation_fingerprint_idx
    ON control.spans (execution_id, operation_fingerprint)
    WHERE operation_fingerprint IS NOT NULL;
CREATE INDEX IF NOT EXISTS usage_execution_observed_idx
    ON control.usage_records (execution_id, observed_at);
CREATE INDEX IF NOT EXISTS usage_provider_model_idx
    ON control.usage_records (provider, model, observed_at DESC);
CREATE INDEX IF NOT EXISTS budget_scope_idx
    ON control.budget_policies (scope_type, scope_id)
    WHERE is_enabled;
CREATE INDEX IF NOT EXISTS budget_ledger_policy_time_idx
    ON control.budget_ledger (budget_policy_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS loop_observations_execution_idx
    ON control.loop_observations (execution_id, observed_at);
CREATE INDEX IF NOT EXISTS policy_decisions_execution_idx
    ON control.policy_decisions (execution_id, decided_at DESC);
CREATE INDEX IF NOT EXISTS incidents_open_idx
    ON control.incidents (status, severity, created_at DESC)
    WHERE status <> 'resolved';
CREATE INDEX IF NOT EXISTS provider_handoffs_execution_idx
    ON control.provider_handoffs (execution_id, initiated_at DESC);
CREATE INDEX IF NOT EXISTS audit_events_project_time_idx
    ON audit.events (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_events_execution_idx
    ON audit.events (execution_id, created_at);
