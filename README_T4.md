# Trading System T4 — Universal Market Data Framework (new package)

Self-contained backend/app/marketdata/. Depends on NOTHING in chart/renko/ or
trading/ and modifies NOTHING there. Emits normalized OHLCV MarketBars (not
bricks); bars->bricks stays in the frozen Renko engine via glue.

## New files (backend/app/marketdata/)
models.py    # MarketBar (UTC, OHLC-validated), AssetClass{EQUITY,COMMODITY,CRYPTO,FOREX},
             #   AdjustmentPolicy{RAW,ADJUSTED}, MarketDataRequest, to_utc(),
             #   MarketCalendar ABC (reserved extension point — no session assumptions)
errors.py    # MarketDataError + AdapterNotFound/SymbolNotFound/DataUnavailable/
             #   RateLimited/MalformedData/NotSupported
adapters/base.py   # MarketDataAdapter ABC (fetch; stream->NotSupported; supports);
                   #   apply_adjustment(policy/asset_class) + normalize_bars(dedup+sort)
adapters/csv.py    # CsvAdapter (configurable column_map/datetime_format/delimiter;
                   #   text or path; honors AdjustmentPolicy via adj_close)
adapters/yahoo.py  # YahooAdapter (injected client; honors AdjustmentPolicy;
                   #   translates errors to typed errors; stream future-ready)
registry.py  # AdapterRegistry + default_registry() (csv, yahoo)
provider.py  # MarketDataProvider (routes by request.source; normalize; typed errors)
cache.py     # MarketDataCache (in-memory, request-keyed; returns copies)
loader.py    # HistoricalLoader (cache check -> provider -> cache set;
             #   optional MarketCalendar hook, applied ONLY when a calendar is supplied)
tests/test_marketdata.py
conftest.py

## Refinements applied
1. AdjustmentPolicy (RAW | ADJUSTED) on MarketDataRequest; adapters scale OHLC by
   adj_close/close only for ADJUSTED + EQUITY (raw otherwise) — not metadata-only.
2. MarketCalendar ABC reserved as an extension point; no concrete impl, no
   hardcoded trading-session assumptions. The loader filters by session ONLY if a
   calendar is explicitly provided (default None = no filtering).

## Run
    pytest -q tests/test_marketdata.py
    # add --cov=backend/app/marketdata --cov-report=term  (100%)
