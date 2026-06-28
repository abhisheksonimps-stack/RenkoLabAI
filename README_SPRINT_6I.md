# Sprint 6I — Hybrid Renko (Builder)

Hybrid Renko is a new BrickBuilder that plugs into the Sprint 6F builder
abstraction. NO engine changes. Traditional builder untouched. Same package
convention as the rest of the codebase (backend.app.chart.renko.*).

## New
* HybridBrickBuilder (in backend/app/chart/renko/builder.py) — composes the
  Traditional builder for geometry (no duplicated logic), tags bricks with a
  hybrid marker + monotonic sequence, and carries state that snapshots/restores
  via Sprint 6G (export_state / import_state).
* tests/test_hybrid_builder.py

## Modified (complete files, drop in at shown paths)
* backend/app/chart/renko/builder.py        — HybridBrickBuilder + register "hybrid"
* backend/app/chart/renko/configuration.py  — `builder_type` field + resolved_builder() precedence
* backend/app/chart/renko/validator.py      — validates the configured builder exists
* backend/app/chart/renko/__init__.py       — exports HybridBrickBuilder
* backend/app/chart/renko/performance.py    — hybrid_engine() for benchmark compatibility
* backend/app/infrastructure/di.py          — wires builder_registry into the validator
* tests/test_brick_builder_abstraction.py   — 2 registry-enumeration assertions now
                                              include "hybrid" (intent preserved)
* conftest.py                               — repo root on sys.path (no PYTHONPATH needed)

## Selection
    BrickConfiguration(..., builder_type="hybrid")   # or builder="hybrid", or metadata["builder_type"]
Traditional remains the default. Factory resolves builders dynamically via the
registry (no if/else chains). Plugins register more builders via
`register_brick_builders` (unchanged mechanism).

## Run (no PYTHONPATH needed)
    pytest -q                                          # 232 passing
    python -m backend.app.chart.renko.benchmark_runner --full

## Not included (unchanged): engine.py, models.py, snapshot.py, factory.py,
## plugin.py, manager.py, strategies.py, providers.py.
## configuration.py is included because builder_type was added; if your config is
## a Pydantic model, add one optional field `builder_type: str | None = None` and
## the resolved_builder() precedence shown here.
