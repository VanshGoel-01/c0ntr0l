from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IncidentStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class IncidentContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    execution_id: UUID
    trace_id: str
    application_name: str
    provider: str
    model: str
    incident_type: str
    severity: str
    status: IncidentStatus
    title: str
    evidence: dict[str, Any]
    created_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class IncidentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: IncidentStatus
