import asyncio
from datetime import datetime

import pytest
from app.providers.errors import (
    ProviderModelNotFoundError,
    ProviderSelectionAmbiguousError,
    ProviderUnavailableError,
)
from app.providers.registry import ProviderRegistry
from control_schemas import ProviderAvailability


class CatalogProvider:
    def __init__(
        self,
        models: tuple[str, ...] = (),
        error: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.models = models
        self.error = error
        self.delay = delay

    async def list_models(self) -> tuple[str, ...]:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.models


@pytest.mark.asyncio
async def test_auto_selection_uses_exact_installed_model() -> None:
    mock = CatalogProvider(("mock-gpt",))
    ollama = CatalogProvider(("qwen2.5:0.5b", "gemma3:1b"))
    registry = ProviderRegistry(  # type: ignore[arg-type]
        {"mock": mock, "ollama": ollama}
    )

    selection = await registry.select("qwen2.5:0.5b")

    assert selection.name == "ollama"
    assert selection.provider is ollama


@pytest.mark.asyncio
async def test_explicit_selection_rejects_model_missing_from_provider() -> None:
    registry = ProviderRegistry(  # type: ignore[arg-type]
        {"mock": CatalogProvider(("mock-gpt",))}
    )

    with pytest.raises(ProviderModelNotFoundError):
        await registry.select("qwen2.5:0.5b", "mock")


@pytest.mark.asyncio
async def test_auto_selection_rejects_ambiguous_model() -> None:
    registry = ProviderRegistry(  # type: ignore[arg-type]
        {
            "first": CatalogProvider(("shared",)),
            "second": CatalogProvider(("shared",)),
        }
    )

    with pytest.raises(ProviderSelectionAmbiguousError):
        await registry.select("shared")


@pytest.mark.asyncio
async def test_auto_selection_reports_catalog_failure_when_model_is_unknown() -> None:
    registry = ProviderRegistry(  # type: ignore[arg-type]
        {
            "offline": CatalogProvider(error=ProviderUnavailableError()),
            "mock": CatalogProvider(("mock-gpt",)),
        }
    )

    with pytest.raises(ProviderUnavailableError):
        await registry.select("unknown")


@pytest.mark.asyncio
async def test_catalog_reports_each_provider_without_leaking_errors() -> None:
    registry = ProviderRegistry(  # type: ignore[arg-type]
        {
            "ollama": CatalogProvider(("qwen2.5:0.5b",)),
            "offline": CatalogProvider(error=ProviderUnavailableError("secret")),
        }
    )

    catalog = await registry.catalog()

    assert isinstance(catalog.checked_at, datetime)
    assert [provider.name for provider in catalog.providers] == ["offline", "ollama"]
    assert catalog.providers[0].status is ProviderAvailability.UNAVAILABLE
    assert catalog.providers[0].models == []
    assert catalog.providers[1].models == ["qwen2.5:0.5b"]


@pytest.mark.asyncio
async def test_catalog_does_not_hide_programming_errors_as_outages() -> None:
    registry = ProviderRegistry(  # type: ignore[arg-type]
        {"broken": CatalogProvider(error=RuntimeError("implementation defect"))}
    )

    with pytest.raises(RuntimeError, match="implementation defect"):
        await registry.catalog()


@pytest.mark.asyncio
async def test_catalog_timeout_bounds_slow_provider_discovery() -> None:
    registry = ProviderRegistry(  # type: ignore[arg-type]
        {"slow": CatalogProvider(("model",), delay=0.1)},
        catalog_timeout_seconds=0.01,
    )

    catalog = await registry.catalog()

    assert catalog.providers[0].status is ProviderAvailability.UNAVAILABLE
