from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text


async def claim_budget_reservations(connection, execution_id: UUID) -> None:  # type: ignore[no-untyped-def]
    await connection.execute(
        text(
            """
            UPDATE control.budget_reservations
            SET claimed_requests = LEAST(
                    reserved_requests, claimed_requests + 1
                )
            WHERE execution_id = :execution_id
              AND status = 'active'
              AND expires_at > now()
              AND claimed_requests < reserved_requests
            """
        ),
        {"execution_id": execution_id},
    )


async def reconcile_budget_reservations(
    connection,  # type: ignore[no-untyped-def]
    execution_id: UUID,
    *,
    actual_tokens: int,
    actual_cost: Decimal,
    now: datetime,
) -> None:
    await connection.execute(
        text(
            """
            UPDATE control.budget_reservations
            SET reserved_tokens = GREATEST(
                    0,
                    reserved_tokens - CEIL(
                        reserved_tokens::numeric / GREATEST(
                            reserved_requests - COALESCE(actual_requests, 0), 1
                        )
                    )::bigint
                ),
                reserved_cost = GREATEST(
                    0,
                    reserved_cost - (
                        reserved_cost / GREATEST(
                            reserved_requests - COALESCE(actual_requests, 0), 1
                        )
                    )
                ),
                claimed_requests = GREATEST(
                    claimed_requests,
                    LEAST(
                        reserved_requests, COALESCE(actual_requests, 0) + 1
                    )
                ),
                actual_requests = LEAST(
                    reserved_requests, COALESCE(actual_requests, 0) + 1
                ),
                actual_tokens = COALESCE(actual_tokens, 0) + :actual_tokens,
                actual_cost = COALESCE(actual_cost, 0) + :actual_cost,
                status = CASE
                    WHEN COALESCE(actual_requests, 0) + 1 >= reserved_requests
                    THEN 'reconciled'
                    ELSE 'active'
                END,
                reconciled_at = CASE
                    WHEN COALESCE(actual_requests, 0) + 1 >= reserved_requests
                    THEN :now
                    ELSE NULL
                END
            WHERE execution_id = :execution_id
              AND status = 'active'
              AND expires_at > :now
              AND COALESCE(actual_requests, 0) < reserved_requests
            """
        ),
        {
            "execution_id": execution_id,
            "actual_tokens": actual_tokens,
            "actual_cost": actual_cost,
            "now": now,
        },
    )
