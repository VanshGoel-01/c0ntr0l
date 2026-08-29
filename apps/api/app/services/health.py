import asyncio
from collections.abc import Sequence

from control_schemas import (
    DependencyHealth,
    DependencyStatus,
    HealthResponse,
    HealthStatus,
)

from app.infrastructure.probes import DependencyProbe


class HealthService:
    def __init__(self, version: str, probes: Sequence[DependencyProbe]) -> None:
        names = [probe.name for probe in probes]
        if len(names) != len(set(names)):
            raise ValueError("Dependency probe names must be unique")
        self._version = version
        self._probes = tuple(probes)

    async def check(self) -> HealthResponse:
        results = await asyncio.gather(*(probe.check() for probe in self._probes))
        dependencies: dict[str, DependencyHealth] = {
            probe.name: result
            for probe, result in zip(self._probes, results, strict=True)
        }
        is_healthy = all(
            dependency.status is DependencyStatus.HEALTHY
            for dependency in dependencies.values()
        )
        return HealthResponse(
            status=HealthStatus.OK if is_healthy else HealthStatus.DEGRADED,
            version=self._version,
            dependencies=dependencies,
        )

    async def close(self) -> None:
        await asyncio.gather(
            *(probe.close() for probe in self._probes),
            return_exceptions=True,
        )
