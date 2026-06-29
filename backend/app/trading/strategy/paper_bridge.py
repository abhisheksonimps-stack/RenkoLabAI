"""Strategy-to-paper-trading integration."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain.market_data.models import Candle, Tick
from backend.app.trading.execution.order import Order, OrderIntent, OrderSide
from backend.app.trading.paper.session import PaperTradingSession
from backend.app.trading.signals.models import Signal, SignalType
from backend.app.trading.strategy.interfaces import Strategy, StrategyContext
from backend.app.trading.strategy.sizing import PositionSizer, PositionSizingContext


@dataclass(frozen=True)
class PaperStrategyDecision:
    """Result of routing one strategy signal to paper trading."""

    signal: Signal
    order: Order | None


class PaperStrategyBridge:
    """Run a Strategy against paper-session market data and route orders."""

    def __init__(self, strategy: Strategy, session: PaperTradingSession, sizer: PositionSizer) -> None:
        self.strategy = strategy
        self.session = session
        self.sizer = sizer
        self.strategy.initialize()

    async def on_candle(self, candle: Candle) -> PaperStrategyDecision:
        """Process a candle and submit an order when signal is actionable."""
        await self.session.on_candle(candle)
        context = StrategyContext(
            symbol=candle.symbol,
            current_price=float(candle.close),
            cash=self.session.portfolio.cash,
            equity=self.session.portfolio.equity(float(candle.close)),
            position_quantity=self.session.portfolio.position.quantity,
            open_positions=1 if self.session.portfolio.position.is_open else 0,
        )
        signal = self.strategy.on_market_data(_market_bar_from_candle(candle), context).signal
        order = await self._route(signal, context)
        return PaperStrategyDecision(signal=signal, order=order)

    async def on_tick(self, tick: Tick) -> PaperStrategyDecision:
        """Process a tick and submit an order when signal is actionable."""
        await self.session.on_tick(tick)
        context = StrategyContext(
            symbol=tick.symbol,
            tick={"price": float(tick.price)},
            current_price=float(tick.price),
            cash=self.session.portfolio.cash,
            equity=self.session.portfolio.equity(float(tick.price)),
            position_quantity=self.session.portfolio.position.quantity,
            open_positions=1 if self.session.portfolio.position.is_open else 0,
        )
        signal = self.strategy.on_tick({"price": float(tick.price)}, context).signal
        order = await self._route(signal, context)
        return PaperStrategyDecision(signal=signal, order=order)

    async def _route(self, signal: Signal, context: StrategyContext) -> Order | None:
        if signal.type is SignalType.HOLD:
            return None
        price = context.current_price
        equity = context.equity
        if price is None or equity is None:
            return None

        if signal.type is SignalType.BUY and not self.session.portfolio.position.is_open:
            quantity = self.sizer.size(PositionSizingContext(equity=equity, price=price))
            if quantity <= 0:
                return None
            return await self.session.submit_market(OrderSide.BUY, quantity, intent=OrderIntent.ENTRY)

        if signal.type is SignalType.EXIT and self.session.portfolio.position.is_open:
            quantity = self.session.portfolio.position.quantity
            if quantity <= 0:
                return None
            return await self.session.submit_market(OrderSide.SELL, quantity, intent=OrderIntent.EXIT)

        return None


def _market_bar_from_candle(candle: Candle):
    from backend.app.marketdata.models import MarketBar

    return MarketBar.create(
        symbol=candle.symbol,
        timestamp=candle.start_time,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
        interval=candle.timeframe.value if hasattr(candle.timeframe, "value") else str(candle.timeframe),
        source="paper_strategy_bridge",
    )


__all__ = ["PaperStrategyBridge", "PaperStrategyDecision"]
