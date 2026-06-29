"""Position synchronization and tracking.

Maintains a local view of positions synchronized with the broker/exchange.
Handles position reconciliation and updates from broker-reported positions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from backend.app.trading.broker.interfaces import BrokerAdapter, Position as BrokerPosition
from backend.app.trading.execution.order import Fill, OrderSide


@dataclass
class PositionRecord:
    """Internal position representation."""
    symbol: str
    side: str  # "long" or "short"
    quantity: float
    average_entry_price: float
    current_price: Optional[float] = None
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    opened_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    broker_position_id: Optional[str] = None

    def update_price(self, price: float) -> None:
        """Update current price and recalculate unrealized P&L."""
        self.current_price = price
        if self.side == "long":
            self.unrealized_pnl = (price - self.average_entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.average_entry_price - price) * self.quantity
        self.updated_at = datetime.utcnow()

    def apply_fill(self, fill: Fill) -> None:
        """Apply a fill to update position."""
        if self.side == "long":
            # Update average price for additional buys
            if fill.side == OrderSide.BUY:
                total_cost = (self.quantity * self.average_entry_price) + (fill.quantity * fill.price)
                self.quantity += fill.quantity
                self.average_entry_price = total_cost / self.quantity
            else:
                # Selling reduces position
                self.realized_pnl += (fill.price - self.average_entry_price) * fill.quantity
                self.quantity -= fill.quantity
        else:
            # Short position
            if fill.side == OrderSide.SELL:
                total_cost = (self.quantity * self.average_entry_price) + (fill.quantity * fill.price)
                self.quantity += fill.quantity
                self.average_entry_price = total_cost / self.quantity
            else:
                # Buying to cover
                self.realized_pnl += (self.average_entry_price - fill.price) * fill.quantity
                self.quantity -= fill.quantity

        # Clean up if position closed
        if abs(self.quantity) < 1e-9:
            self.quantity = 0.0

        self.updated_at = datetime.utcnow()


class PositionSynchronizer:
    """Synchronizes local positions with broker-reported positions.

    Periodically fetches positions from the broker and reconciles differences.
    """

    def __init__(self, broker: BrokerAdapter) -> None:
        """Initialize the synchronizer.

        Args:
            broker: Connected broker adapter
        """
        self._broker = broker
        self._positions: Dict[str, PositionRecord] = {}
        self._last_sync: Optional[datetime] = None

    @property
    def positions(self) -> Dict[str, PositionRecord]:
        """Get all tracked positions."""
        return self._positions

    def get_position(self, symbol: str) -> Optional[PositionRecord]:
        """Get position for a symbol."""
        return self._positions.get(symbol)

    async def sync(self) -> List[PositionRecord]:
        """Synchronize positions with broker.

        Fetches current positions from broker and updates local state.
        Returns the list of current positions after sync.
        """
        try:
            broker_positions = await self._broker.get_positions()
            self._reconcile(broker_positions)
            self._last_sync = datetime.utcnow()
            return list(self._positions.values())
        except Exception as exc:
            # Log error but don't crash
            return list(self._positions.values())

    async def sync_symbol(self, symbol: str) -> Optional[PositionRecord]:
        """Synchronize a specific symbol's position."""
        try:
            broker_positions = await self._broker.get_positions(symbol=symbol)
            for bp in broker_positions:
                if bp.symbol == symbol and bp.quantity > 0:
                    self._update_from_broker(bp)
                    return self._positions.get(symbol)
        except Exception:
            pass
        return self._positions.get(symbol)

    def apply_fill(self, fill: Fill, symbol: str) -> None:
        """Apply a fill to local position tracking.

        Args:
            fill: Executed fill
            symbol: Trading symbol
        """
        if symbol not in self._positions:
            # Create new position
            side = "long" if fill.side == OrderSide.BUY else "short"
            self._positions[symbol] = PositionRecord(
                symbol=symbol,
                side=side,
                quantity=fill.quantity,
                average_entry_price=fill.price,
                opened_at=fill.timestamp,
            )
        else:
            # Update existing position
            self._positions[symbol].apply_fill(fill)

        # Clean up closed positions
        if self._positions[symbol].quantity == 0:
            del self._positions[symbol]

    def update_price(self, symbol: str, price: float) -> None:
        """Update current price for a position."""
        if symbol in self._positions:
            self._positions[symbol].update_price(price)

    def get_unrealized_pnl(self, symbol: str) -> float:
        """Get unrealized P&L for a symbol."""
        pos = self._positions.get(symbol)
        return pos.unrealized_pnl if pos else 0.0

    def get_total_exposure(self) -> float:
        """Get total position exposure (sum of absolute position values)."""
        total = 0.0
        for pos in self._positions.values():
            if pos.current_price is not None:
                total += abs(pos.quantity * pos.current_price)
        return total

    def _reconcile(self, broker_positions: List[BrokerPosition]) -> None:
        """Reconcile broker positions with local state."""
        broker_symbols = set()

        for bp in broker_positions:
            if bp.quantity <= 0:
                # Skip empty positions
                continue

            broker_symbols.add(bp.symbol)
            self._update_from_broker(bp)

        # Remove positions that no longer exist on broker
        for symbol in list(self._positions.keys()):
            if symbol not in broker_symbols:
                del self._positions[symbol]

    def _update_from_broker(self, bp: BrokerPosition) -> None:
        """Update local position from broker position."""
        if bp.symbol in self._positions:
            # Update existing
            local = self._positions[bp.symbol]
            local.quantity = bp.quantity
            local.average_entry_price = bp.average_entry_price
            local.current_price = bp.current_price
            local.unrealized_pnl = bp.unrealized_pnl or 0.0
            local.realized_pnl = bp.realized_pnl
            local.updated_at = datetime.utcnow()
        else:
            # Create new
            self._positions[bp.symbol] = PositionRecord(
                symbol=bp.symbol,
                side=bp.side,
                quantity=bp.quantity,
                average_entry_price=bp.average_entry_price,
                current_price=bp.current_price,
                unrealized_pnl=bp.unrealized_pnl or 0.0,
                realized_pnl=bp.realized_pnl,
                broker_position_id=bp.symbol,  # Use symbol as ID for now
            )

    @property
    def last_sync(self) -> Optional[datetime]:
        """Get timestamp of last successful sync."""
        return self._last_sync

    @property
    def position_count(self) -> int:
        """Get number of open positions."""
        return len(self._positions)