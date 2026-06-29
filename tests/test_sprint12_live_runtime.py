from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from backend.app.marketdata.streaming.events import TickEvent
from backend.app.trading.broker.interfaces import (
    AccountInfo,
    BrokerAdapter,
    BrokerOrder,
    OrderSide as BrokerSide,
    OrderStatus as BrokerStatus,
    OrderType,
    Position,
    TimeInForce,
)
from backend.app.trading.broker.live_executor import LiveExecutor
from backend.app.trading.live_pipeline import LiveTradingPipeline
from backend.app.trading.oms.engine import OMS, OMSConfig
from backend.app.trading.oms.positions import PositionSynchronizer
from backend.app.trading.persistence import JsonlTradingPersistence
from backend.app.trading.portfolio.portfolio import Portfolio
from backend.app.trading.signals.models import Signal, SignalType
from backend.app.trading.strategy.engine import StrategyEngine
from backend.app.trading.strategy.interfaces import Strategy, StrategyContext, StrategyResult


class RuntimeStrategy(Strategy):
    name = "runtime_strategy"

    def __init__(self) -> None:
        self._signal = Signal.hold()
        self.fill_count = 0
        self.closed_count = 0

    def initialize(self) -> None:
        self._signal = Signal.hold()

    def on_brick(self, brick: Any) -> None:
        self._signal = Signal.hold()

    def on_tick(self, tick, context: StrategyContext | None = None) -> StrategyResult:
        if context and context.position_quantity > 0:
            self._signal = Signal(SignalType.SELL, price=float(tick["price"]))
        else:
            self._signal = Signal(SignalType.BUY, price=float(tick["price"]))
        return StrategyResult(signal=self._signal, context=context)

    def on_order_fill(self, fill, context: StrategyContext | None = None) -> StrategyResult:
        self.fill_count += 1
        return StrategyResult.hold(context)

    def on_position_close(self, trade, context: StrategyContext | None = None) -> StrategyResult:
        self.closed_count += 1
        return StrategyResult.hold(context)

    def generate_signal(self) -> Signal:
        return self._signal

    def reset(self) -> None:
        self._signal = Signal.hold()


class ImmediateFillBroker(BrokerAdapter):
    def __init__(self, fill_price: float = 100.0) -> None:
        self.fill_price = fill_price
        self.orders: Dict[str, BrokerOrder] = {}
        self.connected = True
        self.cancelled: List[str] = []

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def get_account_info(self) -> AccountInfo:
        return AccountInfo(account_id="test", currency="USD", cash=100000.0, buying_power=100000.0)

    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        return []

    async def get_order(self, order_id: str, symbol: str) -> BrokerOrder:
        return self.orders[order_id]

    async def cancel_order(self, order_id: str, symbol: str) -> BrokerOrder:
        order = self.orders[order_id]
        order.status = BrokerStatus.CANCELLED
        self.cancelled.append(order_id)
        return order

    async def submit_order(
        self,
        symbol: str,
        side: BrokerSide,
        order_type: OrderType,
        quantity: float,
        *,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        client_order_id: Optional[str] = None,
    ) -> BrokerOrder:
        broker_order_id = f"broker-{len(self.orders) + 1}"
        order = BrokerOrder(
            broker_order_id=broker_order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            status=BrokerStatus.FILLED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            filled_quantity=quantity,
            average_fill_price=self.fill_price,
            time_in_force=time_in_force,
        )
        self.orders[broker_order_id] = order
        return order

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        return {"symbol": symbol, "last": self.fill_price}

    async def get_ohlcv(self, symbol: str, timeframe: str = "1m", since: Optional[datetime] = None, limit: int = 100):
        return []

    @property
    def is_connected(self) -> bool:
        return self.connected

    @property
    def exchange_name(self) -> str:
        return "immediate"


