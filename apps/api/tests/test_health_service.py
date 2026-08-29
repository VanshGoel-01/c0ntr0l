import pytest
from app.services.health import HealthService
from control_schemas import DependencyHealth, DependencyStatus, HealthStatus


class FakeProbe:
    def __init__(self, name: str, status: DependencyStatus) -> None:
        self.name = name
        self._status = status
        self.closed = False

    async def check(self) -> DependencyHealth:
        return DependencyHealth(status=self._status)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_health_is_ok_when_all_dependencies_are_healthy() -> None:
    service = HealthService(
        version="test",
        probes=[
            FakeProbe("postgres", DependencyStatus.HEALTHY),
            FakeProbe("redis", DependencyStatus.HEALTHY),
        ],
    )

    result = await service.check()

    assert result.status is HealthStatus.OK
    assert set(result.dependencies) == {"postgres", "redis"}


@pytest.mark.asyncio
async def test_health_is_degraded_when_a_dependency_is_unhealthy() -> None:
    service = HealthService(
        version="test",
        probes=[FakeProbe("postgres", DependencyStatus.UNHEALTHY)],
    )

    result = await service.check()

    assert result.status is HealthStatus.DEGRADED


def test_duplicate_probe_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        HealthService(
            version="test",
            probes=[
                FakeProbe("postgres", DependencyStatus.HEALTHY),
                FakeProbe("postgres", DependencyStatus.HEALTHY),
            ],
        )
