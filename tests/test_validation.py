from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from backend.app.chart.renko.models import Brick, BrickDirection
from backend.app.trading.validation import ranking, report
from backend.app.trading.validation.dataset import (
    CachingBrickDataSource,
    InMemoryBrickDataSource,
)
from backend.app.trading.validation.matrix import ValidationMatrix
from backend.app.trading.validation.results import (
    METRIC_KEYS,
    ResultSet,
    ScenarioResult,
    metrics_from_performance,
)
from backend.app.trading.validation.runner import (
    ValidationRunner,
    _build_brokerage,
    _build_slippage,
)
from backend.app.trading.validation.scenario import (
    BrickSpec,
    MarketInfo,
    RiskSettings,
    Scenario,
    ScenarioStatus,
)
from backend.app.trading.backtesting.metrics import compute_metrics
from backend.app.trading.costs.brokerage import (
    FixedBrokerage,
    PercentageBrokerage,
    PerShareBrokerage,
    ZeroBrokerage,
)
from backend.app.trading.costs.slippage import (
    FixedSlippage,
    PercentageSlippage,
    ZeroSlippage,
)
from backend.app.trading.execution.position import Trade
from backend.app.trading.portfolio.portfolio import EquityPoint

TS = datetime(2024, 1, 1)


def brick(i, c):
    return Brick(f"b{i}", BrickDirection.UP, c, float(c), float(c), float(c),
                 0.0, TS + timedelta(minutes=i), {})


def make_series():
    closes = [100] * 9 + [200, 300, 50, 40, 300, 60, 500, 50, 600]
    return [brick(i, c) for i, c in enumerate(closes)]


# =====================================================================
# Scenario
# =====================================================================

def test_scenario_is_immutable_and_has_id():
    s = Scenario.create("ema_crossover", {"period": 10}, brick=BrickSpec(brick_size=2.0),
                        symbol="AAA", dataset_id="d1")
    assert s.scenario_id
    assert s.params == {"period": 10}
    with pytest.raises(Exception):
        s.symbol = "ZZZ"  # frozen


def test_scenario_id_stable_and_distinct():
    a = Scenario.create("ema_crossover", {"period": 10}, symbol="AAA", dataset_id="d1")
    b = Scenario.create("ema_crossover", {"period": 10}, symbol="AAA", dataset_id="d1")
    c = Scenario.create("ema_crossover", {"period": 12}, symbol="AAA", dataset_id="d1")
    assert a.scenario_id == b.scenario_id
    assert a == b
    assert a.scenario_id != c.scenario_id


def test_scenario_market_metadata():
    s = Scenario.create("ema_crossover", {"period": 10},
                        market=MarketInfo("NYSE", "equities", "USD"))
    assert s.market.exchange == "NYSE"
    assert s.market.market == "equities"
    assert s.market.currency == "USD"


# =====================================================================
# Matrix
# =====================================================================

def test_matrix_cartesian_cardinality():
    m = (ValidationMatrix()
         .add_strategy("ema_crossover", period=[5, 8, 10, 12, 20, 30])
         .with_bricks(BrickSpec(brick_size=1.0), BrickSpec(brick_size=2.0),
                      BrickSpec(brick_size=3.0), BrickSpec(brick_size=4.0))
         .with_symbols("AAA", "BBB", "CCC")
         .with_datasets("d1", "d2"))
    assert m.count() == 6 * 4 * 3 * 2  # 144


def test_matrix_is_deterministic_and_dedups():
    def build():
        return (ValidationMatrix()
                .add_strategy("ema_crossover", period=[5, 10])
                .with_bricks(BrickSpec())
                .with_symbols("AAA")
                .with_datasets("d1"))
    a = [s.scenario_id for s in build().scenarios()]
    b = [s.scenario_id for s in build().scenarios()]
    assert a == b
    # Duplicate symbol axis collapses via dedup.
    m = build().with_symbols("AAA", "AAA")
    assert len(m.scenarios()) == 2  # still 2 periods, dup symbol removed


