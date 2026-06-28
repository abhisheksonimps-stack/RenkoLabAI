"""Typed market-data errors.

Adapters translate source-specific failures (HTTP, parse, auth) into these so
callers never see raw third-party exceptions, and the rest of the framework can
stay pure and deterministic.
"""

from __future__ import annotations


class MarketDataError(Exception):
    """Base for all market-data errors."""


class AdapterNotFound(MarketDataError):
    pass


class SymbolNotFound(MarketDataError):
    pass


class DataUnavailable(MarketDataError):
    pass


class RateLimited(MarketDataError):
    pass


class MalformedData(MarketDataError):
    pass


class NotSupported(MarketDataError):
    pass
