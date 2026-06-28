from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from backend.app.marketdata.adapters.base import (
    MarketDataAdapter,
    apply_adjustment,
    normalize_bars,
)
from backend.app.marketdata.adapters.csv import CsvAdapter
from backend.app.marketdata.adapters.yahoo import YahooAdapter
from backend.app.marketdata.cache import MarketDataCache
from backend.app.marketdata.errors import (
    AdapterNotFound,
    DataUnavailable,
    MalformedData,
    NotSupported,
    RateLimited,
)
from backend.app.marketdata.loader import HistoricalLoader
from backend.app.marketdata.models import (
    AdjustmentPolicy,
    AssetClass,
    MarketBar,
    MarketCalendar,
    MarketDataRequest,
    to_utc,
)
from backend.app.marketdata.provider import MarketDataProvider
from backend.app.marketdata.registry import AdapterRegistry, default_registry

UTC = timezone.utc


def bar(ts="2024-01-01", o=10, h=11, l=9, c=10, v=100, **kw):
    return MarketBar.create(symbol="X", timestamp=ts, open=o, high=h, low=l, close=c, volume=v, **kw)


# =====================================================================
# Models
# =====================================================================

def test_to_utc_variants():
    naive = datetime(2024, 1, 1, 12)
    assert to_utc(naive).tzinfo == UTC
    aware = datetime(2024, 1, 1, 12, tzinfo=UTC)
    assert to_utc(aware) == aware
    assert to_utc("2024-01-01T00:00:00").tzinfo == UTC
    with pytest.raises(MalformedData):
        to_utc("not-a-date")
    with pytest.raises(MalformedData):
        to_utc(12345)


def test_marketbar_valid_and_utc():
    b = bar()
    assert b.timestamp.tzinfo == UTC
    assert b.asset_class is AssetClass.EQUITY


def test_marketbar_rejects_naive_timestamp():
    with pytest.raises(MalformedData):
        MarketBar(symbol="X", timestamp=datetime(2024, 1, 1), open=1, high=1, low=1, close=1, volume=0)


@pytest.mark.parametrize("o,h,l,c,v", [
    (10, 11, 9, 12, 100),   # close above high
    (10, 9, 9, 10, 100),    # high < open
    (-1, 1, -1, 0, 100),    # negative price
    (10, 11, 9, 10, -5),    # negative volume
])
def test_marketbar_invalid_ohlc(o, h, l, c, v):
    with pytest.raises(MalformedData):
        MarketBar.create(symbol="X", timestamp="2024-01-01", open=o, high=h, low=l, close=c, volume=v)


def test_enums_and_request_cache_key():
    assert {a.value for a in AssetClass} == {"equity", "commodity", "crypto", "forex"}
    assert {p.value for p in AdjustmentPolicy} == {"raw", "adjusted"}
    r1 = MarketDataRequest(symbol="X", source="csv", adjustment=AdjustmentPolicy.RAW)
    r2 = MarketDataRequest(symbol="X", source="csv", adjustment=AdjustmentPolicy.ADJUSTED)
    assert r1.cache_key() != r2.cache_key()         # adjustment is part of identity
    assert r1.cache_key() == MarketDataRequest(symbol="X", source="csv",
                                               adjustment=AdjustmentPolicy.RAW).cache_key()


def test_market_calendar_is_abstract():
    with pytest.raises(TypeError):
        MarketCalendar()  # cannot instantiate the reserved extension point


# =====================================================================
# Adjustment + normalization helpers
# =====================================================================

def test_apply_adjustment_equity_adjusted_scales():
    o, h, l, c = apply_adjustment(20, 22, 19, 20, 10, AdjustmentPolicy.ADJUSTED, AssetClass.EQUITY)
    assert (o, h, l, c) == (10.0, 11.0, 9.5, 10)  # factor 0.5


def test_apply_adjustment_raw_or_non_equity_or_missing():
    raw = apply_adjustment(20, 22, 19, 20, 10, AdjustmentPolicy.RAW, AssetClass.EQUITY)
    assert raw == (20, 22, 19, 20)
    crypto = apply_adjustment(20, 22, 19, 20, 10, AdjustmentPolicy.ADJUSTED, AssetClass.CRYPTO)
    assert crypto == (20, 22, 19, 20)
    no_adj = apply_adjustment(20, 22, 19, 20, None, AdjustmentPolicy.ADJUSTED, AssetClass.EQUITY)
    assert no_adj == (20, 22, 19, 20)
    zero_close = apply_adjustment(20, 22, 19, 0, 10, AdjustmentPolicy.ADJUSTED, AssetClass.EQUITY)
    assert zero_close == (20, 22, 19, 0)


def test_normalize_bars_dedup_last_and_sort():
    b1 = bar(ts="2024-01-02", o=10, h=11, l=9, c=10)
    b2 = bar(ts="2024-01-01", o=20, h=22, l=19, c=20)
    dup = bar(ts="2024-01-02", o=15, h=16, l=14, c=15)  # same ts as b1 -> last wins
    out = normalize_bars([b1, b2, dup])
    assert [b.timestamp.day for b in out] == [1, 2]
    assert out[1].close == 15.0


