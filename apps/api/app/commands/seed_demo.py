import asyncio
from uuid import UUID

from sqlalchemy import text

from app.core.config import get_settings
from app.core.security import api_key_prefix, generate_api_key, hash_api_key
from app.infrastructure.database import Database


async def seed_demo() -> tuple[UUID, str]:
    settings = get_settings()
    database = Database(settings.database_url)
    raw_key = generate_api_key()
    try:
        async with database.begin() as connection:
            organization_id = UUID(
                str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO control.organizations (slug, name)
                                VALUES ('review-demo', 'Review Demo Organization')
                                ON CONFLICT (slug) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    status = 'active',
                                    updated_at = now()
                                RETURNING id
                                """
                            )
                        )
                    ).scalar_one()
                )
            )
            project_id = UUID(
                str(
                    (
                        await connection.execute(
                            text(
                                """
                                INSERT INTO control.projects (organization_id, slug, name)
                                VALUES (:organization_id, 'gateway-demo', 'Gateway Demo')
                                ON CONFLICT (organization_id, slug) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    status = 'active',
                                    updated_at = now()
                                RETURNING id
                                """
                            ),
                            {"organization_id": organization_id},
                        )
                    ).scalar_one()
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO control.project_api_keys (
                        project_id, name, key_prefix, key_hash
                    ) VALUES (
                        :project_id, 'review-demo', :key_prefix, :key_hash
                    )
                    ON CONFLICT (project_id, name) DO UPDATE SET
                        key_prefix = EXCLUDED.key_prefix,
                        key_hash = EXCLUDED.key_hash,
                        is_active = true,
                        expires_at = NULL
                    """
                ),
                {
                    "project_id": project_id,
                    "key_prefix": api_key_prefix(raw_key),
                    "key_hash": hash_api_key(
                        raw_key,
                        settings.api_key_pepper.get_secret_value(),
                    ),
                },
            )
    finally:
        await database.close()
    return project_id, raw_key


def main() -> None:
    project_id, raw_key = asyncio.run(seed_demo())
    print(f"PROJECT_ID={project_id}")
    print(f"CONTROL_API_KEY={raw_key}")
    print("The plaintext key was shown once and only its HMAC-SHA256 hash was stored.")


if __name__ == "__main__":
    main()
