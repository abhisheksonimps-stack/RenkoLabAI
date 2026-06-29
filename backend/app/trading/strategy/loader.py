"""Strategy auto-discovery loader."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from types import ModuleType
from typing import Iterable

from backend.app.trading.strategy.interfaces import Strategy
from backend.app.trading.strategy.registry import StrategyRegistry, register_builtin_strategies


def iter_strategy_classes(module: ModuleType) -> tuple[type[Strategy], ...]:
    """Return concrete Strategy subclasses declared in ``module``."""
    classes: list[type[Strategy]] = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj is Strategy:
            continue
        if not issubclass(obj, Strategy):
            continue
        if inspect.isabstract(obj):
            continue
        if obj.__module__ != module.__name__:
            continue
        classes.append(obj)
    return tuple(classes)


class StrategyLoader:
    """Discover and register Strategy subclasses from Python packages."""

    def __init__(self, package: str = "backend.app.trading.strategy") -> None:
        self.package = package

    def discover(self, module_names: Iterable[str] | None = None) -> StrategyRegistry:
        """Discover strategies and return a populated registry."""
        registry = register_builtin_strategies(StrategyRegistry())
        names = tuple(module_names) if module_names is not None else self._package_modules()
        for module_name in names:
            module = importlib.import_module(module_name)
            for strategy_cls in iter_strategy_classes(module):
                registry.register_class(strategy_cls)
        return registry

    def _package_modules(self) -> tuple[str, ...]:
        package_module = importlib.import_module(self.package)
        package_paths = getattr(package_module, "__path__", None)
        if package_paths is None:
            return (self.package,)
        ignored = {"interfaces", "registry", "factory", "engine", "loader", "risk", "sizing", "paper_bridge"}
        modules: list[str] = []
        for module_info in pkgutil.iter_modules(package_paths, prefix=f"{self.package}."):
            short_name = module_info.name.rsplit(".", 1)[-1]
            if short_name.startswith("_") or short_name in ignored:
                continue
            modules.append(module_info.name)
        return tuple(sorted(modules))


__all__ = ["StrategyLoader", "iter_strategy_classes"]
