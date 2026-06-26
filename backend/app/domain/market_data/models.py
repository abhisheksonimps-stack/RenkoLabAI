from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .enums import AssetClass, Timeframe


class Exchange(BaseModel):
    name: str = Field(min_length=1)
    country: str = Field(min_length=1)
    timezone: str = Field(min_length=1)


class Symbol(BaseModel):
    symbol: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    asset_class: AssetClass
    base_currency: str = Field(min_length=1)
    quote_currency: str = Field(min_length=1)
    description: Optional[str] = None

    @field_validator("symbol", "exchange", "base_currency", "quote_currency", mode="before")
    @classmethod
    def _uppercase_string(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class TradingSession(BaseModel):
    exchange: str = Field(min_length=1)
    session_name: str = Field(min_length=1)
    start_time: time
    end_time: time
    timezone: str = Field(min_length=1)
    active: bool = True

    @model_validator(mode="after")
    def check_times(cls, values):
        if values.start_time >= values.end_time:
            raise ValueError("Trading session start_time must be before end_time")
        return values


class Candle(BaseModel):
    symbol: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    timeframe: Timeframe
    start_time: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    trades: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_price_range(cls, values):
        if values.high < values.low:
            raise ValueError("Candle high must be greater than or equal to low")
        if not (values.low <= values.open <= values.high and values.low <= values.close <= values.high):
            raise ValueError("Candle open/close values must be within low/high range")
        return values


class Tick(BaseModel):
    symbol: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    timestamp: datetime
    price: float = Field(gt=0)
    size: Optional[float] = Field(default=None, ge=0)
    bid: Optional[float] = Field(default=None, gt=0)
    ask: Optional[float] = Field(default=None, gt=0)
    exchange_timestamp: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_spread(cls, values):
        if values.bid is not None and values.ask is not None and values.bid > values.ask:
            raise ValueError("Tick bid must be less than or equal to ask")
        return values
