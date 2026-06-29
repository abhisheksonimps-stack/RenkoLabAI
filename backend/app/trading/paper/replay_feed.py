"""Replay integration — drive a paper session from replayed market data.

The replay engine (:mod:`backend.app.engines.replay`) publishes ``TickReplayed``
and ``CandleReplayed`` events on the shared ``EventBus`` as it walks historical
data. :class:`ReplayMarketFeed` subscribes to those events, reconstructs the
:class:`Tick` / :class:`Candle`, and forwards it to a
:class:`PaperTradingSession`. This is pure composition over the existing bus —
the replay engine is neither imported into nor modified by the paper layer.
"""

from __future__ import annotations

from backend.app.domain.market_data.models import Candle, Tick
from backend.app.engines.replay.events import CandleReplayed, TickReplayed
from backend.app.events.base import BaseEvent
from backend.app.events.bus import EventBus
from backend.app.trading.paper.session import PaperTradingSession


class ReplayMarketFeed:
    """Subscribes replayed ticks/candles into a paper-trading session."""

    def __init__(self, session: PaperTradingSession, event_bus: EventBus) -> None:
        self._session = session
        self._event_bus = event_bus

    def attach(self) -> None:
        """Begin forwarding replayed market data to the session."""
        self._event_bus.subscribe(TickReplayed, self._handle_tick)
        self._event_bus.subscribe(CandleReplayed, self._handle_candle)

    def detach(self) -> None:
        """Stop forwarding replayed market data."""
        self._event_bus.unsubscribe(TickReplayed, self._handle_tick)
        self._event_bus.unsubscribe(CandleReplayed, self._handle_candle)

    async def _handle_tick(self, event: BaseEvent) -> None:
        data = event.payload.get("tick")
        if not data:
            return
        tick = Tick(**data)
        if tick.symbol == self._session.symbol:
            await self._session.on_tick(tick)

    async def _handle_candle(self, event: BaseEvent) -> None:
        data = event.payload.get("candle")
        if not data:
            return
        candle = Candle(**data)
        if candle.symbol == self._session.symbol:
            await self._session.on_candle(candle)
