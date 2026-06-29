"""CCXT-based broker adapter.

Wraps the CCXT library to provide a unified interface to multiple cryptocurrency
exchanges. Translates between CCXT's native types and our broker abstraction.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import ccxt.async_support as ccxt

from backend.app.trading.broker.interfaces import (
    AccountInfo,
    BrokerAdapter,
    BrokerError,
    BrokerOrder,
    ConnectionError,
    InsufficientFundsError,
    InvalidOrderError,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    RateLimitError,
    TimeInForce,
)


class CCXTAdapter(BrokerAdapter):
    """CCXT-based broker adapter for cryptocurrency exchanges.

    Supports any exchange available in CCXT. Configuration is passed via
    exchange-specific parameters (API keys, secrets, etc.).

    Example:
        adapter = CCXTAdapter("binance", {
            "apiKey": "your-key",
            "secret": "your-secret",
            "enableRateLimit": True,
        })
        await adapter.connect()
        account = await adapter.get_account_info()
    """

    def __init__(self, exchange_id: str, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the CCXT adapter.

        Args:
            exchange_id: CCXT exchange identifier (e.g., "binance", "coinbase")
            config: Exchange-specific configuration (API keys, options, etc.)
        """
        if not hasattr(ccxt, exchange_id):
            raise ValueError(f"Unsupported exchange: {exchange_id}")

        self._exchange_id = exchange_id
        self._config = config or {}
        self._exchange: Optional[ccxt.Exchange] = None
        self._connected = False

    @property
    def exchange_name(self) -> str:
        return self._exchange_id

    @property
    def is_connected(self) -> bool:
        return self._connected and self._exchange is not None

    async def connect(self) -> None:
        """Initialize and load the exchange."""
        try:
            exchange_class = getattr(ccxt, self._exchange_id)
            self._exchange = exchange_class(self._config)
            await self._exchange.load_markets()
            self._connected = True
        except Exception as exc:
            self._connected = False
            raise ConnectionError(f"Failed to connect to {self._exchange_id}: {exc}") from exc

    async def disconnect(self) -> None:
        """Close the exchange connection."""
        if self._exchange is not None:
            try:
                await self._exchange.close()
            except Exception:
                pass  # Best-effort close
            self._exchange = None
        self._connected = False

    async def get_account_info(self) -> AccountInfo:
        """Retrieve account balance and info."""
        self._ensure_connected()
        try:
            balance = await self._exchange.fetch_balance()
            # CCXT returns free/used/total for each currency
            # We extract the quote currency (usually USDT, USD, etc.)
            total_balance = balance.get("total", {})
            free_balance = balance.get("free", {})
            used_balance = balance.get("used", {})

            # Sum all non-zero balances for total equity
            cash = sum(v for v in free_balance.values() if isinstance(v, (int, float)))
            margin_used = sum(v for v in used_balance.values() if isinstance(v, (int, float)))

            # Fetch positions if spot (for futures, use fetch_positions)
            positions: List[Position] = []
            if self._exchange.has.get("fetchPositions"):
                try:
                    raw_positions = await self._exchange.fetch_positions()
                    for pos in raw_positions:
                        if float(pos.get("contracts", 0)) > 0:
                            positions.append(self._map_position(pos))
                except Exception:
                    pass  # Positions not supported or failed

            return AccountInfo(
                account_id=balance.get("info", {}).get("accountId", self._exchange_id),
                currency="USD",  # Default; exchanges may override
                cash=cash,
                buying_power=cash,
                margin_used=margin_used,
                margin_available=cash - margin_used,
                leverage=1.0,
                positions=positions,
            )
        except ccxt.RateLimitExceeded as exc:
            raise RateLimitError(f"Rate limit exceeded: {exc}") from exc
        except ccxt.InsufficientFunds as exc:
            raise InsufficientFundsError(f"Insufficient funds: {exc}") from exc
        except ccxt.InvalidOrder as exc:
            raise InvalidOrderError(f"Invalid order: {exc}") from exc
        except Exception as exc:
            raise BrokerError(f"Failed to fetch account info: {exc}") from exc

    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """Retrieve current positions."""
        self._ensure_connected()
        try:
            if not self._exchange.has.get("fetchPositions"):
                return []

            raw_positions = await self._exchange.fetch_positions([symbol] if symbol else None)
            return [self._map_position(pos) for pos in raw_positions]
        except Exception:
            return []

    async def get_order(self, order_id: str, symbol: str) -> BrokerOrder:
        """Retrieve order status."""
        self._ensure_connected()
        try:
            raw_order = await self._exchange.fetch_order(order_id, symbol)
            return self._map_order(raw_order)
        except ccxt.OrderNotFound as exc:
            raise InvalidOrderError(f"Order not found: {order_id}") from exc
        except Exception as exc:
            raise BrokerError(f"Failed to fetch order: {exc}") from exc

    async def cancel_order(self, order_id: str, symbol: str) -> BrokerOrder:
        """Cancel an open order."""
        self._ensure_connected()
        try:
            raw_order = await self._exchange.cancel_order(order_id, symbol)
            return self._map_order(raw_order)
        except ccxt.OrderNotFound as exc:
            raise InvalidOrderError(f"Order not found: {order_id}") from exc
        except Exception as exc:
            raise BrokerError(f"Failed to cancel order: {exc}") from exc

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
        """Submit a new order."""
        self._ensure_connected()
        try:
            # Map our order types to CCXT
            type_map = {
                OrderType.MARKET: "market",
                OrderType.LIMIT: "limit",
                OrderType.STOP: "stop",
                OrderType.STOP_LIMIT: "stop_limit",
            }
            ccxt_type = type_map[order_type]

            # Map sides
            ccxt_side = "buy" if side == OrderSide.BUY else "sell"

            # Build params
            params: Dict[str, Any] = {}
            if client_order_id:
                params["clientOrderId"] = client_order_id

            # Map time-in-force
            tif_map = {
                TimeInForce.GTC: "GTC",
                TimeInForce.IOC: "IOC",
                TimeInForce.FOK: "FOK",
                TimeInForce.DAY: "DAY",
            }
            if time_in_force != TimeInForce.GTC:
                params["timeInForce"] = tif_map[time_in_force]

            # Submit based on type
            if order_type == OrderType.MARKET:
                raw_order = await self._exchange.create_order(symbol, ccxt_type, ccxt_side, quantity, params=params)
            elif order_type == OrderType.LIMIT:
                if limit_price is None:
                    raise InvalidOrderError("Limit price required for limit orders")
                raw_order = await self._exchange.create_order(symbol, ccxt_type, ccxt_side, quantity, limit_price, params=params)
            elif order_type == OrderType.STOP:
                if stop_price is None:
                    raise InvalidOrderError("Stop price required for stop orders")
                raw_order = await self._exchange.create_order(symbol, ccxt_type, ccxt_side, quantity, None, stop_price, params=params)
            elif order_type == OrderType.STOP_LIMIT:
                if limit_price is None or stop_price is None:
                    raise InvalidOrderError("Limit and stop prices required for stop-limit orders")
                raw_order = await self._exchange.create_order(symbol, ccxt_type, ccxt_side, quantity, limit_price, stop_price, params=params)
            else:
                raise InvalidOrderError(f"Unsupported order type: {order_type}")

            return self._map_order(raw_order)
        except ccxt.InsufficientFunds as exc:
            raise InsufficientFundsError(f"Insufficient funds: {exc}") from exc
        except ccxt.InvalidOrder as exc:
            raise InvalidOrderError(f"Invalid order: {exc}") from exc
        except ccxt.RateLimitExceeded as exc:
            raise RateLimitError(f"Rate limit exceeded: {exc}") from exc
        except Exception as exc:
            raise BrokerError(f"Failed to submit order: {exc}") from exc

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get current ticker."""
        self._ensure_connected()
        try:
            ticker = await self._exchange.fetch_ticker(symbol)
            return {
                "symbol": symbol,
                "last": ticker.get("last"),
                "bid": ticker.get("bid"),
                "ask": ticker.get("ask"),
                "high": ticker.get("high"),
                "low": ticker.get("low"),
                "volume": ticker.get("baseVolume"),
                "timestamp": ticker.get("timestamp"),
            }
        except Exception as exc:
            raise BrokerError(f"Failed to fetch ticker: {exc}") from exc

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch OHLCV data."""
        self._ensure_connected()
        try:
            since_ms = int(since.timestamp() * 1000) if since else None
            raw_ohlcv = await self._exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)
            return [
                {
                    "timestamp": datetime.fromtimestamp(candle[0] / 1000),
                    "open": candle[1],
                    "high": candle[2],
                    "low": candle[3],
                    "close": candle[4],
                    "volume": candle[5],
                }
                for candle in raw_ohlcv
            ]
        except Exception as exc:
            raise BrokerError(f"Failed to fetch OHLCV: {exc}") from exc

    def _ensure_connected(self) -> None:
        """Raise if not connected."""
        if not self.is_connected:
            raise ConnectionError(f"Not connected to {self._exchange_id}")

    def _map_order(self, raw: Dict[str, Any]) -> BrokerOrder:
        """Map CCXT order to our BrokerOrder."""
        # Map CCXT status to our status
        status_map = {
            "open": OrderStatus.OPEN,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "expired": OrderStatus.EXPIRED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
        }
        ccxt_status = raw.get("status", "open")
        status = status_map.get(ccxt_status, OrderStatus.OPEN)

        # Map side
        side = OrderSide.BUY if raw.get("side") == "buy" else OrderSide.SELL

        # Map type
        type_map = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
            "stop": OrderType.STOP,
            "stop_limit": OrderType.STOP_LIMIT,
        }
        order_type = type_map.get(raw.get("type"), OrderType.MARKET)

        # Parse timestamps
        created_at = self._parse_timestamp(raw.get("timestamp"))
        updated_at = self._parse_timestamp(raw.get("lastUpdateTimestamp")) or created_at or datetime.utcnow()

        # Extract fill info
        filled = float(raw.get("filled", 0))
        average = raw.get("average")
        cost = raw.get("cost")

        return BrokerOrder(
            broker_order_id=str(raw.get("id", "")),
            symbol=raw.get("symbol", ""),
            side=side,
            order_type=order_type,
            quantity=float(raw.get("amount", 0)),
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            filled_quantity=filled,
            average_fill_price=float(average) if average else None,
            limit_price=raw.get("price") if order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) else None,
            stop_price=raw.get("stopPrice") if order_type in (OrderType.STOP, OrderType.STOP_LIMIT) else None,
            reject_reason=raw.get("info", {}).get("rejectReason"),
            metadata={"raw": raw},
        )

    def _map_position(self, raw: Dict[str, Any]) -> Position:
        """Map CCXT position to our Position."""
        contracts = float(raw.get("contracts", 0))
        if contracts == 0:
            # Skip empty positions
            return Position(
                symbol=raw.get("symbol", ""),
                side="long",
                quantity=0.0,
                average_entry_price=0.0,
            )

        side = "long" if float(raw.get("contracts", 0)) > 0 else "short"
        return Position(
            symbol=raw.get("symbol", ""),
            side=side,
            quantity=abs(float(raw.get("contracts", 0))),
            average_entry_price=float(raw.get("entryPrice", 0)),
            current_price=raw.get("markPrice"),
            unrealized_pnl=raw.get("unrealizedPnl"),
            realized_pnl=float(raw.get("realizedPnl", 0)),
            leverage=float(raw.get("leverage", 1)),
        )

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        """Parse millisecond timestamp to datetime."""
        if value is None:
            return None
        try:
            return datetime.fromtimestamp(int(value) / 1000)
        except (ValueError, TypeError):
            return None