# Milestone 1 — Paper Trading Framework

A simulated execution venue for RenkoLabAI. It runs strategies against live or
replayed market data with realistic fills, costs, latency and a full order
lifecycle — **without modifying or duplicating any existing component**. Every
piece is composed from the platform's existing primitives.

## Design principle: extend, never duplicate

| Existing component | How the paper layer reuses it |
| --- | --- |
| `Executor` (ABC) | `PaperExecutor` *implements* it (`execute(order, reference_price, timestamp) -> Order`) and is a drop-in peer of `SimulatedExecutor`. |
| `Order` / `Fill` | Used unchanged as the single record of identity, status and fill. Order-type/limit/stop metadata lives on a sidecar `OrderTicket`, so `Order` stays venue-agnostic. |
| `Position` / `Trade` / `Portfolio` | Fills are synced via `Portfolio.apply_order` / `reserve` / `release` / `mark`, exactly as `BacktestEngine` does. |
| `SlippageModel` / `BrokerageModel` | Reused directly. **Brokerage *is* the commission model** — no duplicate was created. |
| `EventBus` / `BaseEvent` | Order-lifecycle events are published on the shared bus. |
| Replay engine (`TickReplayed` / `CandleReplayed`) | `ReplayMarketFeed` subscribes to these bus events; the replay engine is untouched. |

## Components (`backend/app/trading/paper/`)

- **`enums.py`** — `OrderType` (MARKET / LIMIT / STOP), `TimeInForce` (GTC / IOC).
- **`quote.py`** — `MarketQuote`, the normalized executable price built from a `Tick` or `Candle`.
- **`ticket.py`** — `OrderTicket`, the sidecar pairing an `Order` with its trigger metadata.
- **`latency.py`** — `LatencyModel` family (`ZeroLatency`, `FixedLatency`, `RandomLatency`).
- **`executor.py`** — `PaperExecutor`: slippage + commission + latency on top of the `Executor` contract.
- **`pending.py`** — `PendingOrderManager`: the resting limit/stop book and trigger rules.
- **`simulator.py`** — `ExchangeSimulator`: the deterministic, synchronous matching core; syncs the portfolio.
- **`events.py`** — `OrderAccepted` / `OrderTriggered` / `OrderFilled` / `OrderRejected` / `OrderCancelled`.
- **`session.py`** — `PaperTradingSession` (async EventBus facade) and `PaperSessionManager` (multi-session registry).
- **`replay_feed.py`** — `ReplayMarketFeed`: drives a session from replayed bus events.

## Order lifecycle

```
submit ──► OrderAccepted ──► (resting on book for LIMIT/STOP)
                                   │
        market data update         ▼
        ──────────────────► OrderTriggered ──► PaperExecutor.execute
                                                     │
                                                     ▼
                                   Portfolio.apply_order ──► OrderFilled
                                                          └► OrderRejected (e.g. no cash)
        cancel() ────────────────────────────────────────► OrderCancelled
```

- **Market** orders fill on the next market update at its price.
- **Limit** orders rest until `low <= limit` (buy) / `high >= limit` (sell); fill reference = limit price.
- **Stop** orders rest until `high >= stop` (buy) / `low <= stop` (sell); fill reference = stop level (becomes marketable).
- The executor's slippage model is applied uniformly to the reference. Use `ZeroSlippage` if you want limit orders to fill exactly at their limit.
- `TimeInForce.IOC` orders that do not trigger on the next update are cancelled.

## Usage

```python
from backend.app.events.bus import EventBus
from backend.app.trading.portfolio.portfolio import Portfolio
from backend.app.trading.costs.slippage import PercentageSlippage
from backend.app.trading.costs.brokerage import PercentageBrokerage
from backend.app.trading.execution.order import OrderSide
from backend.app.trading.paper import (
    PaperExecutor, PaperTradingSession, FixedLatency, MarketQuote,
)

bus = EventBus()
executor = PaperExecutor(
    slippage=PercentageSlippage(0.0005),     # 5 bps
    brokerage=PercentageBrokerage(0.001),    # 10 bps commission
    latency=FixedLatency(milliseconds=50),
)
session = PaperTradingSession("AAPL", Portfolio(100_000), bus, executor=executor)
session.start()

await session.submit_limit(OrderSide.BUY, quantity=10, limit_price=95.0)
await session.feed_quote(MarketQuote("AAPL", ts, price=94.0, high=96.0, low=93.5))
# -> OrderTriggered + OrderFilled published on `bus`; portfolio updated.
```

### Replay integration

```python
from backend.app.trading.paper import ReplayMarketFeed

feed = ReplayMarketFeed(session, bus)
feed.attach()   # forwards the replay engine's TickReplayed / CandleReplayed to the session
```

## Running the tests

```bash
# the paper-trading suite
pytest tests/test_paper_latency.py tests/test_paper_executor.py \
       tests/test_paper_pending.py tests/test_paper_simulator.py \
       tests/test_paper_session.py -q

# the whole repository (existing + new)
pytest -q
```

All existing tests continue to pass; the framework adds 32 unit tests across the
executor, latency models, trigger rules, the matching core (incl. portfolio
sync, cancellation and IOC), and the async session + replay integration.
