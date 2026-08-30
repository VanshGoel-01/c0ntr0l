from collections.abc import Mapping
from typing import Protocol

from control_schemas import ChatCompletion, ChatRequest

from app.providers.errors import ProviderNotConfiguredError


class CompletionProvider(Protocol):
    async def complete(
        self,
        request: ChatRequest,
        demo_scenario: str | None = None,
    ) -> ChatCompletion: ...

    async def context_window(self, model: str) -> int | None: ...

    async def close(self) -> None: ...


class ProviderRegistry:
    def __init__(
        self,
        providers: Mapping[str, CompletionProvider],
        context_defaults: Mapping[str, int] | None = None,
    ) -> None:
        self._providers = {
            name.strip().lower(): provider for name, provider in providers.items()
        }
        self._context_defaults = {
            name.strip().lower(): value
            for name, value in (context_defaults or {}).items()
        }

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    async def complete(
        self,
        provider_name: str,
        request: ChatRequest,
    ) -> ChatCompletion:
        provider = self._providers.get(provider_name.strip().lower())
        if provider is None:
            raise ProviderNotConfiguredError
        return await provider.complete(request)

    async def context_window(
        self,
        provider_name: str,
        model: str,
        fallback: int,
    ) -> int:
        normalized = provider_name.strip().lower()
        provider = self._providers.get(normalized)
        if provider is not None:
            resolved = await provider.context_window(model)
            if resolved is not None and resolved > 0:
                return resolved
        return self._context_defaults.get(normalized, fallback)

    async def close(self) -> None:
        closed: set[int] = set()
        for provider in self._providers.values():
            identity = id(provider)
            if identity in closed:
                continue
            closed.add(identity)
            await provider.close()
