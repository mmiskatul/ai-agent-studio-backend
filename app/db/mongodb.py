from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings


class MongoDatabase:
    """Singleton-style MongoDB connection manager owned by the app lifecycle."""

    def __init__(self) -> None:
        self._client: AsyncIOMotorClient | None = None

    async def connect(self) -> None:
        if self._client is None:
            self._client = AsyncIOMotorClient(settings.mongodb_uri)
            await self._client.admin.command("ping")

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._client is None:
            raise RuntimeError("MongoDB client is not connected")
        return self._client[settings.mongodb_db_name]


mongo_database = MongoDatabase()
