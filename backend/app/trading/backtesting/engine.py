"""Backtest engine.

Drives the (frozen) strategy layer over completed Renko bricks and routes the
resulting signals through the reusable execution core. Fill policy (per the
approved refinement): a signal generated on completed brick N executes on the
NEXT completed brick (N+1), avoiding optimistic same-brick execution.

Per-brick loop:
  1. Execute any order pending from the previous brick, at THIS brick's close.
  2. Mark the portfolio to this brick's close (append equity point).
  3. Feed the brick to the strategy; map the signal to the next pending order.

Signal mapping (long-only): BUY -> open long (from flat); EXIT -> close long;
SELL -> ignored (no shorting in T2); HOLD -> nothing. Any order still pending at
the end is cancelled (no next brick = no execution); an open position is
force-closed at the last brick's close so metrics are complete.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

from backend.app.trading.backtesting.metrics import PerformanceMetrics, compute_metrics
from backend.app.trading.costs.brokerage import BrokerageModel
from backend.app.trading.costs.slippage import SlippageModel
from backend.app.trading.execution.executor import Executor, SimulatedExecutor
from backend.app.trading.execution.order import Order, OrderIntent, OrderSide, OrderStatus
from backend.app.trading.execution.position import TradeAttribution
from backend.app.trading.portfolio.portfolio import EquityPoint, Portfolio
from backend.app.trading.signals.models import SignalType
from backend.app.trading.strategy.engine import StrategyEngine
from backend.app.trading.strategy.interfaces import Strategy


@dataclass
class BacktestResult:
    portfolio: Portfolio
    metrics: PerformanceMetrics

    @property
    def trades(self):
        return self.portfolio.trades

    @property
    def equity_curve(self) -> List[EquityPoint]:
        return self.portfolio.equity_curve


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        *,
        starting_capital: float = 100_000.0,
        attribution: Optional[TradeAttribution] = None,
        executor: Optional[Executor] = None,
        slippage: Optional[SlippageModel] = None,
        brokerage: Optional[BrokerageModel] = None,
        position_fraction: float = 0.95,
        fixed_quantity: Optional[float] = None,
        leverage: float = 1.0,
        force_close: bool = True,
    ) -> None:
        if attribution is None:
            attribution = TradeAttribution(strategy_name=getattr(strategy, "name", "unknown"))
        self._strategy_engine = StrategyEngine(strategy)
        self._executor = executor or SimulatedExecutor(slippage=slippage, brokerage=brokerage)
        self.portfolio = Portfolio(starting_capital, attribution=attribution, leverage=leverage)
        self._position_fraction = float(position_fraction)
        self._fixed_quantity = fixed_quantity
        self._force_close = force_close
        self._next_order_id = 0

    # -- order helpers --------------------------------------------------------
    def _new_order_id(self) -> int:
        self._next_order_id += 1
        return self._next_order_id

    def _entry_quantity(self, reference_price: float) -> float:
        if self._fixed_quantity is not None:
            return float(self._fixed_quantity)
        if reference_price <= 0:
            return 0.0
        return (self.portfolio.buying_power * self._position_fraction) / reference_price

    def _order_from_signal(self, signal_type: SignalType, brick: Any) -> Optional[Order]:
        ref = float(brick.close_price)
        ts = brick.created_at
        if signal_type is SignalType.BUY and not self.portfolio.position.is_open:
            qty = self._entry_quantity(ref)
            if qty <= 0:
                return None
            order = Order(self._new_order_id(), OrderSide.BUY, OrderIntent.ENTRY, qty, ref, ts)
            order.reserved = qty * ref
            self.portfolio.reserve(order.reserved)
            self.portfolio.record_order(order)
            return order
        if signal_type is SignalType.EXIT and self.portfolio.position.is_open:
            qty = self.portfolio.position.quantity
            order = Order(self._new_order_id(), OrderSide.SELL, OrderIntent.EXIT, qty, ref, ts)
            self.portfolio.record_order(order)
            return order
        # SELL (no shorting in T2), or signals with no actionable position change.
        return None

    def _execute(self, order: Order, brick: Any, bar_index: int) -> None:
        self._executor.execute(order, reference_price=float(brick.close_price), timestamp=brick.created_at)
        self.portfolio.apply_order(order, bar_index)

    # -- run ------------------------------------------------------------------
    def run(self, bricks: Sequence[Any]) -> BacktestResult:
        self._strategy_engine.start()
        pending: Optional[Order] = None
        last_index = -1
        last_brick = None

        for index, brick in enumerate(bricks):
            # 1. Next-brick fill: execute the order pending from the previous brick.
            if pending is not None:
                self._execute(pending, brick, index)
                pending = None
            # 2. Mark equity at this brick's close.
            self.portfolio.mark(brick.created_at, float(brick.close_price))
            # 3. Strategy consumes the brick; derive the next order (executes next brick).
            signal = self._strategy_engine.process_brick(brick)
            pending = self._order_from_signal(signal.type, brick)
            last_index = index
            last_brick = brick

        # A still-pending order has no next brick to fill against — cancel it.
        if pending is not None:
            self.portfolio.release(pending.reserved)
            pending.cancel()

        # Force-close any open position at the last brick's close.
        if self._force_close and last_brick is not None and self.portfolio.position.is_open:
            close_order = Order(
                self._new_order_id(), OrderSide.SELL, OrderIntent.EXIT,
                self.portfolio.position.quantity, float(last_brick.close_price), last_brick.created_at,
            )
            self.portfolio.record_order(close_order)
            self._execute(close_order, last_brick, last_index)
            self.portfolio.mark(last_brick.created_at, float(last_brick.close_price))

        metrics = compute_metrics(
            self.portfolio.equity_curve,
            self.portfolio.trades,
            self.portfolio.starting_capital,
            total_brokerage=self.portfolio.total_brokerage,
            total_slippage=self.portfolio.total_slippage,
        )
        return BacktestResult(portfolio=self.portfolio, metrics=metrics)
