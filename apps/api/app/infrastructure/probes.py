from typing import Protocol

from control_schemas import DependencyHealth


class DependencyProbe(Protocol):
    name: str

    async def check(self) -> DependencyHealth: ...

    async def close(self) -> None: ...
