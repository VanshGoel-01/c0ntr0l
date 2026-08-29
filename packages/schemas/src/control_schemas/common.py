from enum import StrEnum


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"


class DependencyStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
