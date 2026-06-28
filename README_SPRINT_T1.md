# Sprint T1 — Strategy Engine (new backend/app/trading/ package)

Built ON TOP OF the frozen Renko engine. NOTHING under backend/app/chart/renko/
is modified. The strategy consumes COMPLETED Renko bricks only.

## New files
backend/app/trading/__init__.py
backend/app/trading/signals/__init__.py
backend/app/trading/signals/models.py          # SignalType {BUY,SELL,EXIT,HOLD} + Signal
backend/app/trading/indicators/__init__.py
backend/app/trading/indicators/ema.py          # EMA (SMA-seeded, alpha=2/(n+1))
backend/app/trading/indicators/sma.py          # SMA (O(1) rolling)
backend/app/trading/strategy/__init__.py
backend/app/trading/strategy/interfaces.py     # Strategy: initialize/on_brick/generate_signal/reset
backend/app/trading/strategy/ema_crossover.py  # the first strategy (exact spec)
backend/app/trading/strategy/engine.py         # StrategyEngine (feeds bricks -> signals)
backend/app/trading/strategy/registry.py       # StrategyRegistry + default_strategy_registry()
backend/app/trading/strategy/factory.py        # StrategyFactory (registry-driven; no if/else)
tests/test_trading_strategy.py                 # 34 tests, 100% coverage of backend/app/trading
conftest.py                                    # repo root on sys.path (no PYTHONPATH needed)

## Strategy (exactly as specified)
BUY  : completed brick closes above the 10 EMA (entered from flat)
SELL : completed brick closes below the 10 EMA (entered from flat)
EXIT : opposite-direction brick while a position is held (long->flat / short->flat)
HOLD : otherwise (same direction while held, or EMA not yet ready)
Signals are computed at brick close from completed bricks + prior state only
(no repaint). No optimization, AI, filters, or improvements.

## Run
    pytest -q tests/test_trading_strategy.py
    pytest -q tests/test_trading_strategy.py --cov=backend/app/trading --cov-report=term
