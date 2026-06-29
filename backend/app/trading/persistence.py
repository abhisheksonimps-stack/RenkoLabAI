"""Durable trading runtime persistence adapters."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from backend.app.trading.execution.order import Fill, Order
from backend.app.trading.oms.engine import RiskDecision
from backend.app.trading.portfolio.live_snapshot import LivePortfolioSnapshot


class TradingPersistencePort(ABC):
    """Port for writing live-trading runtime state."""

    @abstractmethod
    async def save_order(self, order: Order) -> None:
        """Persist one OMS order."""

    @abstractmethod
    async def save_fill(self, order: Order) -> None:
        """Persist an order fill when present."""

    @abstractmethod
    async def save_risk_decision(self, decision: RiskDecision) -> None:
        """Persist one pre-execution risk decision."""

    @abstractmethod
    async def save_portfolio_snapshot(self, snapshot: LivePortfolioSnapshot) -> None:
        """Persist a live portfolio snapshot."""

    @abstractmethod
    async def save_analytics_snapshot(self, payload: dict[str, Any]) -> None:
        """Persist analytics/reporting state."""

    @abstractmethod
    async def save_broker_sync_state(self, payload: dict[str, Any]) -> None:
        """Persist broker synchronization state."""


@dataclass(frozen=True)
class TradingPersistenceRecord:
    """Append-only persistence record."""

    record_type: str
    payload: dict[str, Any]
    recorded_at: datetime = field(default_factory=datetime.utcnow)


class NullTradingPersistence(TradingPersistencePort):
    """No-op persistence adapter used only when persistence is intentionally disabled."""

    async def save_order(self, order: Order) -> None:
        return None

    async def save_fill(self, order: Order) -> None:
        return None

    async def save_risk_decision(self, decision: RiskDecision) -> None:
        return None

    async def save_portfolio_snapshot(self, snapshot: LivePortfolioSnapshot) -> None:
        return None

    async def save_analytics_snapshot(self, payload: dict[str, Any]) -> None:
        return None

    async def save_broker_sync_state(self, payload: dict[str, Any]) -> None:
        return None


class JsonlTradingPersistence(TradingPersistencePort):
    """Append-only JSONL persistence for live runtime state and recovery snapshots."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

    async def save_order(self, order: Order) -> None:
        await self._append("orders", self._serialize_order(order))

    async def save_fill(self, order: Order) -> None:
        if order.fill is not None:
            await self._append("fills", {"order_id": order.order_id, "broker_order_id": order.broker_order_id, "fill": self._serialize(order.fill)})

    async def save_risk_decision(self, decision: RiskDecision) -> None:
        await self._append("risk_decisions", self._serialize(decision))

    async def save_portfolio_snapshot(self, snapshot: LivePortfolioSnapshot) -> None:
        await self._append("portfolio_snapshots", snapshot.to_dict())

    async def save_analytics_snapshot(self, payload: dict[str, Any]) -> None:
        await self._append("analytics_snapshots", payload)

    async def save_broker_sync_state(self, payload: dict[str, Any]) -> None:
        await self._append("broker_sync_state", payload)

    def load_records(self, name: str) -> list[TradingPersistenceRecord]:
        path = self._path(name)
        if not path.exists():
            return []
        records: list[TradingPersistenceRecord] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            records.append(
                TradingPersistenceRecord(
                    record_type=str(data["record_type"]),
                    payload=dict(data["payload"]),
                    recorded_at=datetime.fromisoformat(data["recorded_at"]),
                )
            )
        return records

    async def _append(self, name: str, payload: dict[str, Any]) -> None:
        record = TradingPersistenceRecord(record_type=name, payload=payload)
        with self._path(name).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._serialize(record), sort_keys=True) + "\n")

    def _path(self, name: str) -> Path:
        safe_name = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in name)
        return self._directory / f"{safe_name}.jsonl"

    @classmethod
    def _serialize_order(cls, order: Order) -> dict[str, Any]:
        payload = cls._serialize(order)
        if order.fill is not None:
            payload["fill"] = cls._serialize(order.fill)
        return payload

    @classmethod
    def _serialize(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return {key: cls._serialize(item) for key, item in asdict(value).items()}
        if isinstance(value, dict):
            return {str(key): cls._serialize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._serialize(item) for item in value]
        return value


__all__ = [
    "JsonlTradingPersistence",
    "NullTradingPersistence",
    "TradingPersistencePort",
    "TradingPersistenceRecord",
]
