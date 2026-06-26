import asyncio
from pathlib import Path

from backend.app.events.bus import EventBus
from backend.app.plugins.manager import PluginManager


def test_plugin_manager_lifecycle(tmp_path: Path) -> None:
    plugin_code = """from __future__ import annotations

from backend.app.events.bus import EventBus


class DummyPlugin:
    name = "dummy"

    def __init__(self) -> None:
        self.state = []
        self.event_bus: EventBus | None = None

    async def load(self, event_bus: EventBus | None = None) -> None:
        self.state.append("load")
        self.event_bus = event_bus

    async def start(self) -> None:
        self.state.append("start")

    async def stop(self) -> None:
        self.state.append("stop")

    async def unload(self) -> None:
        self.state.append("unload")
"""
    plugin_file = tmp_path / "dummy_plugin.py"
    plugin_file.write_text(plugin_code, encoding="utf-8")

    event_bus = EventBus()
    manager = PluginManager(tmp_path, event_bus=event_bus)

    async def run() -> None:
        await manager.load()
        plugin = manager.get_plugin("dummy")
        await manager.start()
        await manager.stop()

        assert plugin.state == ["load", "start", "stop"]
        assert plugin.event_bus is event_bus

        await manager.unload()

    asyncio.run(run())

    asyncio.run(run())
