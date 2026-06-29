"""Institutional research metrics.

The calculations are pure, deterministic, dependency-free, and operate on the
existing backtesting equity curve and trade entities. Sprint 7 analytics remains
the canonical report analytics layer; this module provides research-grade
metrics for optimization, simulation, and portfolio allocation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from backend.app.trading.execution.position import Trade
from backend.app.trading.portfolio.portfolio import EquityPoint


@dataclass(frozen=True)
class RollingMetricPoint:
    """One rolling metric observation."""

    index: int
    value: float


@dataclass(frozen=True)
class InstitutionalMetrics:
    """Institutional performance metric set."""

    sharpe: float
    sortino: float
    calmar: float
    omega: float
    mar: float
    ulcer_index: float
    profit_factor: float | None
    expectancy: float
    sqn: float
    alpha: float | None
    beta: float | None
    tracking_error: float | None
    information_ratio: float | None
    treynor: float | None
    var: float
    cvar: float
    exposure: float
    recovery_factor: float
    max_drawdown: float
    max_drawdown_pct: float
    drawdown_duration: int
    rolling_cagr: tuple[RollingMetricPoint, ...]
    rolling_sharpe: tuple[RollingMetricPoint, ...]
    rolling_volatility: tuple[RollingMetricPoint, ...]

    def to_mapping(self) -> dict[str, float | None]:
        """Return scalar metrics as a mapping."""
        return {
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "calmar": self.calmar,
            "omega": self.omega,
            "mar": self.mar,
            "ulcer_index": self.ulcer_index,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "sqn": self.sqn,
            "alpha": self.alpha,
            "beta": self.beta,
            "tracking_error": self.tracking_error,
            "information_ratio": self.information_ratio,
            "treynor": self.treynor,
            "var": self.var,
            "cvar": self.cvar,
            "exposure": self.exposure,
            "recovery_factor": self.recovery_factor,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "drawdown_duration": float(self.drawdown_duration),
        }


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: Sequence[float], sample: bool = True) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    denominator = len(values) - 1 if sample else len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / denominator)


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def equity_values(equity_curve: Sequence[EquityPoint]) -> list[float]:
    """Extract equity values from the existing portfolio equity curve."""
    return [float(point.equity) for point in equity_curve]


def returns_from_equity(equity_curve: Sequence[EquityPoint]) -> list[float]:
    """Return simple period returns from an equity curve."""
    values = equity_values(equity_curve)
    returns: list[float] = []
    for previous, current in zip(values, values[1:]):
        if previous != 0:
            returns.append((current - previous) / previous)
    return returns


def drawdown_series(values: Sequence[float]) -> list[float]:
    """Return drawdown percentages as non-positive decimals."""
    if not values:
        return []
    peak = values[0]
    out: list[float] = []
    for value in values:
        peak = max(peak, value)
        out.append(0.0 if peak == 0 else (value - peak) / peak)
    return out


def max_drawdown(values: Sequence[float]) -> tuple[float, float, int]:
    """Return maximum drawdown amount, percentage, and duration."""
    if not values:
        return 0.0, 0.0, 0
    peak = values[0]
    max_amount = 0.0
    max_pct = 0.0
    current_duration = 0
    max_duration = 0
    for value in values:
        if value >= peak:
            peak = value
            current_duration = 0
        else:
            current_duration += 1
            amount = peak - value
            pct = amount / peak if peak else 0.0
            if amount > max_amount:
                max_amount = amount
                max_pct = pct
            max_duration = max(max_duration, current_duration)
    return max_amount, max_pct, max_duration


def percentile(values: Sequence[float], q: float) -> float:
    """Deterministic percentile with linear interpolation."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * q
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def rolling(values: Sequence[float], window: int, fn) -> tuple[RollingMetricPoint, ...]:
    """Return rolling metric observations using a fixed trailing window."""
    if window <= 0:
        raise ValueError("rolling window must be positive")
    if len(values) < window:
        return ()
    return tuple(
        RollingMetricPoint(index=index, value=float(fn(values[index - window : index])))
        for index in range(window, len(values) + 1)
    )


