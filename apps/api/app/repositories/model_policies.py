from uuid import UUID

from control_schemas import ModelPolicyContext, ModelPolicyUpsert
from sqlalchemy import text

from app.infrastructure.database import Database


class ModelPolicyRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def list(self, project_id: UUID) -> list[ModelPolicyContext]:
        async with self._database.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id, project_id, provider, model, mode, token_limit,
                               created_at, updated_at
                        FROM control.model_policies
                        WHERE project_id = :project_id
                        ORDER BY provider, model
                        """
                        ),
                        {"project_id": project_id},
                    )
                )
                .mappings()
                .all()
            )
        return [ModelPolicyContext.model_validate(dict(row)) for row in rows]

    async def get(
        self,
        project_id: UUID,
        provider: str,
        model: str,
    ) -> ModelPolicyContext | None:
        async with self._database.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id, project_id, provider, model, mode, token_limit,
                               created_at, updated_at
                        FROM control.model_policies
                        WHERE project_id = :project_id
                          AND provider = lower(:provider)
                          AND model = :model
                        """
                        ),
                        {
                            "project_id": project_id,
                            "provider": provider,
                            "model": model,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        return ModelPolicyContext.model_validate(dict(row)) if row else None

    async def upsert(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        api_key_id: UUID,
        policy: ModelPolicyUpsert,
    ) -> ModelPolicyContext:
        async with self._database.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        INSERT INTO control.model_policies (
                            project_id, provider, model, mode, token_limit
                        ) VALUES (
                            :project_id, :provider, :model, :mode, :token_limit
                        )
                        ON CONFLICT (project_id, provider, model)
                        DO UPDATE SET mode = EXCLUDED.mode,
                                      token_limit = EXCLUDED.token_limit,
                                      updated_at = now()
                        RETURNING id, project_id, provider, model, mode, token_limit,
                                  created_at, updated_at
                        """
                        ),
                        {
                            "project_id": project_id,
                            "provider": policy.provider,
                            "model": policy.model,
                            "mode": policy.mode.value,
                            "token_limit": policy.token_limit,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO audit.events (
                        organization_id, project_id, actor_type, actor_id,
                        event_type, outcome, evidence
                    ) VALUES (
                        :organization_id, :project_id, 'api_key', :actor_id,
                        'model_policy.updated', 'success',
                        jsonb_build_object(
                            'provider', CAST(:provider AS text),
                            'model', CAST(:model AS text),
                            'mode', CAST(:mode AS text),
                            'token_limit', CAST(:token_limit AS bigint)
                        )
                    )
                    """
                ),
                {
                    "organization_id": organization_id,
                    "project_id": project_id,
                    "actor_id": str(api_key_id),
                    "provider": policy.provider,
                    "model": policy.model,
                    "mode": policy.mode.value,
                    "token_limit": policy.token_limit,
                },
            )
        return ModelPolicyContext.model_validate(dict(row))
