"""Alpaca broker adapter using Alpaca's REST API."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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


class AlpacaAdapter(BrokerAdapter):
    """Async wrapper around Alpaca Trading REST endpoints."""

    def __init__(self, *, api_key: str, secret_key: str, paper: bool = True, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._base_url = (base_url or ("https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets")).rstrip("/")
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def exchange_name(self) -> str:
        return "alpaca"

    async def connect(self) -> None:
        try:
            await self.get_account_info()
            self._connected = True
        except Exception as exc:
            self._connected = False
            raise ConnectionError(f"Failed to connect to Alpaca: {exc}") from exc

    async def disconnect(self) -> None:
        self._connected = False

    async def get_account_info(self) -> AccountInfo:
        data = await self._request("GET", "/v2/account")
        return AccountInfo(
            account_id=str(data.get("id", "alpaca")),
            currency="USD",
            cash=float(data.get("cash", 0) or 0),
            buying_power=float(data.get("buying_power", 0) or 0),
            margin_used=max(0.0, float(data.get("portfolio_value", 0) or 0) - float(data.get("equity", 0) or 0)),
            margin_available=float(data.get("buying_power", 0) or 0),
            leverage=float(data.get("multiplier", 1) or 1),
            positions=await self.get_positions(),
            metadata=data,
        )

    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        endpoint = f"/v2/positions/{symbol}" if symbol else "/v2/positions"
        data = await self._request("GET", endpoint)
        raw_positions = data if isinstance(data, list) else [data]
        return [
            Position(
                symbol=str(item.get("symbol", "")),
                side="long" if float(item.get("qty", 0) or 0) >= 0 else "short",
                quantity=abs(float(item.get("qty", 0) or 0)),
                average_entry_price=float(item.get("avg_entry_price", 0) or 0),
                current_price=float(item.get("current_price", 0) or 0),
                unrealized_pnl=float(item.get("unrealized_pl", 0) or 0),
                metadata=item,
            )
            for item in raw_positions
            if item
        ]

    async def get_order(self, order_id: str, symbol: str) -> BrokerOrder:
        return self._map_order(await self._request("GET", f"/v2/orders/{order_id}"))

    async def cancel_order(self, order_id: str, symbol: str) -> BrokerOrder:
        await self._request("DELETE", f"/v2/orders/{order_id}")
        order = await self.get_order(order_id, symbol)
        if order.status not in (OrderStatus.CANCELLED, OrderStatus.FILLED):
            order.status = OrderStatus.CANCELLED
        return order

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
        payload: dict[str, object] = {
            "symbol": symbol,
            "qty": str(quantity),
            "side": side.value,
            "type": order_type.value.replace("stop_limit", "stop_limit"),
            "time_in_force": time_in_force.value,
        }
        if client_order_id:
            payload["client_order_id"] = client_order_id
        if limit_price is not None:
            payload["limit_price"] = str(limit_price)
        if stop_price is not None:
            payload["stop_price"] = str(stop_price)
        try:
            return self._map_order(await self._request("POST", "/v2/orders", payload))
        except BrokerError as exc:
            raise InvalidOrderError(str(exc)) from exc

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        endpoint = f"/v2/stocks/{symbol}/quotes/latest"
        return await self._request("GET", endpoint, market_data=True)

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1Min",
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        params = {"timeframe": timeframe, "limit": str(limit)}
        if since is not None:
            params["start"] = since.isoformat()
        endpoint = f"/v2/stocks/{symbol}/bars?{urlencode(params)}"
        data = await self._request("GET", endpoint, market_data=True)
        return list(data.get("bars", [])) if isinstance(data, dict) else []

    async def _request(self, method: str, endpoint: str, payload: dict[str, object] | None = None, *, market_data: bool = False) -> Any:
        return await asyncio.to_thread(self._request_sync, method, endpoint, payload, market_data)

    def _request_sync(self, method: str, endpoint: str, payload: dict[str, object] | None, market_data: bool) -> Any:
        base = "https://data.alpaca.markets" if market_data else self._base_url
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            f"{base}{endpoint}",
            data=body,
            method=method,
            headers={
                "APCA-API-KEY-ID": self._api_key,
                "APCA-API-SECRET-KEY": self._secret_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - endpoint controlled by adapter base URL
                content = response.read().decode()
                return json.loads(content) if content else {}
        except HTTPError as exc:
            detail = exc.read().decode(errors="ignore")
            raise BrokerError(f"Alpaca HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise ConnectionError(f"Alpaca connection failed: {exc}") from exc

    @staticmethod
    def _map_order(data: dict[str, Any]) -> BrokerOrder:
        status_map = {
            "new": OrderStatus.OPEN,
            "accepted": OrderStatus.OPEN,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "filled": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "expired": OrderStatus.EXPIRED,
        }
        order_type = OrderType(data.get("type", "market")) if data.get("type", "market") in OrderType._value2member_map_ else OrderType.MARKET
        created_at = datetime.fromisoformat(str(data.get("created_at")).replace("Z", "+00:00")) if data.get("created_at") else datetime.utcnow()
        updated_at = datetime.fromisoformat(str(data.get("updated_at")).replace("Z", "+00:00")) if data.get("updated_at") else created_at
        return BrokerOrder(
            broker_order_id=str(data.get("id", "")),
            symbol=str(data.get("symbol", "")),
            side=OrderSide.BUY if data.get("side") == "buy" else OrderSide.SELL,
            order_type=order_type,
            quantity=float(data.get("qty", 0) or 0),
            status=status_map.get(str(data.get("status", "new")), OrderStatus.OPEN),
            created_at=created_at,
            updated_at=updated_at,
            filled_quantity=float(data.get("filled_qty", 0) or 0),
            average_fill_price=float(data["filled_avg_price"]) if data.get("filled_avg_price") else None,
            limit_price=float(data["limit_price"]) if data.get("limit_price") else None,
            stop_price=float(data["stop_price"]) if data.get("stop_price") else None,
            reject_reason=data.get("failed_at") or data.get("replaced_by"),
            metadata=data,
        )


__all__ = ["AlpacaAdapter"]
