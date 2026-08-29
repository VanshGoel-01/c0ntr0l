from uuid import UUID

import pytest
from app.core.security import generate_api_key, hash_api_key
from app.domain.auth import ApiKeyPrincipal, InvalidApiKeyError
from app.services.authentication import AuthenticationService

PRINCIPAL = ApiKeyPrincipal(
    api_key_id=UUID("00000000-0000-0000-0000-000000000001"),
    organization_id=UUID("00000000-0000-0000-0000-000000000002"),
    project_id=UUID("00000000-0000-0000-0000-000000000003"),
)


class FakeApiKeyRepository:
    def __init__(self, principal: ApiKeyPrincipal | None) -> None:
        self.principal = principal
        self.received_hash: str | None = None

    async def resolve_active_key(self, key_hash: str) -> ApiKeyPrincipal | None:
        self.received_hash = key_hash
        return self.principal


@pytest.mark.asyncio
async def test_authentication_hashes_key_before_repository_lookup() -> None:
    repository = FakeApiKeyRepository(PRINCIPAL)
    service = AuthenticationService(repository, "test-pepper")  # type: ignore[arg-type]
    raw_key = generate_api_key()

    result = await service.authenticate(raw_key)

    assert result == PRINCIPAL
    assert repository.received_hash == hash_api_key(raw_key, "test-pepper")
    assert raw_key != repository.received_hash


@pytest.mark.asyncio
async def test_malformed_key_is_rejected_without_database_lookup() -> None:
    repository = FakeApiKeyRepository(PRINCIPAL)
    service = AuthenticationService(repository, "test-pepper")  # type: ignore[arg-type]

    with pytest.raises(InvalidApiKeyError):
        await service.authenticate("not-a-control-key")

    assert repository.received_hash is None


@pytest.mark.asyncio
async def test_unknown_key_returns_the_same_authentication_error() -> None:
    repository = FakeApiKeyRepository(None)
    service = AuthenticationService(repository, "test-pepper")  # type: ignore[arg-type]

    with pytest.raises(InvalidApiKeyError):
        await service.authenticate(generate_api_key())
