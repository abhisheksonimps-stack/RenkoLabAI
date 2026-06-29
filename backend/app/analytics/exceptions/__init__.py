"""Analytics exceptions."""


class AnalyticsError(Exception):
    """Base exception for analytics failures."""


class AnalyticsValidationError(AnalyticsError):
    """Raised when analytics input is invalid."""


class AnalyticsMetricError(AnalyticsError):
    """Raised when a requested metric cannot be resolved."""


class AnalyticsReportError(AnalyticsError):
    """Raised when an analytics report cannot be created or rendered."""


__all__ = [
    "AnalyticsError",
    "AnalyticsMetricError",
    "AnalyticsReportError",
    "AnalyticsValidationError",
]
