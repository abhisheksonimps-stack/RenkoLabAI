import redis.asyncio as redis
from backend.app.configuration.loader import settings


class RedisClient:
    def __init__(self, config) -> None:
        self._config = config
        self._client = None

    async def connect(self) -> None:
        self._client = redis.from_url(
            f"redis://{self._config.redis_host}:{self._config.redis_port}/{self._config.redis_db}",
            encoding="utf-8",
            decode_responses=True,
        )

    @property
    def client(self):
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
