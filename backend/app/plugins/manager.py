from __future__ import annotations

import asyncio
import importlib.util
import inspect
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Optional, Type

from backend.app.chart.registry import ChartRegistry
from backend.app.chart.renko.registry import RenkoRegistry
from backend.app.events.bus import EventBus
from backend.app.plugins.base import PluginInterface


class PluginManager:
    """Manager for plugin discovery and lifecycle operations."""

    def __init__(
        self,
        plugin_directory: Path,
        event_bus: Optional[EventBus] = None,
        chart_registry: Optional[ChartRegistry] = None,
        renko_registry: Optional[RenkoRegistry] = None,
    ) -> None:
        self.plugin_directory = plugin_directory
        self.event_bus = event_bus
        self.chart_registry = chart_registry
        self.renko_registry = renko_registry
        self._plugins: Dict[str, PluginInterface] = {}

    def discover(self) -> List[Path]:
        if not self.plugin_directory.exists():
            raise FileNotFoundError(f"Plugin directory does not exist: {self.plugin_directory}")

        discovered: List[Path] = []
        for child in sorted(self.plugin_directory.iterdir(), key=lambda item: item.name):
            if child.name == "__init__.py":
                continue

            if child.is_file() and child.suffix == ".py":
                discovered.append(child)
            elif child.is_dir() and (child / "__init__.py").exists():
                discovered.append(child)

        return discovered

    async def load(self) -> None:
        for path in self.discover():
            plugin = self._load_plugin(path)
            if plugin.name in self._plugins:
                raise ValueError(f"Plugin with name '{plugin.name}' is already loaded")

            await self._invoke_lifecycle(plugin, "load", self.event_bus)
            await self._register_plugin_charts(plugin)
            await self._register_plugin_renko_engines(plugin)
            self._plugins[plugin.name] = plugin

    async def _register_plugin_charts(self, plugin: PluginInterface) -> None:
        if self.chart_registry is None:
            return

        register_method = getattr(plugin, "register_charts", None)
        if register_method is None or not callable(register_method):
            return

        result = register_method(self.chart_registry)
        if inspect.isawaitable(result):
            await result

    async def _register_plugin_renko_engines(self, plugin: PluginInterface) -> None:
        if self.renko_registry is None:
            return

        register_method = getattr(plugin, "register_renko_engines", None)
        if register_method is None or not callable(register_method):
            return

        result = register_method(self.renko_registry)
        if inspect.isawaitable(result):
            await result

    async def start(self) -> None:
        self._ensure_plugins_loaded()
        for plugin in self._plugins.values():
            await self._invoke_lifecycle(plugin, "start")

    async def stop(self) -> None:
        self._ensure_plugins_loaded()
        for plugin in self._plugins.values():
            await self._invoke_lifecycle(plugin, "stop")

    async def unload(self) -> None:
        self._ensure_plugins_loaded()
        for plugin in self._plugins.values():
            await self._invoke_lifecycle(plugin, "unload")
        self._plugins.clear()

    def get_plugin(self, name: str) -> PluginInterface:
        if name not in self._plugins:
            raise KeyError(f"Plugin not loaded: {name}")
        return self._plugins[name]

    def _load_plugin(self, path: Path) -> PluginInterface:
        module = self._import_plugin_module(path)
        plugin_class = self._find_plugin_class(module)
        return plugin_class()

    def _import_plugin_module(self, path: Path) -> ModuleType:
        if path.is_dir():
            module_path = path / "__init__.py"
            module_name = f"plugin_{path.name}"
        else:
            module_path = path
            module_name = f"plugin_{path.stem}"

        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to import plugin module from {module_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _find_plugin_class(self, module: ModuleType) -> Type[PluginInterface]:
        for obj in vars(module).values():
            if not inspect.isclass(obj):
                continue
            if obj is PluginInterface:
                continue
            if obj.__module__ != module.__name__:
                continue
            if self._is_valid_plugin_class(obj):
                return obj

        raise ValueError(f"No valid plugin class found in module {module.__name__}")

    def _is_valid_plugin_class(self, candidate: Type[object]) -> bool:
        if not hasattr(candidate, "name") or not isinstance(getattr(candidate, "name"), str):
            return False

        required_methods = ["load", "start", "stop", "unload"]
        for method_name in required_methods:
            method = getattr(candidate, method_name, None)
            if method is None or not asyncio.iscoroutinefunction(method):
                return False

        return True

    async def _invoke_lifecycle(self, plugin: PluginInterface, method_name: str, *args: object) -> None:
        method = getattr(plugin, method_name)
        await method(*args)

    def _ensure_plugins_loaded(self) -> None:
        if not self._plugins:
            raise RuntimeError("No plugins have been loaded")