@pytest.mark.asyncio
async def test_sprint12_end_to_end_tick_to_report(tmp_path: Path) -> None:
    broker = ImmediateFillBroker(fill_price=100.0)
    executor = LiveExecutor(broker, poll_interval=0.0, fill_timeout=1.0)
    positions = PositionSynchronizer(broker)
    oms = OMS(executor, broker=broker, position_synchronizer=positions, config=OMSConfig(max_position_size=0.1))
    strategy = RuntimeStrategy()
    pipeline = LiveTradingPipeline(
        strategy_engine=StrategyEngine(strategy),
        oms=oms,
        portfolio=Portfolio(100000.0),
        persistence=JsonlTradingPersistence(tmp_path),
    )

    first = await pipeline.handle_tick(
        TickEvent(symbol="BTC/USD", price=Decimal("100"), size=Decimal("1"), side="buy", exchange="test")
    )
    assert first.order is not None
    assert first.order.is_filled
    assert first.order.broker_order_id == "broker-1"
    assert positions.get_position("BTC/USD") is not None
    assert first.portfolio_snapshot.position_quantity > 0
    assert "Portfolio Analytics" in first.report.markdown

    broker.fill_price = 110.0
    second = await pipeline.handle_tick(
        TickEvent(symbol="BTC/USD", price=Decimal("110"), size=Decimal("1"), side="sell", exchange="test")
    )
    assert second.order is not None
    assert second.order.is_filled
    assert second.trade is not None
    assert strategy.fill_count == 2
    assert strategy.closed_count == 1
    assert pipeline.processed_ticks == 2
    assert (tmp_path / "orders.jsonl").exists()
    assert (tmp_path / "fills.jsonl").exists()
    assert (tmp_path / "portfolio_snapshots.jsonl").exists()
    assert (tmp_path / "analytics_snapshots.jsonl").exists()


@pytest.mark.asyncio
async def test_sprint12_risk_rejection_is_stored(tmp_path: Path) -> None:
    broker = ImmediateFillBroker(fill_price=100.0)
    executor = LiveExecutor(broker, poll_interval=0.0, fill_timeout=1.0)
    oms = OMS(
        executor,
        broker=broker,
        config=OMSConfig(max_position_size=1.0, max_order_value=10.0, require_risk_validation=True),
    )
    pipeline = LiveTradingPipeline(
        strategy_engine=StrategyEngine(RuntimeStrategy()),
        oms=oms,
        portfolio=Portfolio(100000.0),
        persistence=JsonlTradingPersistence(tmp_path),
    )

    result = await pipeline.handle_tick(
        TickEvent(symbol="ETH/USD", price=Decimal("100"), size=Decimal("1"), side="buy", exchange="test")
    )
    assert result.order is not None
    assert result.order.status.value == "rejected"
    assert len(oms.risk_decisions) == 1
    assert oms.risk_decisions[0].passed is False
    assert (tmp_path / "risk_decisions.jsonl").exists()


@pytest.mark.asyncio
async def test_sprint12_order_cancel_synchronizes_broker_id() -> None:
    broker = ImmediateFillBroker(fill_price=100.0)
    executor = LiveExecutor(broker, poll_interval=0.0, fill_timeout=1.0)
    oms = OMS(executor, broker=broker)
    order = oms.order_manager.create_order(
        side=__import__("backend.app.trading.execution.order", fromlist=["OrderSide"]).OrderSide.BUY,
        intent=__import__("backend.app.trading.execution.order", fromlist=["OrderIntent"]).OrderIntent.ENTRY,
        quantity=1.0,
        reference_price=100.0,
        symbol="BTC/USD",
    )
    broker_order = BrokerOrder(
        broker_order_id="broker-open",
        symbol="BTC/USD",
        side=BrokerSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        status=BrokerStatus.OPEN,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    broker.orders[broker_order.broker_order_id] = broker_order
    order.broker_order_id = broker_order.broker_order_id
    order.submit()

    assert await oms.cancel_order(order.order_id)
    assert broker.cancelled == ["broker-open"]
    assert order.status.value == "cancelled"
