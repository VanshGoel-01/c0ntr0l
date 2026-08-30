from uuid import UUID

from control_schemas import ApplicationContext, BudgetPolicyContext, WorkspaceContext
from sqlalchemy import text

from app.infrastructure.database import Database


class WorkspaceRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def get(self, project_id: UUID) -> WorkspaceContext | None:
        async with self._database.connect() as connection:
            workspace_row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT organization.id AS organization_id,
                               organization.name AS organization_name,
                               project.id AS project_id,
                               project.slug AS project_slug,
                               project.name AS project_name,
                               count(DISTINCT execution.id) FILTER (
                                   WHERE execution.started_at >= now() - interval '24 hours'
                               ) AS requests_24h,
                               COALESCE(sum(usage.total_tokens) FILTER (
                                   WHERE execution.started_at >= now() - interval '24 hours'
                               ), 0) AS tokens_24h,
                               COALESCE(sum(usage.cost_amount) FILTER (
                                   WHERE execution.started_at >= now() - interval '24 hours'
                               ), 0) AS cost_24h
                        FROM control.projects project
                        JOIN control.organizations organization
                          ON organization.id = project.organization_id
                        LEFT JOIN control.executions execution
                          ON execution.project_id = project.id
                        LEFT JOIN control.usage_records usage
                          ON usage.execution_id = execution.id
                        WHERE project.id = :project_id
                        GROUP BY organization.id, organization.name,
                                 project.id, project.slug, project.name
                        """
                        ),
                        {"project_id": project_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if workspace_row is None:
                return None

            application_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, slug, name, environment, status
                        FROM control.applications
                        WHERE project_id = :project_id AND status <> 'archived'
                        ORDER BY name
                        """
                    ),
                    {"project_id": project_id},
                )
            ).mappings()
            budget_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, name, scope_type, scope_id, period_type, mode,
                               max_requests, max_tokens, max_cost, currency, is_enabled
                        FROM control.budget_policies
                        WHERE (scope_type = 'project' AND scope_id = :project_id)
                           OR (scope_type = 'application' AND scope_id IN (
                               SELECT id FROM control.applications
                               WHERE project_id = :project_id
                           ))
                        ORDER BY scope_type, name
                        """
                    ),
                    {"project_id": project_id},
                )
            ).mappings()

        return WorkspaceContext(
            **dict(workspace_row),
            applications=[
                ApplicationContext.model_validate(dict(row)) for row in application_rows
            ],
            budgets=[
                BudgetPolicyContext.model_validate(dict(row)) for row in budget_rows
            ],
        )
