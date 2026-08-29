from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine


class Database:
    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
        )

    def connect(self) -> AsyncConnection:
        return self._engine.connect()

    def begin(self):  # type: ignore[no-untyped-def]
        return self._engine.begin()

    async def close(self) -> None:
        await self._engine.dispose()