def test_matrix_empty_param_grid_gives_one_combo():
    m = (ValidationMatrix().add_strategy("ema_crossover")
         .with_bricks(BrickSpec()).with_symbols("AAA").with_datasets("d1"))
    scns = m.scenarios()
    assert len(scns) == 1
    assert scns[0].params == {}


def test_matrix_filter_drops_scenarios():
    m = (ValidationMatrix().add_strategy("ema_crossover", period=[5, 10, 20])
         .with_bricks(BrickSpec()).with_symbols("AAA").with_datasets("d1")
         .filter(lambda s: s.params.get("period", 0) >= 10))
    assert m.count() == 2


# =====================================================================
# BrickDataSource
# =====================================================================

def test_in_memory_data_source_register_and_get():
    ds = InMemoryBrickDataSource()
    series = make_series()
    ds.register(symbol="AAA", dataset_id="d1", bricks=series, brick=BrickSpec())
    got = ds.get_bricks(symbol="AAA", dataset_id="d1", brick=BrickSpec())
    assert len(got) == len(series)
    with pytest.raises(KeyError):
        ds.get_bricks(symbol="ZZZ", dataset_id="d1", brick=BrickSpec())


def test_caching_data_source_loads_once():
    series = make_series()
    calls = {"n": 0}

    def loader(symbol, dataset_id, brick, date_range):
        calls["n"] += 1
        return series

    ds = CachingBrickDataSource(loader)
    a = ds.get_bricks(symbol="AAA", dataset_id="d1", brick=BrickSpec())
    b = ds.get_bricks(symbol="AAA", dataset_id="d1", brick=BrickSpec())
    assert a == b
    assert calls["n"] == 1            # loaded once, reused
    assert ds.load_count == 1
    ds.get_bricks(symbol="BBB", dataset_id="d1", brick=BrickSpec())
    assert ds.load_count == 2         # different key -> new load


# =====================================================================
# Results
# =====================================================================

def _perf():
    eq = [EquityPoint(TS, 100.0), EquityPoint(TS, 110.0)]
    trades = [Trade("X", "ema_crossover", "traditional", 1.0, "renko", "long",
                    1.0, 100.0, 110.0, TS, TS, 0.0, 0.0, 10.0, 10.0, 0.1, 2)]
    return compute_metrics(eq, trades, starting_capital=100.0)


def test_metrics_from_performance_maps_all_keys():
    metrics = metrics_from_performance(_perf())
    for key in METRIC_KEYS:
        assert key in metrics
    assert metrics["total_trades"] == 1
    assert metrics["net_profit"] == metrics["total_pnl"] or metrics["net_profit"] == 10.0


def test_scenario_result_record_shape():
    s = Scenario.create("ema_crossover", {"period": 10}, symbol="AAA", dataset_id="d1",
                        market=MarketInfo("NYSE", "equities", "USD"))
    r = ScenarioResult(s, ScenarioStatus.COMPLETED, metrics_from_performance(_perf()))
    rec = r.to_record()
    assert rec["strategy"] == "ema_crossover"
    assert rec["exchange"] == "NYSE" and rec["currency"] == "USD"
    assert rec["status"] == "completed"
    assert "profit_factor" in rec
    assert r.completed is True


def test_result_set_completed_failed_partition():
    s = Scenario.create("ema_crossover", {"period": 10})
    ok = ScenarioResult(s, ScenarioStatus.COMPLETED, {})
    bad = ScenarioResult(s, ScenarioStatus.FAILED, {}, error="boom")
    rs = ResultSet([ok, bad])
    assert len(rs) == 2
    assert rs.completed() == [ok]
    assert rs.failed() == [bad]
    assert rs[0] is ok


# =====================================================================
# Runner (reuses the real, frozen BacktestEngine)
# =====================================================================

