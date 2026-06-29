"""Production health checks for live trading runtime components."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Mapping

HealthCheck = Callable[[], Awaitable[Mapping[str, object]]]


@dataclass(frozen=True)
class ComponentHealth:
    name: str
    status: str
    details: Mapping[str, object] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=datetime.utcnow)


class ProductionHealthRegistry:
    """Async health-check registry with component isolation."""

    def __init__(self) -> None:
        self._checks: dict[str, HealthCheck] = {}

    def register(self, name: str, check: HealthCheck) -> None:
        if not name.strip():
            raise ValueError("health check name cannot be blank")
        self._checks[name] = check

    def unregister(self, name: str) -> None:
        self._checks.pop(name, None)

    async def run(self) -> dict[str, ComponentHealth]:
        results: dict[str, ComponentHealth] = {}
        for name, check in self._checks.items():
            try:
                details = dict(await check())
                status = str(details.get("status", "ok"))
            except Exception as exc:  # pylint: disable=broad-except
                status = "error"
                details = {"status": "error", "error": str(exc)}
            results[name] = ComponentHealth(name=name, status=status, details=details)
        return results

    async def summary(self) -> dict[str, object]:
        results = await self.run()
        status = "ok" if all(item.status == "ok" for item in results.values()) else "degraded"
        return {
            "status": status,
            "components": {name: {"status": item.status, "details": dict(item.details)} for name, item in results.items()},
        }


__all__ = ["ComponentHealth", "ProductionHealthRegistry"]
