import hashlib
import time
from dataclasses import dataclass
from uuid import uuid4

from control_schemas import ChatCompletion, ChatRequest

from app.domain.auth import ApiKeyPrincipal
from app.providers.errors import ProviderError
from app.providers.http import HttpProviderClient
from app.repositories.executions import ExecutionRepository


class StreamingNotImplementedError(Exception):
    """Raised until durable streaming reconciliation is implemented."""


@dataclass(frozen=True, slots=True)
class ChatResult:
    execution_id: str
    completion: ChatCompletion


class ChatService:
    def __init__(
        self,
        repository: ExecutionRepository,
        provider: HttpProviderClient,
    ) -> None:
        self._repository = repository
        self._provider = provider

    async def complete(
        self,
        principal: ApiKeyPrincipal,
        request: ChatRequest,
        request_id: str | None,
        demo_scenario: str | None,
        application_slug: str | None = None,
        agent_slug: str | None = None,
    ) -> ChatResult:
        if request.stream:
            raise StreamingNotImplementedError

        resolved_request_id = request_id or f"req_{uuid4().hex}"
        input_fingerprint = self._fingerprint(request.model_dump_json())
        trace = await self._repository.start(
            principal,
            request.model,
            request.stream,
            resolved_request_id,
            input_fingerprint,
            application_slug,
            agent_slug,
        )
        started_at = time.perf_counter()
        try:
            completion = await self._provider.complete(request, demo_scenario)
        except ProviderError as exc:
            latency_ms = self._elapsed_ms(started_at)
            await self._repository.fail(
                trace,
                error_code=exc.code,
                attempt_status=exc.attempt_status,
                latency_ms=latency_ms,
            )
            raise

        latency_ms = self._elapsed_ms(started_at)
        await self._repository.complete(
            trace,
            completion,
            latency_ms,
            self._fingerprint(completion.model_dump_json()),
        )
        return ChatResult(
            execution_id=str(trace.execution_id),
            completion=completion,
        )

    @staticmethod
    def _fingerprint(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(0, round((time.perf_counter() - started_at) * 1000))
