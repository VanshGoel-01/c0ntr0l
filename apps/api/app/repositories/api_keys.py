from uuid import UUID

from sqlalchemy import text

from app.domain.auth import ApiKeyPrincipal
from app.infrastructure.database import Database


class ApiKeyRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def resolve_active_key(self, key_hash: str) -> ApiKeyPrincipal | None:
        statement = text(
            """
            UPDATE control.project_api_keys AS api_key
            SET last_used_at = now()
            FROM control.projects AS project
            JOIN control.organizations AS organization
              ON organization.id = project.organization_id
            WHERE api_key.key_hash = :key_hash
              AND api_key.project_id = project.id
              AND api_key.is_active = true
              AND (api_key.expires_at IS NULL OR api_key.expires_at > now())
              AND project.status = 'active'
              AND organization.status = 'active'
            RETURNING
                api_key.id AS api_key_id,
                project.id AS project_id,
                organization.id AS organization_id
            """
        )
        async with self._database.begin() as connection:
            row = (
                (await connection.execute(statement, {"key_hash": key_hash}))
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return ApiKeyPrincipal(
            api_key_id=UUID(str(row["api_key_id"])),
            organization_id=UUID(str(row["organization_id"])),
            project_id=UUID(str(row["project_id"])),
        )
