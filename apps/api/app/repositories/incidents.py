from uuid import UUID

from control_schemas import IncidentContext, IncidentStatus
from sqlalchemy import text

from app.infrastructure.database import Database


class IncidentNotFoundError(Exception):
    """Raised when an incident is outside the authenticated project."""


class IncidentRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def list(
        self,
        project_id: UUID,
        *,
        limit: int,
        status: IncidentStatus | None,
    ) -> list[IncidentContext]:
        async with self._database.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT incident.id, incident.execution_id,
                               COALESCE(execution.request_id::text, execution.id::text)
                                   AS trace_id,
                               COALESCE(application.name, 'Unassigned') AS application_name,
                               COALESCE(execution.active_provider, 'Unassigned') AS provider,
                               COALESCE(execution.active_model, execution.requested_model) AS model,
                               incident.incident_type, incident.severity, incident.status,
                               incident.title, incident.evidence, incident.created_at,
                               incident.acknowledged_at, incident.resolved_at
                        FROM control.incidents incident
                        JOIN control.executions execution
                          ON execution.id = incident.execution_id
                        LEFT JOIN control.applications application
                          ON application.id = execution.application_id
                        WHERE execution.project_id = :project_id
                          AND (
                              CAST(:status AS text) IS NULL
                              OR incident.status = CAST(:status AS text)
                          )
                        ORDER BY incident.created_at DESC, incident.id
                        LIMIT :limit
                        """
                        ),
                        {
                            "project_id": project_id,
                            "status": status.value if status else None,
                            "limit": limit,
                        },
                    )
                )
                .mappings()
                .all()
            )
        return [IncidentContext.model_validate(dict(row)) for row in rows]

    async def update_status(
        self,
        project_id: UUID,
        incident_id: UUID,
        status: IncidentStatus,
    ) -> IncidentContext:
        async with self._database.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        UPDATE control.incidents incident
                        SET status = :status,
                            acknowledged_at = CASE
                                WHEN :status = 'acknowledged'
                                    THEN COALESCE(incident.acknowledged_at, now())
                                ELSE incident.acknowledged_at
                            END,
                            resolved_at = CASE
                                WHEN :status = 'resolved' THEN now()
                                WHEN :status = 'open' THEN NULL
                                ELSE incident.resolved_at
                            END
                        FROM control.executions execution
                        LEFT JOIN control.applications application
                          ON application.id = execution.application_id
                        WHERE incident.id = :incident_id
                          AND execution.id = incident.execution_id
                          AND execution.project_id = :project_id
                        RETURNING incident.id, incident.execution_id,
                                  COALESCE(execution.request_id::text, execution.id::text)
                                      AS trace_id,
                                  COALESCE(application.name, 'Unassigned')
                                      AS application_name,
                                  COALESCE(execution.active_provider, 'Unassigned')
                                      AS provider,
                                  COALESCE(execution.active_model, execution.requested_model)
                                      AS model,
                                  incident.incident_type, incident.severity,
                                  incident.status, incident.title, incident.evidence,
                                  incident.created_at, incident.acknowledged_at,
                                  incident.resolved_at
                        """
                        ),
                        {
                            "incident_id": incident_id,
                            "project_id": project_id,
                            "status": status.value,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise IncidentNotFoundError
        return IncidentContext.model_validate(dict(row))
