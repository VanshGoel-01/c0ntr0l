ALTER TABLE control.policy_decisions
    ADD COLUMN IF NOT EXISTS model_policy_id uuid
        REFERENCES control.model_policies(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS policy_decisions_model_policy_idx
    ON control.policy_decisions (model_policy_id, decided_at DESC)
    WHERE model_policy_id IS NOT NULL;
