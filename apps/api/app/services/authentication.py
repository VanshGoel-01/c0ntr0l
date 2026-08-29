from app.core.security import has_valid_api_key_shape, hash_api_key
from app.domain.auth import ApiKeyPrincipal, InvalidApiKeyError
from app.repositories.api_keys import ApiKeyRepository


class AuthenticationService:
    def __init__(self, repository: ApiKeyRepository, pepper: str) -> None:
        self._repository = repository
        self._pepper = pepper

    async def authenticate(self, raw_key: str) -> ApiKeyPrincipal:
        if not has_valid_api_key_shape(raw_key):
            raise InvalidApiKeyError
        principal = await self._repository.resolve_active_key(
            hash_api_key(raw_key, self._pepper)
        )
        if principal is None:
            raise InvalidApiKeyError
        return principal
