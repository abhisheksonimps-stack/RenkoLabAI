"""Portfolio — single source of truth for cash, capital, positions, and equity.

Mutated only by fills (apply_order) and marks (mark). Tracks, in addition to
cash and holdings:
  * available_capital = cash - reserved
  * reserved_capital  = capital earmarked for pending orders
  * buying_power      = available_capital * leverage
Backward compatible: leverage defaults to 1.0, so buying_power == available
capital == free cash unless leverage is configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from backend.app.trading.execution.order import Order, OrderSide
from backend.app.trading.execution.position import Position, Trade, TradeAttribution


@dataclass(frozen=True)
class EquityPoint:
    timestamp: datetime
    equity: float


class Portfolio:
    def __init__(self, starting_capital: float,
                 attribution: Optional[TradeAttribution] = None,
                 leverage: float = 1.0) -> None:
        if starting_capital <= 0:
            raise ValueError("starting_capital must be positive")
        if leverage <= 0:
            raise ValueError("leverage must be positive")
        self.starting_capital = float(starting_capital)
        self.cash = float(starting_capital)
        self.reserved = 0.0
        self.leverage = float(leverage)
        self.position = Position(attribution)
        self.trades: List[Trade] = []
        self.orders: List[Order] = []
        self.equity_curve: List[EquityPoint] = []
        self.total_brokerage = 0.0
        self.total_slippage = 0.0

    # -- capital views --------------------------------------------------------
    @property
    def available_capital(self) -> float:
        return self.cash - self.reserved

    @property
    def buying_power(self) -> float:
        return self.available_capital * self.leverage

    def reserve(self, amount: float) -> None:
        self.reserved += max(0.0, float(amount))

    def release(self, amount: float) -> None:
        self.reserved = max(0.0, self.reserved - max(0.0, float(amount)))

    # -- mutation -------------------------------------------------------------
    def record_order(self, order: Order) -> None:
        self.orders.append(order)

    def apply_order(self, order: Order, bar_index: int) -> Optional[Trade]:
        # Always release any reservation tied to a buy order, whether it filled,
        # was rejected by the executor, or fails the cash check below.
        if order.side is OrderSide.BUY:
            self.release(order.reserved)

        fill = order.fill
        if fill is None:  # executor rejected (no price)
            return None

        if order.side is OrderSide.BUY:
            total_cost = fill.price * fill.quantity + fill.cost
            if total_cost > self.cash + 1e-9:
                order.reject("insufficient cash")
                return None
            self.cash -= total_cost
            self.total_brokerage += fill.cost
            self.total_slippage += fill.slippage
            self.position.open_long(fill.price, fill.quantity, fill.cost, fill.timestamp, bar_index)
            return None

        # SELL / EXIT -> close (long-only).
        proceeds = fill.price * fill.quantity - fill.cost
        self.cash += proceeds
        self.total_brokerage += fill.cost
        self.total_slippage += fill.slippage
        trade = self.position.close(fill.price, fill.cost, fill.timestamp, bar_index)
        if trade is not None:
            self.trades.append(trade)
        return trade

    def mark(self, timestamp: datetime, price: float) -> float:
        equity = self.equity(price)
        self.equity_curve.append(EquityPoint(timestamp, equity))
        return equity

    def equity(self, price: float) -> float:
        return self.cash + self.position.market_value(price)
