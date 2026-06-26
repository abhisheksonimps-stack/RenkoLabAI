from datetime import datetime, time

import pytest

from backend.app.domain.market_data import (
    AssetClass,
    Candle,
    Exchange,
    MarketDataProvider,
    MarketDataValidationError,
    MarketDataValidator,
    Symbol,
    SymbolRegistry,
    Timeframe,
    Tick,
    TradingSession,
)


def test_symbol_model_normalization():
    symbol = Symbol(
        symbol="btcusdt",
        exchange="binance",
        asset_class=AssetClass.CRYPTO,
        base_currency="btc",
        quote_currency="usdt",
    )
    assert symbol.symbol == "BTCUSDT"
    assert symbol.exchange == "BINANCE"
    assert symbol.asset_class == AssetClass.CRYPTO


def test_candle_model_validation():
    candle = Candle(
        symbol="BTCUSDT",
        exchange="BINANCE",
        timeframe=Timeframe.ONE_MINUTE,
        start_time=datetime(2026, 1, 1, 0, 0),
        open=10.0,
        high=15.0,
        low=8.0,
        close=12.0,
        volume=123.0,
        trades=5,
    )
    assert candle.high >= candle.low
    assert candle.open >= candle.low


def test_tick_model_validation():
    tick = Tick(
        symbol="AAPL",
        exchange="NASDAQ",
        timestamp=datetime(2026, 1, 1, 9, 30),
        price=145.0,
        size=10.5,
        bid=144.5,
        ask=145.5,
    )
    assert tick.price == 145.0


def test_trading_session_validation():
    session = TradingSession(
        exchange="NYSE",
        session_name="REGULAR",
        start_time=time(9, 30),
        end_time=time(16, 0),
        timezone="America/New_York",
    )
    assert session.active is True


def test_symbol_registry():
    registry = SymbolRegistry()
    symbol = Symbol(
        symbol="AAPL",
        exchange="NASDAQ",
        asset_class=AssetClass.EQUITY,
        base_currency="USD",
        quote_currency="USD",
    )
    registry.register(symbol)
    assert registry.get("AAPL") == symbol
    assert registry.list(exchange="NASDAQ") == [symbol]


def test_market_data_validator_raises():
    with pytest.raises(MarketDataValidationError):
        MarketDataValidator.validate_symbol({"symbol": "", "exchange": "", "asset_class": "crypto", "base_currency": "BTC", "quote_currency": "USD"})


class DummyProvider(MarketDataProvider):
    def __init__(self) -> None:
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    async def fetch_historical(self, symbol, timeframe, start, end):
        return []

    async def stream_ticks(self, symbol):
        if False:
            yield

    async def subscribe_candles(self, symbol, timeframe):
        if False:
            yield


def test_market_data_provider_interface():
    provider = DummyProvider()
    assert not provider.is_connected()

    import asyncio

    async def run() -> None:
        await provider.connect()
        assert provider.is_connected()
        await provider.disconnect()
        assert not provider.is_connected()

    asyncio.run(run())
