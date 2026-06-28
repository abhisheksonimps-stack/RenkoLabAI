"""Performance metrics — pure functions over the equity curve and closed trades.

Conventions (documented): risk-free rate = 0; returns are per-brick (not
annualized); drawdown is computed on the equity curve. No I/O, no randomness.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

from backend.app.trading.execution.position import Trade
from backend.app.trading.portfolio.portfolio import EquityPoint


@dataclass(frozen=True)
class PerformanceMetrics:
    starting_equity: float
    ending_equity: float
    total_return: float
    total_pnl: float
    max_drawdown: float
    max_drawdown_pct: float
    num_trades: int
    wins: int
    losses: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: Optional[float]
    expectancy: float
    avg_bars_held: float
    largest_win: float
    largest_loss: float
    gross_pnl: float
    net_pnl: float
    total_brokerage: float
    total_slippage: float
    sharpe: float
    sortino: float


def _equity_values(equity_curve: Sequence[EquityPoint]) -> List[float]:
    return [p.equity for p in equity_curve]


def _max_drawdown(values: Sequence[float]) -> tuple[float, float]:
    peak = None
    max_dd = 0.0
    max_dd_pct = 0.0
    for v in values:
        if peak is None or v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = (dd / peak) if peak else 0.0
    return max_dd, max_dd_pct


def _returns(values: Sequence[float]) -> List[float]:
    out = []
    for prev, cur in zip(values, values[1:]):
        if prev != 0:
            out.append((cur - prev) / prev)
    return out


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def compute_metrics(
    equity_curve: Sequence[EquityPoint],
    trades: Sequence[Trade],
    starting_capital: float,
    total_brokerage: float = 0.0,
    total_slippage: float = 0.0,
) -> PerformanceMetrics:
    values = _equity_values(equity_curve)
    starting_equity = float(starting_capital)
    ending_equity = values[-1] if values else starting_equity
    total_pnl = ending_equity - starting_equity
    total_return = (total_pnl / starting_equity) if starting_equity else 0.0

    max_dd, max_dd_pct = _max_drawdown(values)

    nets = [t.net_pnl for t in trades]
    grosses = [t.gross_pnl for t in trades]
    win_nets = [n for n in nets if n > 0]
    loss_nets = [n for n in nets if n < 0]
    num_trades = len(trades)
    wins = len(win_nets)
    losses = len(loss_nets)
    win_rate = (wins / num_trades) if num_trades else 0.0
    avg_win = _mean(win_nets)
    avg_loss = _mean(loss_nets)
    gross_profit = sum(win_nets)
    gross_loss = abs(sum(loss_nets))
    if gross_loss > 0:
        profit_factor: Optional[float] = gross_profit / gross_loss
    else:
        profit_factor = None  # undefined when there are no losing trades
    expectancy = _mean(nets)
    avg_bars_held = _mean([t.bars_held for t in trades])
    largest_win = max(nets) if nets else 0.0
    largest_loss = min(nets) if nets else 0.0

    rets = _returns(values)
    mean_r = _mean(rets)
    std_r = _std(rets)
    sharpe = (mean_r / std_r) if std_r > 0 else 0.0
    downside = [r for r in rets if r < 0]
    dstd = _std(downside)
    sortino = (mean_r / dstd) if dstd > 0 else 0.0

    return PerformanceMetrics(
        starting_equity=starting_equity,
        ending_equity=ending_equity,
        total_return=total_return,
        total_pnl=total_pnl,
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
        num_trades=num_trades,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=profit_factor,
        expectancy=expectancy,
        avg_bars_held=avg_bars_held,
        largest_win=largest_win,
        largest_loss=largest_loss,
        gross_pnl=sum(grosses),
        net_pnl=sum(nets),
        total_brokerage=float(total_brokerage),
        total_slippage=float(total_slippage),
        sharpe=sharpe,
        sortino=sortino,
    )
