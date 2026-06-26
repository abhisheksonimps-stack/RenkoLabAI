class MarketDataError(Exception):
    """Base market data exception."""

    pass


class MarketDataValidationError(MarketDataError):
    """Raised when market data validation fails."""

    pass


class InvalidSymbolError(MarketDataError):
    """Raised when a symbol cannot be resolved."""

    pass
