"""Broker abstraction layer for live trading execution.

Provides a venue-agnostic interface to broker/exchange APIs, with a CCXT-based
implementation as the first concrete adapter.
"""
from backend.app.trading.broker.binance_adapter import BinanceAdapter
from backend.app.trading.broker.alpaca_adapter import AlpacaAdapter
from backend.app.trading.broker.interactive_brokers_adapter import InteractiveBrokersAdapter

__all__ = ["AlpacaAdapter", "BinanceAdapter", "InteractiveBrokersAdapter"]
