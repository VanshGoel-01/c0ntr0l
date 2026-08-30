from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExecutionTrace:
    execution_id: UUID
    root_span_id: UUID
    provider_span_id: UUID
    provider_attempt_id: UUID
    provider_name: str