class InstitutionalMetricsEngine:
    """Compute institutional metrics from backtesting outputs."""

    def compute(
        self,
        equity_curve: Sequence[EquityPoint],
        trades: Sequence[Trade],
        *,
        starting_capital: float,
        benchmark_returns: Sequence[float] = (),
        periods_per_year: int = 252,
        rolling_window: int = 20,
    ) -> InstitutionalMetrics:
        """Return institutional metrics for an equity curve and trade list."""
        if starting_capital <= 0:
            raise ValueError("starting_capital must be positive")
        if periods_per_year <= 0:
            raise ValueError("periods_per_year must be positive")
        values = equity_values(equity_curve)
        returns = returns_from_equity(equity_curve)
        ending_equity = values[-1] if values else starting_capital
        total_return = _safe_div(ending_equity - starting_capital, starting_capital)
        annual_return = ((1.0 + total_return) ** _safe_div(periods_per_year, max(len(returns), 1))) - 1.0 if returns else 0.0
        mean_return = _mean(returns)
        volatility = _std(returns) * math.sqrt(periods_per_year)
        downside = [min(0.0, value) for value in returns]
        downside_std = _std(downside) * math.sqrt(periods_per_year)
        max_dd_amount, max_dd_pct, dd_duration = max_drawdown(values)
        dd = drawdown_series(values)
        ulcer_index = math.sqrt(_mean([value * value for value in dd])) if dd else 0.0
        sharpe = _safe_div(mean_return, _std(returns)) * math.sqrt(periods_per_year) if returns else 0.0
        sortino = _safe_div(mean_return, _std(downside)) * math.sqrt(periods_per_year) if downside else 0.0
        calmar = _safe_div(annual_return, max_dd_pct)
        mar = calmar
        gains = [value for value in returns if value > 0]
        losses = [-value for value in returns if value < 0]
        omega = _safe_div(sum(gains), sum(losses)) if losses else (math.inf if gains else 0.0)
        net_pnls = [float(trade.net_pnl) for trade in trades]
        wins = [value for value in net_pnls if value > 0]
        losses_pnl = [value for value in net_pnls if value < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses_pnl))
        profit_factor = None if gross_loss == 0 else gross_profit / gross_loss
        expectancy = _mean(net_pnls)
        pnl_std = _std(net_pnls)
        sqn = math.sqrt(len(net_pnls)) * _safe_div(expectancy, pnl_std) if net_pnls else 0.0
        beta = None
        alpha = None
        tracking_error = None
        information_ratio = None
        treynor = None
        if benchmark_returns:
            aligned = min(len(returns), len(benchmark_returns))
            if aligned > 1:
                asset = returns[:aligned]
                benchmark = list(benchmark_returns[:aligned])
                bmean = _mean(benchmark)
                amean = _mean(asset)
                variance = sum((value - bmean) ** 2 for value in benchmark) / (aligned - 1)
                covariance = sum((a - amean) * (b - bmean) for a, b in zip(asset, benchmark)) / (aligned - 1)
                beta = covariance / variance if variance else 0.0
                alpha = (amean - beta * bmean) * periods_per_year
                active = [a - b for a, b in zip(asset, benchmark)]
                tracking_error = _std(active) * math.sqrt(periods_per_year)
                information_ratio = _safe_div(_mean(active) * periods_per_year, tracking_error)
                treynor = _safe_div(annual_return, beta) if beta else None
        value_at_risk = percentile(returns, 0.05) if returns else 0.0
        tail = [value for value in returns if value <= value_at_risk]
        cvar = _mean(tail) if tail else value_at_risk
        exposure = len([value for value in values if value != starting_capital]) / len(values) if values else 0.0
        recovery_factor = _safe_div(ending_equity - starting_capital, max_dd_amount)
        rolling_cagr = rolling(returns, rolling_window, lambda window_values: (1 + sum(window_values)) ** _safe_div(periods_per_year, len(window_values)) - 1) if returns else ()
        rolling_sharpe = rolling(returns, rolling_window, lambda window_values: _safe_div(_mean(window_values), _std(window_values)) * math.sqrt(periods_per_year)) if returns else ()
        rolling_volatility = rolling(returns, rolling_window, lambda window_values: _std(window_values) * math.sqrt(periods_per_year)) if returns else ()
        return InstitutionalMetrics(
            sharpe=sharpe,
            sortino=sortino,
            calmar=calmar,
            omega=omega,
            mar=mar,
            ulcer_index=ulcer_index,
            profit_factor=profit_factor,
            expectancy=expectancy,
            sqn=sqn,
            alpha=alpha,
            beta=beta,
            tracking_error=tracking_error,
            information_ratio=information_ratio,
            treynor=treynor,
            var=value_at_risk,
            cvar=cvar,
            exposure=exposure,
            recovery_factor=recovery_factor,
            max_drawdown=max_dd_amount,
            max_drawdown_pct=max_dd_pct,
            drawdown_duration=dd_duration,
            rolling_cagr=rolling_cagr,
            rolling_sharpe=rolling_sharpe,
            rolling_volatility=rolling_volatility,
        )


def metric_mapping(metrics: InstitutionalMetrics) -> dict[str, float | None]:
    """Return institutional metrics as primitive mapping."""
    return metrics.to_mapping()


__all__ = [
    "InstitutionalMetrics",
    "InstitutionalMetricsEngine",
    "RollingMetricPoint",
    "drawdown_series",
    "equity_values",
    "max_drawdown",
    "metric_mapping",
    "percentile",
    "returns_from_equity",
]
