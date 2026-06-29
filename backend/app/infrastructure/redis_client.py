"""Redis client infrastructure adapter."""

from __future__ import annotations

from typing import Any

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover - exercised when deployment extra is absent
    redis = None  # type: ignore[assignment]


class RedisUnavailableError(RuntimeError):
    """Raised when Redis is requested but the redis package is unavailable."""


class RedisClient:
    """Lazy Redis adapter used by infrastructure and health checks."""

    def __init__(self, config) -> None:
        self._config = config
        self._client: Any = None
        self._connected = False
        self._last_error: str | None = None

    async def connect(self) -> None:
        """Connect to Redis when the optional deployment dependency is installed."""
        if redis is None:
            self._connected = False
            self._last_error = "redis package is not installed"
            return
        self._client = redis.from_url(
            f"redis://{self._config.redis_host}:{self._config.redis_port}/{self._config.redis_db}",
            encoding="utf-8",
            decode_responses=True,
        )
        try:
            await self._client.ping()
            self._connected = True
            self._last_error = None
        except Exception as exc:  # pylint: disable=broad-except
            self._connected = False
            self._last_error = str(exc)

    @property
    def client(self):
        """Return the raw Redis client, or None when unavailable."""
        return self._client

    @property
    def is_connected(self) -> bool:
        """Return whether Redis was connected successfully."""
        return self._connected

    @property
    def last_error(self) -> str | None:
        """Return the last connection or health-check error."""
        return self._last_error

    async def health(self) -> dict[str, object]:
        """Return Redis health without raising when Redis is unavailable."""
        if self._client is None:
            return {"status": "unavailable", "connected": False, "error": self._last_error}
        try:
            ok = await self._client.ping()
            self._connected = bool(ok)
            self._last_error = None
        except Exception as exc:  # pylint: disable=broad-except
            self._connected = False
            self._last_error = str(exc)
        return {"status": "ok" if self._connected else "error", "connected": self._connected, "error": self._last_error}

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            await self._client.close()
        self._client = None
        self._connected = False
