"""Report — format performance metrics into a dict and a Markdown/text report.

Pure formatting; no charting dependency.
"""

from __future__ import annotations

from typing import Any, Dict

from backend.app.trading.backtesting.metrics import PerformanceMetrics


def metrics_to_dict(metrics: PerformanceMetrics) -> Dict[str, Any]:
    return {
        "starting_equity": metrics.starting_equity,
        "ending_equity": metrics.ending_equity,
        "total_return": metrics.total_return,
        "total_pnl": metrics.total_pnl,
        "max_drawdown": metrics.max_drawdown,
        "max_drawdown_pct": metrics.max_drawdown_pct,
        "num_trades": metrics.num_trades,
        "wins": metrics.wins,
        "losses": metrics.losses,
        "win_rate": metrics.win_rate,
        "avg_win": metrics.avg_win,
        "avg_loss": metrics.avg_loss,
        "profit_factor": metrics.profit_factor,
        "expectancy": metrics.expectancy,
        "avg_bars_held": metrics.avg_bars_held,
        "largest_win": metrics.largest_win,
        "largest_loss": metrics.largest_loss,
        "gross_pnl": metrics.gross_pnl,
        "net_pnl": metrics.net_pnl,
        "total_brokerage": metrics.total_brokerage,
        "total_slippage": metrics.total_slippage,
        "sharpe": metrics.sharpe,
        "sortino": metrics.sortino,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.4f}"
    return str(value)


def format_report(metrics: PerformanceMetrics, title: str = "Backtest Report") -> str:
    rows = [
        ("Starting equity", metrics.starting_equity),
        ("Ending equity", metrics.ending_equity),
        ("Total return", metrics.total_return),
        ("Total PnL", metrics.total_pnl),
        ("Gross PnL", metrics.gross_pnl),
        ("Net PnL", metrics.net_pnl),
        ("Max drawdown", metrics.max_drawdown),
        ("Max drawdown %", metrics.max_drawdown_pct),
        ("Trades", metrics.num_trades),
        ("Wins", metrics.wins),
        ("Losses", metrics.losses),
        ("Win rate", metrics.win_rate),
        ("Avg win", metrics.avg_win),
        ("Avg loss", metrics.avg_loss),
        ("Profit factor", metrics.profit_factor),
        ("Expectancy", metrics.expectancy),
        ("Avg bars held", metrics.avg_bars_held),
        ("Largest win", metrics.largest_win),
        ("Largest loss", metrics.largest_loss),
        ("Total brokerage", metrics.total_brokerage),
        ("Total slippage", metrics.total_slippage),
        ("Sharpe", metrics.sharpe),
        ("Sortino", metrics.sortino),
    ]
    lines = [f"# {title}", "", "| Metric | Value |", "| --- | --- |"]
    lines += [f"| {label} | {_fmt(value)} |" for label, value in rows]
    return "\n".join(lines)