# =====================================================================
# CSV adapter
# =====================================================================

CSV = ("timestamp,open,high,low,close,adj_close,volume\n"
       "2024-01-02,10,11,9,10,5,100\n"
       "2024-01-01,20,22,19,20,10,200\n")


def csv_request(adjustment=AdjustmentPolicy.RAW, asset=AssetClass.EQUITY, text=CSV):
    return MarketDataRequest(symbol="AAA", source="csv", asset_class=asset,
                             adjustment=adjustment, extra={"text": text})


def test_csv_raw_fetch():
    bars = CsvAdapter().fetch(csv_request(AdjustmentPolicy.RAW))
    assert [b.close for b in bars] == [10.0, 20.0]  # adapter order; provider sorts
    assert all(b.source == "csv" for b in bars)


def test_csv_adjusted_fetch_scales():
    bars = CsvAdapter().fetch(csv_request(AdjustmentPolicy.ADJUSTED))
    # row1 close 10 -> adj 5 (factor .5), row2 close 20 -> adj 10 (factor .5)
    assert [b.close for b in bars] == [5.0, 10.0]
    assert [b.open for b in bars] == [5.0, 10.0]


def test_csv_custom_column_map_and_datetime_format():
    text = "d;o;h;l;c;vol\n01-2024-02;10;11;9;10;100\n"
    adapter = CsvAdapter(
        column_map={"timestamp": "d", "open": "o", "high": "h", "low": "l", "close": "c", "volume": "vol"},
        datetime_format="%m-%Y-%d", delimiter=";",
    )
    req = MarketDataRequest(symbol="AAA", source="csv", extra={"text": text})
    bars = adapter.fetch(req)
    assert len(bars) == 1 and bars[0].close == 10.0


def test_csv_bad_timestamp_for_format_raises():
    text = "d,o,h,l,c,vol\nNOT-A-DATE,10,11,9,10,100\n"
    adapter = CsvAdapter(
        column_map={"timestamp": "d", "open": "o", "high": "h", "low": "l", "close": "c", "volume": "vol"},
        datetime_format="%Y-%m-%d",
    )
    with pytest.raises(MalformedData):
        adapter.fetch(MarketDataRequest(symbol="AAA", source="csv", extra={"text": text}))


def test_csv_missing_source_raises():
    with pytest.raises(DataUnavailable):
        CsvAdapter().fetch(MarketDataRequest(symbol="AAA", source="csv"))


def test_csv_malformed_row_raises():
    bad = "timestamp,open,high,low,close,volume\n2024-01-01,oops,11,9,10,100\n"
    with pytest.raises(MalformedData):
        CsvAdapter().fetch(csv_request(text=bad))


