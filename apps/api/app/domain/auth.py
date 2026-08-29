from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ApiKeyPrincipal:
    api_key_id: UUID
    organization_id: UUID
    project_id: UUID


class InvalidApiKeyError(Exception):
    """Raised when a project API key cannot be authenticated."""