def _matrix_and_source():
    ds = InMemoryBrickDataSource()
    series = make_series()
    for sym in ("AAA", "BBB"):
        ds.register(symbol=sym, dataset_id="d1", bricks=series, brick=BrickSpec())
    m = (ValidationMatrix()
         .add_strategy("ema_crossover", period=[5, 10, 20])
         .with_bricks(BrickSpec())
         .with_symbols("AAA", "BBB")
         .with_datasets("d1")
         .with_risk(RiskSettings(starting_capital=1_000_000, fixed_quantity=1)))
    return m, ds


def test_runner_runs_all_scenarios_via_real_engine():
    m, ds = _matrix_and_source()
    rs = ValidationRunner(ds).run(m.scenarios())
    assert len(rs) == m.count() == 6
    assert len(rs.completed()) == 6
    assert all(r.metrics["total_trades"] >= 0 for r in rs)


def test_runner_is_deterministic():
    m, ds = _matrix_and_source()
    a = [(r.scenario.scenario_id, r.metrics) for r in ValidationRunner(ds).run(m.scenarios())]
    b = [(r.scenario.scenario_id, r.metrics) for r in ValidationRunner(ds).run(m.scenarios())]
    assert a == b


def test_runner_captures_failures_without_aborting():
    ds = InMemoryBrickDataSource()  # nothing registered -> get_bricks raises
    m = (ValidationMatrix().add_strategy("ema_crossover", period=[5, 10])
         .with_bricks(BrickSpec()).with_symbols("AAA").with_datasets("d1"))
    rs = ValidationRunner(ds).run(m.scenarios())
    assert len(rs) == 2
    assert len(rs.failed()) == 2
    assert all(r.error for r in rs.failed())


def test_runner_cost_builders():
    assert isinstance(_build_brokerage(RiskSettings(brokerage="zero")), ZeroBrokerage)
    assert isinstance(_build_brokerage(RiskSettings(brokerage="fixed", brokerage_value=1)), FixedBrokerage)
    assert isinstance(_build_brokerage(RiskSettings(brokerage="percentage", brokerage_value=0.01)), PercentageBrokerage)
    assert isinstance(_build_brokerage(RiskSettings(brokerage="per_share", brokerage_value=0.01)), PerShareBrokerage)
    assert isinstance(_build_slippage(RiskSettings(slippage="zero")), ZeroSlippage)
    assert isinstance(_build_slippage(RiskSettings(slippage="fixed", slippage_value=0.1)), FixedSlippage)
    assert isinstance(_build_slippage(RiskSettings(slippage="percentage", slippage_value=0.001)), PercentageSlippage)


# =====================================================================
# Ranking
# =====================================================================

def _result(pid, **metrics):
    s = Scenario.create("ema_crossover", {"period": pid})
    base = {k: 0.0 for k in METRIC_KEYS}
    base.update(metrics)
    return ScenarioResult(s, ScenarioStatus.COMPLETED, base)


def test_rank_by_higher_is_better():
    rs = ResultSet([_result(1, profit_factor=1.2), _result(2, profit_factor=2.5),
                    _result(3, profit_factor=1.8)])
    ranked = ranking.rank_by(rs, "profit_factor")
    assert [e.result.scenario.params["period"] for e in ranked] == [2, 3, 1]
    assert ranked[0].rank == 1


def test_rank_by_lower_is_better_metric():
    rs = ResultSet([_result(1, max_drawdown_pct=0.30), _result(2, max_drawdown_pct=0.10),
                    _result(3, max_drawdown_pct=0.20)])
    ranked = ranking.rank_by(rs, "max_drawdown_pct")
    assert [e.result.scenario.params["period"] for e in ranked] == [2, 3, 1]


def test_rank_treats_none_metric_as_worst():
    rs = ResultSet([_result(1, profit_factor=None), _result(2, profit_factor=1.5)])
    ranked = ranking.rank_by(rs, "profit_factor")
    assert ranked[0].result.scenario.params["period"] == 2  # valid first
    assert ranked[-1].result.scenario.params["period"] == 1  # None last


