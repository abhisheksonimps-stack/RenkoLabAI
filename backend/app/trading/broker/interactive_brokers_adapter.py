"""Interactive Brokers adapter using ib_insync when available."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.trading.broker.interfaces import (
    AccountInfo,
    BrokerAdapter,
    BrokerError,
    BrokerOrder,
    ConnectionError,
    InvalidOrderError,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TimeInForce,
)

try:
    from ib_insync import IB, Forex, MarketOrder, LimitOrder, Stock, StopOrder
except ImportError:  # pragma: no cover
    IB = Forex = MarketOrder = LimitOrder = Stock = StopOrder = None  # type: ignore[assignment]


class InteractiveBrokersAdapter(BrokerAdapter):
    """Interactive Brokers TWS/Gateway adapter."""

    def __init__(self, *, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._ib: Any = None

    @property
    def is_connected(self) -> bool:
        return bool(self._ib is not None and self._ib.isConnected())

    @property
    def exchange_name(self) -> str:
        return "interactive_brokers"

    async def connect(self) -> None:
        if IB is None:
            raise ConnectionError("ib_insync is required for Interactive Brokers integration")
        self._ib = IB()
        try:
            await self._ib.connectAsync(self._host, self._port, clientId=self._client_id)
        except Exception as exc:
            raise ConnectionError(f"Failed to connect to Interactive Brokers: {exc}") from exc

    async def disconnect(self) -> None:
        if self._ib is not None:
            self._ib.disconnect()
        self._ib = None

    async def get_account_info(self) -> AccountInfo:
        self._ensure_connected()
        account_values = await asyncio.to_thread(self._ib.accountValues)
        lookup = {(item.tag, item.currency): item.value for item in account_values}
        currency = "USD"
        return AccountInfo(
            account_id=str(account_values[0].account) if account_values else "ib",
            currency=currency,
            cash=float(lookup.get(("CashBalance", currency), 0) or 0),
            buying_power=float(lookup.get(("BuyingPower", currency), 0) or 0),
            margin_used=float(lookup.get(("FullInitMarginReq", currency), 0) or 0),
            margin_available=float(lookup.get(("FullAvailableFunds", currency), 0) or 0),
            positions=await self.get_positions(),
        )

    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        self._ensure_connected()
        raw_positions = await asyncio.to_thread(self._ib.positions)
        positions: list[Position] = []
        for item in raw_positions:
            contract_symbol = getattr(item.contract, "symbol", "")
            if symbol and contract_symbol != symbol:
                continue
            qty = float(item.position)
            positions.append(
                Position(
                    symbol=contract_symbol,
                    side="long" if qty >= 0 else "short",
                    quantity=abs(qty),
                    average_entry_price=float(item.avgCost),
                    metadata={"account": item.account, "contract": repr(item.contract)},
                )
            )
        return positions

    async def get_order(self, order_id: str, symbol: str) -> BrokerOrder:
        self._ensure_connected()
        trades = await asyncio.to_thread(self._ib.trades)
        for trade in trades:
            if str(getattr(trade.order, "orderId", "")) == str(order_id):
                return self._map_trade(trade, symbol)
        raise InvalidOrderError(f"Order not found: {order_id}")

    async def cancel_order(self, order_id: str, symbol: str) -> BrokerOrder:
        self._ensure_connected()
        trades = await asyncio.to_thread(self._ib.trades)
        for trade in trades:
            if str(getattr(trade.order, "orderId", "")) == str(order_id):
                self._ib.cancelOrder(trade.order)
                return self._map_trade(trade, symbol, forced_status=OrderStatus.CANCELLED)
        raise InvalidOrderError(f"Order not found: {order_id}")

    async def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        *,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        client_order_id: Optional[str] = None,
    ) -> BrokerOrder:
        self._ensure_connected()
        contract = self._contract(symbol)
        action = "BUY" if side is OrderSide.BUY else "SELL"
        if order_type is OrderType.MARKET:
            order = MarketOrder(action, quantity)
        elif order_type is OrderType.LIMIT and limit_price is not None:
            order = LimitOrder(action, quantity, limit_price)
        elif order_type is OrderType.STOP and stop_price is not None:
            order = StopOrder(action, quantity, stop_price)
        else:
            raise InvalidOrderError(f"Unsupported IB order type or missing price: {order_type.value}")
        order.tif = time_in_force.value.upper()
        if client_order_id:
            order.orderRef = client_order_id
        trade = await self._ib.placeOrderAsync(contract, order)
        return self._map_trade(trade, symbol)

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        self._ensure_connected()
        ticker = self._ib.reqMktData(self._contract(symbol), "", False, False)
        await asyncio.sleep(1)
        return {"symbol": symbol, "last": ticker.last, "bid": ticker.bid, "ask": ticker.ask, "timestamp": datetime.utcnow().isoformat()}

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1 min",
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        self._ensure_connected()
        bars = await self._ib.reqHistoricalDataAsync(
            self._contract(symbol),
            endDateTime="",
            durationStr=f"{max(1, limit)} M",
            barSizeSetting=timeframe,
            whatToShow="TRADES",
            useRTH=True,
        )
        return [bar.__dict__ for bar in bars]

    def _contract(self, symbol: str) -> Any:
        if "/" in symbol and Forex is not None:
            return Forex(symbol.replace("/", ""))
        return Stock(symbol, "SMART", "USD")

    def _ensure_connected(self) -> None:
        if not self.is_connected:
            raise ConnectionError("Interactive Brokers is not connected")

    @staticmethod
    def _map_trade(trade: Any, symbol: str, forced_status: OrderStatus | None = None) -> BrokerOrder:
        status_raw = str(getattr(trade.orderStatus, "status", "Submitted")).lower()
        status_map = {
            "submitted": OrderStatus.OPEN,
            "presubmitted": OrderStatus.OPEN,
            "filled": OrderStatus.FILLED,
            "cancelled": OrderStatus.CANCELLED,
            "inactive": OrderStatus.REJECTED,
        }
        order = trade.order
        side = OrderSide.BUY if str(order.action).upper() == "BUY" else OrderSide.SELL
        return BrokerOrder(
            broker_order_id=str(order.orderId),
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET if order.orderType == "MKT" else OrderType.LIMIT,
            quantity=float(order.totalQuantity),
            status=forced_status or status_map.get(status_raw, OrderStatus.OPEN),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            filled_quantity=float(getattr(trade.orderStatus, "filled", 0) or 0),
            average_fill_price=float(getattr(trade.orderStatus, "avgFillPrice", 0) or 0) or None,
            limit_price=float(getattr(order, "lmtPrice", 0) or 0) or None,
            stop_price=float(getattr(order, "auxPrice", 0) or 0) or None,
            metadata={"status": status_raw},
        )


__all__ = ["InteractiveBrokersAdapter"]
