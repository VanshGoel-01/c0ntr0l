import asyncio
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from control_schemas import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatRequest,
    ProviderAvailability,
    ProviderCatalog,
    ProviderSummary,
)

from app.providers.errors import (
    ProviderError,
    ProviderModelNotFoundError,
    ProviderNotConfiguredError,
    ProviderSelectionAmbiguousError,
    ProviderUnavailableError,
)


class CompletionProvider(Protocol):
    async def complete(
        self,
        request: ChatRequest,
        demo_scenario: str | None = None,
    ) -> ChatCompletion: ...

    def stream(
        self,
        request: ChatRequest,
        demo_scenario: str | None = None,
    ) -> AsyncIterator[ChatCompletionChunk]: ...

    async def list_models(self) -> tuple[str, ...]: ...

    async def context_window(self, model: str) -> int | None: ...

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ProviderSelection:
    name: str
    provider: CompletionProvider


class ProviderRegistry:
    def __init__(
        self,
        providers: Mapping[str, CompletionProvider],
        context_defaults: Mapping[str, int] | None = None,
        catalog_timeout_seconds: float = 2.0,
        catalog_ttl_seconds: float = 5.0,
    ) -> None:
        self._providers = {
            name.strip().lower(): provider for name, provider in providers.items()
        }
        self._context_defaults = {
            name.strip().lower(): value
            for name, value in (context_defaults or {}).items()
        }
        self._catalog_timeout_seconds = catalog_timeout_seconds
        self._catalog_ttl_seconds = catalog_ttl_seconds
        self._model_cache: dict[str, tuple[float, tuple[str, ...]]] = {}
        self._refresh_lock = asyncio.Lock()
        self._model_refreshes: dict[str, asyncio.Task[tuple[str, ...]]] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    async def select(
        self,
        model: str,
        requested_provider: str | None = None,
    ) -> ProviderSelection:
        normalized = (requested_provider or "auto").strip().lower()
        if normalized != "auto":
            provider = self._providers.get(normalized)
            if provider is None:
                raise ProviderNotConfiguredError
            if model not in await self._models(normalized):
                raise ProviderModelNotFoundError
            return ProviderSelection(normalized, provider)

        names = tuple(self._providers)
        results = await asyncio.gather(
            *(self._models(name) for name in names),
            return_exceptions=True,
        )
        matches: list[str] = []
        had_failure = False
        for name, result in zip(names, results, strict=True):
            if isinstance(result, ProviderError):
                had_failure = True
            elif isinstance(result, Exception):
                raise result
            elif model in result:
                matches.append(name)
        if len(matches) > 1:
            raise ProviderSelectionAmbiguousError
        if len(matches) == 1:
            name = matches[0]
            return ProviderSelection(name, self._providers[name])
        if had_failure:
            raise ProviderUnavailableError
        raise ProviderModelNotFoundError

    async def catalog(self) -> ProviderCatalog:
        names = tuple(sorted(self._providers))
        results = await asyncio.gather(
            *(self._models(name) for name in names),
            return_exceptions=True,
        )
        providers = []
        for name, result in zip(names, results, strict=True):
            if isinstance(result, ProviderError):
                providers.append(
                    ProviderSummary(
                        name=name,
                        status=ProviderAvailability.UNAVAILABLE,
                        models=[],
                    )
                )
                continue
            if isinstance(result, Exception):
                raise result
            providers.append(
                ProviderSummary(
                    name=name,
                    status=ProviderAvailability.OPERATIONAL,
                    models=sorted(result),
                )
            )
        return ProviderCatalog(checked_at=datetime.now(UTC), providers=providers)

    async def _models(self, name: str) -> tuple[str, ...]:
        now = time.monotonic()
        cached = self._model_cache.get(name)
        if cached is not None and cached[0] > now:
            return cached[1]
        async with self._refresh_lock:
            cached = self._model_cache.get(name)
            if cached is not None and cached[0] > time.monotonic():
                return cached[1]
            refresh = self._model_refreshes.get(name)
            if refresh is None:
                refresh = asyncio.create_task(self._refresh_models(name))
                self._model_refreshes[name] = refresh
                refresh.add_done_callback(
                    lambda completed, provider_name=name: self._clear_refresh(
                        provider_name, completed
                    )
                )
        return await asyncio.shield(refresh)

    async def _refresh_models(self, name: str) -> tuple[str, ...]:
        try:
            async with asyncio.timeout(self._catalog_timeout_seconds):
                models = await self._providers[name].list_models()
        except TimeoutError as exc:
            raise ProviderUnavailableError from exc
        self._model_cache[name] = (
            time.monotonic() + self._catalog_ttl_seconds,
            models,
        )
        return models

    def _clear_refresh(
        self,
        name: str,
        task: asyncio.Task[tuple[str, ...]],
    ) -> None:
        if self._model_refreshes.get(name) is task:
            self._model_refreshes.pop(name, None)

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
