CREATE TABLE IF NOT EXISTS control.model_policies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL
        REFERENCES control.projects(id) ON DELETE CASCADE,
    provider text NOT NULL
        CHECK (provider ~ '^[a-z0-9][a-z0-9_-]{0,62}$'),
    model text NOT NULL CHECK (char_length(model) BETWEEN 1 AND 255),
    mode text NOT NULL DEFAULT 'observe'
        CHECK (mode IN ('observe', 'warn', 'block')),
    token_limit bigint CHECK (token_limit IS NULL OR token_limit > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, provider, model)
);

CREATE INDEX IF NOT EXISTS model_policies_project_idx
    ON control.model_policies (project_id, provider, model);

COMMENT ON TABLE control.model_policies IS
    'Project-scoped model review and enforcement settings; no provider credentials are stored';

COMMENT ON COLUMN control.model_policies.token_limit IS
    'Optional per-call ceiling for projected input plus requested output tokens';
