from __future__ import annotations

from datetime import datetime, timedelta

from backend.app.trading.backtesting.metrics import compute_metrics
from backend.app.trading.backtesting.report import format_report, metrics_to_dict
from backend.app.trading.execution.position import Trade
from backend.app.trading.portfolio.portfolio import EquityPoint

TS = datetime(2024, 1, 1)


def eq_curve(values):
    return [EquityPoint(TS + timedelta(minutes=i), v) for i, v in enumerate(values)]


def make_trade(net, gross=None, bars=2):
    g = gross if gross is not None else net
    return Trade(
        symbol="X", strategy_name="s", brick_type="t", brick_size=1.0, timeframe="renko",
        direction="long", quantity=1.0, entry_price=100.0, exit_price=100.0 + net,
        entry_time=TS, exit_time=TS, entry_cost=0.0, exit_cost=0.0,
        gross_pnl=g, net_pnl=net, return_pct=net / 100.0, bars_held=bars,
    )


def test_max_drawdown_and_return():
    m = compute_metrics(eq_curve([100, 120, 90, 110, 80]), [], starting_capital=100)
    assert m.max_drawdown == 120 - 80  # 40 (peak 120 -> trough 80)
    assert abs(m.max_drawdown_pct - (40 / 120)) < 1e-9
    assert abs(m.total_return - (-0.2)) < 1e-9
    assert m.ending_equity == 80
    assert m.total_pnl == -20


def test_trade_statistics():
    trades = [make_trade(100), make_trade(-50), make_trade(30), make_trade(-20)]
    m = compute_metrics(eq_curve([100, 200]), trades, starting_capital=100)
    assert m.num_trades == 4
    assert m.wins == 2 and m.losses == 2
    assert m.win_rate == 0.5
    assert m.avg_win == 65.0          # (100+30)/2
    assert m.avg_loss == -35.0        # (-50-20)/2
    assert abs(m.profit_factor - (130 / 70)) < 1e-9
    assert m.expectancy == 15.0       # mean of nets
    assert m.largest_win == 100 and m.largest_loss == -50
    assert m.avg_bars_held == 2.0


def test_profit_factor_none_when_no_losses():
    m = compute_metrics(eq_curve([100, 110]), [make_trade(10), make_trade(20)], starting_capital=100)
    assert m.profit_factor is None


def test_empty_inputs_are_safe():
    m = compute_metrics([], [], starting_capital=1000)
    assert m.num_trades == 0
    assert m.win_rate == 0.0
    assert m.max_drawdown == 0.0
    assert m.ending_equity == 1000
    assert m.sharpe == 0.0 and m.sortino == 0.0


def test_sharpe_and_sortino_positive_for_rising_curve():
    m = compute_metrics(eq_curve([100, 110, 121, 133]), [], starting_capital=100)
    assert m.sharpe > 0
    # No negative returns -> sortino falls back to 0 (no downside deviation).
    assert m.sortino == 0.0


def test_report_dict_and_text():
    m = compute_metrics(eq_curve([100, 110]), [make_trade(10)], starting_capital=100,
                        total_brokerage=1.0, total_slippage=2.0)
    d = metrics_to_dict(m)
    assert d["total_brokerage"] == 1.0 and d["total_slippage"] == 2.0
    assert "sharpe" in d and "profit_factor" in d
    text = format_report(m, title="My Report")
    assert "# My Report" in text
    assert "Profit factor | n/a" in text  # single winning trade -> no losses -> n/a
    assert "Total slippage" in text