def test_csv_path_loading(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text(CSV, encoding="utf-8")
    bars = CsvAdapter().fetch(MarketDataRequest(symbol="AAA", source="csv", extra={"path": str(p)}))
    assert len(bars) == 2


# =====================================================================
# Yahoo adapter
# =====================================================================

def yahoo_rows(symbol, interval, start, end):
    return [{"timestamp": "2024-01-01T00:00:00", "open": 100, "high": 110, "low": 90,
             "close": 100, "adj_close": 50, "volume": 1000}]


def test_yahoo_adjusted_and_raw():
    req_adj = MarketDataRequest(symbol="MSFT", source="yahoo", adjustment=AdjustmentPolicy.ADJUSTED)
    adj = YahooAdapter(client=yahoo_rows).fetch(req_adj)
    assert adj[0].close == 50.0 and adj[0].open == 50.0  # scaled by 0.5
    req_raw = MarketDataRequest(symbol="MSFT", source="yahoo", adjustment=AdjustmentPolicy.RAW)
    raw = YahooAdapter(client=yahoo_rows).fetch(req_raw)
    assert raw[0].close == 100.0 and raw[0].open == 100.0


def test_yahoo_default_client_unavailable():
    with pytest.raises(DataUnavailable):
        YahooAdapter().fetch(MarketDataRequest(symbol="MSFT", source="yahoo"))


def test_yahoo_translates_generic_error():
    def boom(**kw):
        raise RuntimeError("network down")
    with pytest.raises(DataUnavailable):
        YahooAdapter(client=boom).fetch(MarketDataRequest(symbol="MSFT", source="yahoo"))


def test_yahoo_passes_through_typed_error():
    def limited(**kw):
        raise RateLimited("slow down")
    with pytest.raises(RateLimited):
        YahooAdapter(client=limited).fetch(MarketDataRequest(symbol="MSFT", source="yahoo"))


def test_yahoo_malformed_row():
    def bad(**kw):
        return [{"timestamp": "2024-01-01", "open": "x", "high": 1, "low": 1, "close": 1}]
    with pytest.raises(MalformedData):
        YahooAdapter(client=bad).fetch(MarketDataRequest(symbol="MSFT", source="yahoo"))


def test_yahoo_stream_not_supported():
    with pytest.raises(NotSupported):
        YahooAdapter(client=yahoo_rows).stream(MarketDataRequest(symbol="MSFT", source="yahoo"))


# =====================================================================
# Registry
# =====================================================================

def test_registry_basic_and_errors():
    reg = AdapterRegistry()
    reg.register("csv", lambda **kw: CsvAdapter(**kw))
    assert reg.exists("csv") and "csv" in reg.names()
    assert isinstance(reg.create("csv"), CsvAdapter)
    with pytest.raises(AdapterNotFound):
        reg.get("nope")
    with pytest.raises(ValueError):
        reg.register("", lambda **kw: CsvAdapter())


def test_default_registry_has_csv_and_yahoo():
    reg = default_registry()
    assert set(reg.names()) == {"csv", "yahoo"}


# =====================================================================
# Provider
# =====================================================================

def test_provider_routes_to_csv_and_sorts():
    bars = MarketDataProvider().get_history(csv_request(AdjustmentPolicy.RAW))
    assert [b.timestamp.day for b in bars] == [1, 2]  # normalized ascending


def test_provider_passes_adapter_kwargs_to_yahoo():
    prov = MarketDataProvider(yahoo={"client": yahoo_rows})
    bars = prov.get_history(MarketDataRequest(symbol="MSFT", source="yahoo",
                                              adjustment=AdjustmentPolicy.RAW))
    assert bars[0].close == 100.0


def test_provider_unknown_source():
    with pytest.raises(AdapterNotFound):
        MarketDataProvider().get_history(MarketDataRequest(symbol="X", source="ghost"))


def test_provider_supports_false_raises():
    class Picky(MarketDataAdapter):
        name = "picky"
        def fetch(self, request):
            return []
        def supports(self, request):
            return False
    reg = AdapterRegistry()
    reg.register("picky", lambda **kw: Picky())
    with pytest.raises(NotSupported):
        MarketDataProvider(reg).get_history(MarketDataRequest(symbol="X", source="picky"))


def test_provider_stream_delegates_not_supported():
    with pytest.raises(NotSupported):
        MarketDataProvider().stream(MarketDataRequest(symbol="X", source="csv"))


# =====================================================================
# Cache
# =====================================================================

def test_cache_set_get_has_clear():
    cache = MarketDataCache()
    req = csv_request()
    assert cache.has(req) is False
    cache.set(req, [bar()])
    assert cache.has(req) and len(cache) == 1
    got = cache.get(req)
    got.append(bar())                 # mutating the returned copy must not affect cache
    assert len(cache.get(req)) == 1
    cache.clear()
    assert len(cache) == 0


# =====================================================================
# Loader
# =====================================================================

class CountingProvider:
    def __init__(self, bars):
        self._bars = bars
        self.calls = 0

    def get_history(self, request):
        self.calls += 1
        return list(self._bars)


def test_loader_caches_load_once():
    provider = CountingProvider([bar(ts="2024-01-01"), bar(ts="2024-01-02")])
    loader = HistoricalLoader(provider=provider, cache=MarketDataCache())
    req = csv_request()
    a = loader.load(req)
    b = loader.load(req)
    assert [x.timestamp for x in a] == [x.timestamp for x in b]
    assert provider.calls == 1  # second load served from cache


def test_loader_without_cache_calls_each_time():
    provider = CountingProvider([bar()])
    loader = HistoricalLoader(provider=provider)
    loader.load(csv_request())
    loader.load(csv_request())
    assert provider.calls == 2


def test_loader_calendar_filters_sessions():
    provider = CountingProvider([bar(ts="2024-01-01"), bar(ts="2024-01-02")])
    loader = HistoricalLoader(provider=provider)

    class OnlyDay2(MarketCalendar):
        def is_trading_session(self, timestamp):
            return timestamp.day == 2

    out = loader.load(csv_request(), calendar=OnlyDay2())
    assert len(out) == 1 and out[0].timestamp.day == 2


# =====================================================================
# Isolation: bars feed the FROZEN Renko engine unchanged
# =====================================================================

def test_bars_feed_frozen_renko_engine():
    from backend.app.chart.renko.configuration import BrickConfiguration, BrickType, RenkoMode
    from backend.app.chart.renko.engine import TraditionalRenkoEngine
    from backend.app.chart.renko.providers import FixedBrickSizeProvider

    text = ("timestamp,open,high,low,close,volume\n"
            "2024-01-01,100,100,100,100,0\n"
            "2024-01-02,105,105,105,105,0\n"
            "2024-01-03,110,110,110,110,0\n")
    bars = MarketDataProvider().get_history(
        MarketDataRequest(symbol="AAA", source="csv", adjustment=AdjustmentPolicy.RAW,
                          extra={"text": text}))

    cfg = BrickConfiguration(brick_type=BrickType.TRADITIONAL, brick_size=1.0, mode=RenkoMode.REPLAY)
    engine = TraditionalRenkoEngine(provider=FixedBrickSizeProvider(1.0))
    engine.configure(cfg)

    async def run():
        await engine.start()
        for b in bars:
            await engine.process_market_data({
                "timestamp": b.timestamp, "open": b.open, "high": b.high,
                "low": b.low, "close": b.close, "volume": b.volume,
            })
        return len(engine.history())

    assert asyncio.run(run()) > 0
