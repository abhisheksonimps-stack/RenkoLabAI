from __future__ import annotations

from typing import Any

from pydantic import ValidationError as PydanticValidationError

from .exceptions import MarketDataValidationError
from .models import Candle, Exchange, Symbol, Tick, TradingSession


class MarketDataValidator:
    """Validation wrapper for market data payloads."""

    @staticmethod
    def validate_symbol(payload: dict[str, Any]) -> Symbol:
        try:
            return Symbol.model_validate(payload)
        except PydanticValidationError as error:
            raise MarketDataValidationError(str(error)) from error

    @staticmethod
    def validate_exchange(payload: dict[str, Any]) -> Exchange:
        try:
            return Exchange.model_validate(payload)
        except PydanticValidationError as error:
            raise MarketDataValidationError(str(error)) from error

    @staticmethod
    def validate_trading_session(payload: dict[str, Any]) -> TradingSession:
        try:
            return TradingSession.model_validate(payload)
        except PydanticValidationError as error:
            raise MarketDataValidationError(str(error)) from error

    @staticmethod
    def validate_candle(payload: dict[str, Any]) -> Candle:
        try:
            return Candle.model_validate(payload)
        except PydanticValidationError as error:
            raise MarketDataValidationError(str(error)) from error

    @staticmethod
    def validate_tick(payload: dict[str, Any]) -> Tick:
        try:
            return Tick.model_validate(payload)
        except PydanticValidationError as error:
            raise MarketDataValidationError(str(error)) from error
