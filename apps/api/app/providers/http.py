from collections.abc import AsyncIterator

from control_schemas import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatRequest,
    ProviderModelList,
    StreamOptions,
)
from httpx import (
    AsyncBaseTransport,
    AsyncClient,
    RequestError,
    Timeout,
    TimeoutException,
)
from pydantic import ValidationError

from app.providers.errors import (
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class HttpProviderClient:
    _MAX_STREAM_EVENT_BYTES = 1_048_576

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        transport: AsyncBaseTransport | None = None,
    ) -> None:
        self._client = AsyncClient(
            base_url=base_url,
            timeout=Timeout(timeout_seconds),
            follow_redirects=False,
            transport=transport,
        )

    async def complete(
        self,
        request: ChatRequest,
        demo_scenario: str | None = None,
    ) -> ChatCompletion:
        headers = {"X-Mock-Scenario": demo_scenario} if demo_scenario else None
        try:
            response = await self._client.post(
                "/v1/chat/completions",
                json=request.model_dump(mode="json"),
                headers=headers,
            )
        except TimeoutException as exc:
            raise ProviderTimeoutError from exc
        except RequestError as exc:
            raise ProviderUnavailableError from exc

        if response.status_code == 504:
            raise ProviderTimeoutError
        if response.status_code >= 500:
            raise ProviderUnavailableError
        if response.status_code >= 400:
            raise ProviderResponseError
        try:
            return ChatCompletion.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise ProviderResponseError from exc

    async def stream(
        self,
        request: ChatRequest,
        demo_scenario: str | None = None,
    ) -> AsyncIterator[ChatCompletionChunk]:
        headers = {"X-Mock-Scenario": demo_scenario} if demo_scenario else None
        stream_request = request.model_copy(
            update={
                "stream": True,
                "stream_options": StreamOptions(include_usage=True),
            }
        )
        try:
            async with self._client.stream(
                "POST",
                "/v1/chat/completions",
                json=stream_request.model_dump(mode="json", exclude_none=True),
                headers=headers,
            ) as response:
                self._raise_for_status(response.status_code)
                async for line in response.aiter_lines():
                    if not line or line.startswith(":") or not line.startswith("data:"):
                        continue
                    payload = line.removeprefix("data:").strip()
                    if payload == "[DONE]":
                        return
                    if len(payload.encode("utf-8")) > self._MAX_STREAM_EVENT_BYTES:
                        raise ProviderResponseError
                    try:
                        yield ChatCompletionChunk.model_validate_json(payload)
                    except (ValueError, ValidationError) as exc:
                        raise ProviderResponseError from exc
        except TimeoutException as exc:
            raise ProviderTimeoutError from exc
        except RequestError as exc:
            raise ProviderUnavailableError from exc

    async def list_models(self) -> tuple[str, ...]:
        try:
            response = await self._client.get("/v1/models")
        except TimeoutException as exc:
            raise ProviderTimeoutError from exc
        except RequestError as exc:
            raise ProviderUnavailableError from exc
        self._raise_for_status(response.status_code)
        try:
            payload = ProviderModelList.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise ProviderResponseError from exc
        return tuple(model.id for model in payload.data)

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if status_code == 504:
            raise ProviderTimeoutError
        if status_code >= 500:
            raise ProviderUnavailableError
        if status_code >= 400:
            raise ProviderResponseError

    async def close(self) -> None:
        await self._client.aclose()

    async def context_window(self, model: str) -> int | None:
        return None
