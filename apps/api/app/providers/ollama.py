from typing import Any

from httpx import AsyncBaseTransport, RequestError, TimeoutException

from app.providers.http import HttpProviderClient


class OllamaProviderClient(HttpProviderClient):
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        transport: AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(base_url, timeout_seconds, transport)

    async def context_window(self, model: str) -> int | None:
        try:
            running = await self._client.get("/api/ps")
            if running.status_code < 400:
                running_payload: dict[str, Any] = running.json()
                for loaded in running_payload.get("models", []):
                    if not isinstance(loaded, dict):
                        continue
                    loaded_name = str(loaded.get("name", ""))
                    if loaded_name in {model, f"{model}:latest"}:
                        active_context = loaded.get("context_length")
                        if isinstance(active_context, int) and active_context > 0:
                            return active_context
            response = await self._client.post("/api/show", json={"model": model})
        except (RequestError, TimeoutException, ValueError):
            return None
        if response.status_code >= 400:
            return None
        try:
            payload: dict[str, Any] = response.json()
        except ValueError:
            return None
        model_info = payload.get("model_info")
        if not isinstance(model_info, dict):
            return None
        for key, value in model_info.items():
            if str(key).endswith(".context_length") and isinstance(value, int):
                return value
        return None