def test_composite_score_orders_by_weighted_blend():
    rs = ResultSet([
        _result(1, profit_factor=1.0, expectancy=1.0, max_drawdown_pct=0.5),
        _result(2, profit_factor=2.0, expectancy=2.0, max_drawdown_pct=0.1),  # best
        _result(3, profit_factor=1.5, expectancy=1.5, max_drawdown_pct=0.3),
    ])
    ranked = ranking.composite_score(rs, {"profit_factor": 1.0, "expectancy": 1.0,
                                          "max_drawdown_pct": 1.0})
    assert ranked[0].result.scenario.params["period"] == 2
    assert ranked[0].rank == 1
    assert ranked[0].value >= ranked[-1].value


def test_composite_score_empty_weights_safe():
    rs = ResultSet([_result(1, profit_factor=1.0)])
    ranked = ranking.composite_score(rs, {})
    assert len(ranked) == 1 and ranked[0].value == 0.0


def test_matrix_optional_axes_and_defaults():
    m = (ValidationMatrix().add_strategy("ema_crossover", period=[5])
         .with_bricks(BrickSpec()).with_symbols("AAA").with_datasets("d1")
         .with_date_ranges(("2024-01-01", "2024-06-01"))
         .with_markets(MarketInfo("NASDAQ", "equities", "USD")))
    scns = m.scenarios()
    assert scns[0].date_range == ("2024-01-01", "2024-06-01")
    assert scns[0].market.exchange == "NASDAQ"
    # Empty args fall back to defaults.
    m2 = (ValidationMatrix().add_strategy("ema_crossover", period=[5])
          .with_bricks(BrickSpec()).with_symbols("AAA").with_datasets("d1")
          .with_date_ranges().with_risk().with_markets())
    s2 = m2.scenarios()[0]
    assert s2.date_range == (None, None)
    assert s2.market == MarketInfo()


def test_result_set_add_and_metric_accessor():
    rs = ResultSet()
    s = Scenario.create("ema_crossover", {"period": 10})
    r = ScenarioResult(s, ScenarioStatus.COMPLETED, {"sharpe": 1.5})
    rs.add(r)
    assert len(rs) == 1
    assert r.metric("sharpe") == 1.5
    assert r.metric("missing") is None
    assert rs.results[0] is r


def test_composite_score_all_none_metric_column():
    rs = ResultSet([_result(1, profit_factor=None), _result(2, profit_factor=None)])
    ranked = ranking.composite_score(rs, {"profit_factor": 1.0})
    assert len(ranked) == 2  # does not crash; worst fallback applied


# =====================================================================
# Report
# =====================================================================

def _small_resultset():
    m, ds = _matrix_and_source()
    return ValidationRunner(ds).run(m.scenarios())


def test_report_json_parses():
    rs = _small_resultset()
    data = json.loads(report.to_json(rs))
    assert len(data) == len(rs)
    assert "scenario_id" in data[0]


def test_report_csv_header_and_rows():
    rs = _small_resultset()
    lines = report.to_csv(rs).splitlines()
    assert lines[0].startswith("scenario_id")
    assert len(lines) == len(rs) + 1  # header + rows


def test_report_csv_empty():
    assert report.to_csv(ResultSet([])) == ""


def test_report_markdown_contains_table():
    rs = _small_resultset()
    md = report.to_markdown(rs, title="My Validation")
    assert "# My Validation" in md
    assert "profit_factor" in md


def test_ranked_to_markdown():
    rs = _small_resultset()
    ranked = ranking.composite_score(rs, {"profit_factor": 1.0, "expectancy": 1.0})
    md = report.ranked_to_markdown(ranked, title="Ranked")
    assert "# Ranked" in md
    assert md.count("\n") >= len(ranked)
