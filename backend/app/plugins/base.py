from __future__ import annotations

from typing import Optional, Protocol, TYPE_CHECKING, runtime_checkable

if TYPE_CHECKING:
    from backend.app.events.bus import EventBus


@runtime_checkable
class PluginInterface(Protocol):
    """Plugin contract for lifecycle-managed plugins."""

    name: str

    async def load(self, event_bus: Optional["EventBus"] = None) -> None:
        ...

    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    async def unload(self) -> None:
        ...
