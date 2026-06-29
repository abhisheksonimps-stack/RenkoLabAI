"""Broker abstraction layer for live trading execution.

Provides a venue-agnostic interface to broker/exchange APIs, with a CCXT-based
implementation as the first concrete adapter.
"""