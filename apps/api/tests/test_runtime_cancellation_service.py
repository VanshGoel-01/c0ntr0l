from uuid import UUID

import pytest
from app.domain.auth import ApiKeyPrincipal
from app.repositories.runtime import RuntimeExecutionNotFoundError
from app.services.runtime import RuntimeService
from control_schemas import RuntimeCancellationResult

PRINCIPAL = ApiKeyPrincipal(
    api_key_id=UUID("00000000-0000-0000-0000-000000000001"),
    organization_id=UUID("00000000-0000-0000-0000-000000000002"),
    project_id=UUID("00000000-0000-0000-0000-000000000003"),
)
EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000004")


class FakeRepository:
    def __init__(self, authorized: bool = True) -> None:
        self.authorized = authorized
        self.cancelled = False

    async def authorize_execution(self, principal, execution_id):  # type: ignore[no-untyped-def]
        if not self.authorized:
            raise RuntimeExecutionNotFoundError

    async def cancel(self, principal, execution_id):  # type: ignore[no-untyped-def]
        self.cancelled = True
        return RuntimeCancellationResult(execution_id=execution_id, status="cancelled")


class FakeSignals:
    def __init__(self) -> None:
        self.requested: list[tuple[UUID, UUID]] = []

    async def request_cancellation(self, project_id, execution_id):  # type: ignore[no-untyped-def]
        self.requested.append((project_id, execution_id))

    async def clear_cancellation(self, project_id, execution_id):  # type: ignore[no-untyped-def]
        return None


class FakeRunner:
    pass


class FakeProviders:
    pass


def service(repository: FakeRepository, signals: FakeSignals) -> RuntimeService:
    return RuntimeService(
        repository,  # type: ignore[arg-type]
        signals,  # type: ignore[arg-type]
        FakeRunner(),  # type: ignore[arg-type]
        FakeProviders(),  # type: ignore[arg-type]
        8_192,
        256,
        0.85,
    )


@pytest.mark.asyncio
async def test_cancel_scopes_signal_after_authorization() -> None:
    repository = FakeRepository()
    signals = FakeSignals()

    result = await service(repository, signals).cancel(PRINCIPAL, EXECUTION_ID)

    assert result.status == "cancelled"
    assert repository.cancelled is True
    assert signals.requested == [(PRINCIPAL.project_id, EXECUTION_ID)]


@pytest.mark.asyncio
async def test_cancel_does_not_signal_unauthorized_execution() -> None:
    repository = FakeRepository(authorized=False)
    signals = FakeSignals()

    with pytest.raises(RuntimeExecutionNotFoundError):
        await service(repository, signals).cancel(PRINCIPAL, EXECUTION_ID)

    assert repository.cancelled is False
    assert signals.requested == []
