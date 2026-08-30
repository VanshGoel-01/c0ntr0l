ALTER TABLE control.budget_reservations
ADD COLUMN IF NOT EXISTS claimed_requests bigint NOT NULL DEFAULT 0
    CHECK (claimed_requests >= 0);

COMMENT ON COLUMN control.budget_reservations.claimed_requests IS
    'Approved requests already claimed by provider attempts; unclaimed requests remain budget reservations';
