from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from app.repositories.budget_reservations import (
    claim_budget_reservations,
    reconcile_budget_reservations,
)

EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000001")


class RecordingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def execute(self, statement, parameters):  # type: ignore[no-untyped-def]
        self.calls.append((str(statement), parameters))


@pytest.mark.asyncio
async def test_claim_only_consumes_unclaimed_active_reservation() -> None:
    connection = RecordingConnection()

    await claim_budget_reservations(connection, EXECUTION_ID)

    statement, parameters = connection.calls[0]
    assert "claimed_requests < reserved_requests" in statement
    assert "expires_at > now()" in statement
    assert parameters == {"execution_id": EXECUTION_ID}


@pytest.mark.asyncio
async def test_reconcile_replaces_one_estimate_with_actual_usage() -> None:
    connection = RecordingConnection()
    now = datetime(2026, 8, 30, tzinfo=UTC)

    await reconcile_budget_reservations(
        connection,
        EXECUTION_ID,
        actual_tokens=42,
        actual_cost=Decimal("0.25"),
        now=now,
    )

    statement, parameters = connection.calls[0]
    assert "reserved_tokens - CEIL" in statement
    assert "actual_requests = LEAST" in statement
    assert "THEN 'reconciled'" in statement
    assert parameters == {
        "execution_id": EXECUTION_ID,
        "actual_tokens": 42,
        "actual_cost": Decimal("0.25"),
        "now": now,
    }
