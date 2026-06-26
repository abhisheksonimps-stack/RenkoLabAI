from __future__ import annotations

from typing import Dict, Optional

from backend.app.chart.renko.interfaces import RenkoEngine


class RenkoRegistry:
    def __init__(self) -> None:
        self._engines: Dict[str, RenkoEngine] = {}

    def register(self, engine_type: str, engine: RenkoEngine) -> None:
        if engine_type in self._engines:
            raise ValueError(f"Engine type already registered: {engine_type}")
        self._engines[engine_type] = engine

    def get(self, engine_type: str) -> RenkoEngine:
        if engine_type not in self._engines:
            raise KeyError(f"Engine type not registered: {engine_type}")
        return self._engines[engine_type]

    def exists(self, engine_type: str) -> bool:
        return engine_type in self._engines

    def all(self) -> list[RenkoEngine]:
        return list(self._engines.values())

    def lookup(self, configuration: "BrickConfiguration") -> RenkoEngine:
        engine_type = configuration.brick_type.value
        return self.get(engine_type)
