from control_schemas import ChatCompletion, ChatRequest
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

    async def close(self) -> None:
        await self._client.aclose()

    async def context_window(self, model: str) -> int | None:
        return None
