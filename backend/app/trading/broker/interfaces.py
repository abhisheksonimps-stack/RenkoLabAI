"""Broker abstraction interfaces.

Defines the contract that all broker/exchange adapters must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class OrderType(str, Enum):
    """Supported order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(str, Enum):
    """Order time-in-force instructions."""
    GTC = "gtc"  # Good 'til cancelled
    IOC = "ioc"  # Immediate or cancel
    FOK = "fok"  # Fill or kill
    DAY = "day"  # Day order


class OrderSide(str, Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Broker-reported order status."""
    CREATED = "created"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class BrokerOrder:
    """Broker-agnostic order representation."""
    broker_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
    filled_quantity: float = 0.0
    average_fill_price: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.GTC
    reject_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Position:
    """Broker-reported position."""
    symbol: str
    side: str  # "long" or "short"
    quantity: float
    average_entry_price: float
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: float = 0.0
    leverage: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AccountInfo:
    """Broker account information."""
    account_id: str
    currency: str
    cash: float
    buying_power: float
    margin_used: float = 0.0
    margin_available: float = 0.0
    leverage: float = 1.0
    positions: List[Position] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BrokerError(Exception):
    """Base broker error."""
    pass


class InsufficientFundsError(BrokerError):
    """Insufficient funds for order."""
    pass


class InvalidOrderError(BrokerError):
    """Invalid order parameters."""
    pass


class RateLimitError(BrokerError):
    """Exchange rate limit exceeded."""
    pass


class ConnectionError(BrokerError):
    """Connection to exchange failed."""
    pass


class BrokerAdapter(ABC):
    """Abstract base class for broker/exchange adapters.

    All broker implementations must implement this interface to ensure
    interchangeability across different venues.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the broker/exchange."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the broker/exchange."""
        pass

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """Retrieve account information including balances and positions."""
        pass

    @abstractmethod
    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """Retrieve current positions, optionally filtered by symbol."""
        pass

    @abstractmethod
    async def get_order(self, order_id: str, symbol: str) -> BrokerOrder:
        """Retrieve order status by ID."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> BrokerOrder:
        """Cancel an open order."""
        pass

    @abstractmethod
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
        """Submit a new order to the broker.

        Returns the broker-acknowledged order with assigned broker_order_id.
        """
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get current ticker/quote for a symbol."""
        pass

    @abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch OHLCV candlestick data."""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Return connection status."""
        pass

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Return the exchange/broker name."""
        pass