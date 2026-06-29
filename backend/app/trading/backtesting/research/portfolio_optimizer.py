"""Portfolio optimization for multiple strategy sleeves."""

from __future__ import annotations

import math
from typing import Sequence

from backend.app.trading.backtesting.research.metrics import _mean, _std
from backend.app.trading.backtesting.research.models import (
    PortfolioAllocation,
    PortfolioOptimizationMethod,
    PortfolioOptimizationResult,
)


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in weights.values())
    if total <= 0:
        count = len(weights)
        return {name: 1.0 / count for name in weights} if count else {}
    return {name: max(0.0, value) / total for name, value in weights.items()}


def _correlation(left: Sequence[float], right: Sequence[float]) -> float:
    size = min(len(left), len(right))
    if size < 2:
        return 0.0
    a = list(left[:size])
    b = list(right[:size])
    ma = _mean(a)
    mb = _mean(b)
    sa = _std(a)
    sb = _std(b)
    if sa == 0 or sb == 0:
        return 0.0
    covariance = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (size - 1)
    return covariance / (sa * sb)


class PortfolioOptimizer:
    """Deterministic long-only portfolio allocation optimizer."""

    def optimize(
        self,
        returns_by_strategy: dict[str, Sequence[float]],
        *,
        method: PortfolioOptimizationMethod = PortfolioOptimizationMethod.RISK_PARITY,
        capital: float = 100_000.0,
    ) -> PortfolioOptimizationResult:
        """Return allocations for the supplied strategy return streams."""
        if capital <= 0:
            raise ValueError("capital must be positive")
        clean = {name: tuple(float(value) for value in values) for name, values in sorted(returns_by_strategy.items())}
        if not clean:
            raise ValueError("at least one strategy return stream is required")
        means = {name: _mean(values) for name, values in clean.items()}
        vols = {name: _std(values) for name, values in clean.items()}
        if method is PortfolioOptimizationMethod.EQUAL_WEIGHT:
            weights = {name: 1.0 for name in clean}
        elif method is PortfolioOptimizationMethod.MINIMUM_VARIANCE:
            weights = {name: 1.0 / max(vols[name] ** 2, 1e-12) for name in clean}
        elif method is PortfolioOptimizationMethod.MAXIMUM_SHARPE:
            weights = {name: max(0.0, means[name]) / max(vols[name] ** 2, 1e-12) for name in clean}
        else:
            weights = {name: 1.0 / max(vols[name], 1e-12) for name in clean}
        normalized = _normalize(weights)
        allocations = tuple(
            PortfolioAllocation(name=name, weight=weight, capital=capital * weight)
            for name, weight in normalized.items()
        )
        correlation = {
            left: {right: (1.0 if left == right else _correlation(clean[left], clean[right])) for right in clean}
            for left in clean
        }
        expected_return = sum(normalized[name] * means[name] for name in clean)
        variance = 0.0
        for left in clean:
            for right in clean:
                variance += normalized[left] * normalized[right] * vols[left] * vols[right] * correlation[left][right]
        expected_volatility = math.sqrt(max(0.0, variance))
        expected_sharpe = expected_return / expected_volatility if expected_volatility else 0.0
        return PortfolioOptimizationResult(
            method=method,
            allocations=allocations,
            expected_return=expected_return,
            expected_volatility=expected_volatility,
            expected_sharpe=expected_sharpe,
            correlation_matrix=correlation,
        )


__all__ = ["PortfolioOptimizer"]
