"""Prometheus-backed live trading metrics."""

from __future__ import annotations

from dataclasses import dataclass

try:
    from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest
except ImportError:  # pragma: no cover
    Counter = Gauge = Histogram = CollectorRegistry = generate_latest = None  # type: ignore[assignment]


@dataclass(frozen=True)
class MetricsSnapshot:
    ticks_processed: int
    orders_submitted: int
    orders_rejected: int
    fills_processed: int
    active_positions: int
    portfolio_equity: float


class TradingMetrics:
    """Metrics collector for strategy, order, broker and portfolio runtime state."""

    def __init__(self, registry=None) -> None:
        self._registry = registry or (CollectorRegistry() if CollectorRegistry is not None else None)
        self._fallback = MetricsSnapshot(0, 0, 0, 0, 0, 0.0)
        if Counter is None:
            self._ticks = self._orders = self._rejections = self._fills = None
            self._latency = self._queue = self._positions = self._equity = None
            return
        self._ticks = Counter("renkolab_ticks_processed_total", "Total processed ticks", registry=self._registry)
        self._orders = Counter("renkolab_orders_submitted_total", "Total submitted orders", registry=self._registry)
        self._rejections = Counter("renkolab_orders_rejected_total", "Total rejected orders", registry=self._registry)
        self._fills = Counter("renkolab_fills_processed_total", "Total processed fills", registry=self._registry)
        self._latency = Histogram("renkolab_order_execution_latency_seconds", "Order execution latency", registry=self._registry)
        self._queue = Gauge("renkolab_event_queue_size", "Event queue depth", registry=self._registry)
        self._positions = Gauge("renkolab_active_positions", "Active positions", registry=self._registry)
        self._equity = Gauge("renkolab_portfolio_equity", "Portfolio equity", registry=self._registry)

    def record_tick(self) -> None:
        if self._ticks is not None:
            self._ticks.inc()
        self._fallback = MetricsSnapshot(
            self._fallback.ticks_processed + 1,
            self._fallback.orders_submitted,
            self._fallback.orders_rejected,
            self._fallback.fills_processed,
            self._fallback.active_positions,
            self._fallback.portfolio_equity,
        )

    def record_order_submitted(self) -> None:
        if self._orders is not None:
            self._orders.inc()
        self._fallback = MetricsSnapshot(
            self._fallback.ticks_processed,
            self._fallback.orders_submitted + 1,
            self._fallback.orders_rejected,
            self._fallback.fills_processed,
            self._fallback.active_positions,
            self._fallback.portfolio_equity,
        )

    def record_order_rejected(self) -> None:
        if self._rejections is not None:
            self._rejections.inc()
        self._fallback = MetricsSnapshot(
            self._fallback.ticks_processed,
            self._fallback.orders_submitted,
            self._fallback.orders_rejected + 1,
            self._fallback.fills_processed,
            self._fallback.active_positions,
            self._fallback.portfolio_equity,
        )

    def record_fill(self) -> None:
        if self._fills is not None:
            self._fills.inc()
        self._fallback = MetricsSnapshot(
            self._fallback.ticks_processed,
            self._fallback.orders_submitted,
            self._fallback.orders_rejected,
            self._fallback.fills_processed + 1,
            self._fallback.active_positions,
            self._fallback.portfolio_equity,
        )

    def observe_execution_latency(self, seconds: float) -> None:
        if self._latency is not None:
            self._latency.observe(max(0.0, seconds))

    def set_queue_size(self, size: int) -> None:
        if self._queue is not None:
            self._queue.set(max(0, size))

    def set_portfolio(self, *, active_positions: int, equity: float) -> None:
        if self._positions is not None:
            self._positions.set(max(0, active_positions))
        if self._equity is not None:
            self._equity.set(equity)
        self._fallback = MetricsSnapshot(
            self._fallback.ticks_processed,
            self._fallback.orders_submitted,
            self._fallback.orders_rejected,
            self._fallback.fills_processed,
            max(0, active_positions),
            equity,
        )

    def snapshot(self) -> MetricsSnapshot:
        return self._fallback

    def prometheus(self) -> bytes:
        if generate_latest is None or self._registry is None:
            return b""
        return generate_latest(self._registry)


__all__ = ["MetricsSnapshot", "TradingMetrics"]
