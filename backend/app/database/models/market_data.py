from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Enum as SaEnum, Float, ForeignKey, Integer, String, Time, UniqueConstraint

from backend.app.database.models.base import Base
from backend.app.domain.market_data.enums import AssetClass, Timeframe


class ExchangeEntity(Base):
    __tablename__ = "exchanges"

    name = Column(String(64), primary_key=True)
    country = Column(String(64), nullable=False)
    timezone = Column(String(64), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ExchangeEntity(name={self.name})>"


class SymbolEntity(Base):
    __tablename__ = "symbols"

    symbol = Column(String(64), primary_key=True)
    exchange_name = Column(String(64), ForeignKey("exchanges.name"), nullable=False)
    asset_class = Column(SaEnum(AssetClass, name="asset_class"), nullable=False)
    base_currency = Column(String(16), nullable=False)
    quote_currency = Column(String(16), nullable=False)
    description = Column(String(256), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SymbolEntity(symbol={self.symbol})>"


class TradingSessionEntity(Base):
    __tablename__ = "trading_sessions"
    __table_args__ = (UniqueConstraint("exchange_name", "session_name", "start_time", "end_time", name="uq_session"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange_name = Column(String(64), nullable=False)
    session_name = Column(String(64), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    timezone = Column(String(64), nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TradingSessionEntity(exchange={self.exchange_name}, session={self.session_name})>"


class CandleEntity(Base):
    __tablename__ = "candles"
    __table_args__ = (UniqueConstraint("symbol", "timeframe", "start_time", name="uq_candle"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(64), nullable=False)
    exchange_name = Column(String(64), nullable=False)
    timeframe = Column(SaEnum(Timeframe, name="timeframe"), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False, default=0.0)
    trades = Column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CandleEntity(symbol={self.symbol}, timeframe={self.timeframe})>"


class TickEntity(Base):
    __tablename__ = "ticks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(64), nullable=False)
    exchange_name = Column(String(64), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    price = Column(Float, nullable=False)
    size = Column(Float, nullable=True)
    bid = Column(Float, nullable=True)
    ask = Column(Float, nullable=True)
    exchange_timestamp = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TickEntity(symbol={self.symbol}, timestamp={self.timestamp})>"
