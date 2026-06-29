"""Production live runtime orchestrator."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable

from backend.app.events.bridge import EventSystemBridge
from backend.app.events.bus import EventBus
from backend.app.marketdata.streaming.dispatcher import EventDispatcher
from backend.app.marketdata.streaming.events import TickEvent
from backend.app.marketdata.streaming.manager import StreamingManager
from backend.app.trading.live_pipeline import LiveTradingPipeline
from backend.app.trading.oms.engine import OMS


@dataclass(frozen=True)
class RuntimeHealth:
    running: bool
    streaming: dict[str, object]
    event_bridge: dict[str, object]
    oms_active_orders: int
    portfolio_ticks: int


class LiveRuntimeOrchestrator:
    """Coordinate streaming, dispatcher, strategy, OMS, broker, portfolio and analytics."""

    def __init__(
        self,
        *,
        streaming_manager: StreamingManager,
        live_pipeline: LiveTradingPipeline,
        oms: OMS,
        event_bus: EventBus | None = None,
        dispatcher: EventDispatcher | None = None,
    ) -> None:
        self._streaming_manager = streaming_manager
        self._live_pipeline = live_pipeline
        self._oms = oms
        self._event_bus = event_bus or EventBus()
        self._dispatcher = dispatcher or streaming_manager.dispatcher
        self._bridge = EventSystemBridge(self._event_bus, self._dispatcher)
        self._running = False
        self._lock = asyncio.Lock()

    @property
    def live_pipeline(self) -> LiveTradingPipeline:
        return self._live_pipeline

    async def start(self, symbols: Iterable[str] = ()) -> None:
        async with self._lock:
            if self._running:
                return
            self._dispatcher.subscribe(TickEvent, self._live_pipeline.on_event)
            for symbol in symbols:
                for stream in self._streaming_manager.streams.values():
                    await stream.subscribe(symbol)
            await self._bridge.start()
            await self._streaming_manager.start()
            self._running = True

    async def stop(self) -> None:
        async with self._lock:
            if not self._running:
                return
            self._dispatcher.unsubscribe(TickEvent, self._live_pipeline.on_event)
            await self._streaming_manager.stop()
            await self._bridge.stop()
            self._running = False

    async def recover(self) -> None:
        await self._oms.recover()
        if self._oms.position_synchronizer is not None:
            await self._oms.position_synchronizer.sync()

    async def health(self) -> RuntimeHealth:
        return RuntimeHealth(
            running=self._running,
            streaming=await self._streaming_manager.health(),
            event_bridge=await self._bridge.health(),
            oms_active_orders=len(self._oms.order_manager.get_active_orders()),
            portfolio_ticks=self._live_pipeline.processed_ticks,
        )


__all__ = ["LiveRuntimeOrchestrator", "RuntimeHealth"]
