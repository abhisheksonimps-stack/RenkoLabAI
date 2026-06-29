"""Monte Carlo research simulation."""

from __future__ import annotations

import random
from typing import Sequence

from backend.app.trading.backtesting.research.metrics import max_drawdown, percentile
from backend.app.trading.backtesting.research.models import (
    MonteCarloConfig,
    MonteCarloMethod,
    MonteCarloPath,
    MonteCarloResult,
)
from backend.app.trading.execution.position import Trade


class TradeMonteCarloSimulator:
    """Deterministic Monte Carlo simulator for closed trade sequences."""

    def simulate(self, trades: Sequence[Trade], config: MonteCarloConfig) -> MonteCarloResult:
        """Run trade-order or bootstrap simulation over trade net PnL values."""
        pnls = [float(trade.net_pnl) for trade in trades]
        rng = random.Random(config.seed)
        paths: list[MonteCarloPath] = []
        ruin_level = config.starting_equity * config.ruin_threshold
        for index in range(config.iterations):
            sampled = self._sample(pnls, config.method, rng)
            curve = self._equity_curve(config.starting_equity, sampled)
            max_dd, max_dd_pct, _ = max_drawdown(curve)
            ending = curve[-1] if curve else config.starting_equity
            paths.append(
                MonteCarloPath(
                    index=index,
                    ending_equity=ending,
                    max_drawdown=max_dd,
                    max_drawdown_pct=max_dd_pct,
                    ruined=any(value <= ruin_level for value in curve),
                )
            )
        ending_values = [path.ending_equity for path in paths]
        confidence = {
            f"p{int(level * 100)}": percentile(ending_values, level)
            for level in sorted(config.confidence_levels)
        }
        probability_of_ruin = sum(1 for path in paths if path.ruined) / len(paths) if paths else 0.0
        drawdowns = tuple(path.max_drawdown_pct for path in paths)
        return MonteCarloResult(
            config=config,
            paths=tuple(paths),
            confidence_intervals=confidence,
            probability_of_ruin=probability_of_ruin,
            drawdown_distribution=drawdowns,
        )

    @staticmethod
    def _sample(pnls: Sequence[float], method: MonteCarloMethod, rng: random.Random) -> list[float]:
        if not pnls:
            return []
        if method is MonteCarloMethod.BOOTSTRAP:
            return [rng.choice(pnls) for _ in pnls]
        sampled = list(pnls)
        rng.shuffle(sampled)
        return sampled

    @staticmethod
    def _equity_curve(starting_equity: float, pnls: Sequence[float]) -> list[float]:
        equity = starting_equity
        curve = [equity]
        for pnl in pnls:
            equity += pnl
            curve.append(equity)
        return curve


__all__ = ["TradeMonteCarloSimulator"]
