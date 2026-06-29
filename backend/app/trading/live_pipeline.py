"""Runtime integration pipeline for live trading."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterable, Optional

from backend.app.analytics.domain.entities import AnalyticsReport
from backend.app.analytics.domain.services import AnalyticsReportService
from backend.app.analytics.portfolio import PortfolioAnalyticsCalculator
from backend.app.analytics.reporting import AnalyticsReportRenderer
from backend.app.events.base import BaseEvent
from backend.app.marketdata.streaming.events import TickEvent
from backend.app.marketdata.streaming.interfaces import MarketDataSubscriber
from backend.app.metrics.production import TradingMetrics
from backend.app.marketdata.streaming.tick_processor import TickProcessor, TickProcessingResult
from backend.app.trading.backtesting.metrics import PerformanceMetrics, compute_metrics
from backend.app.trading.execution.order import Order
from backend.app.trading.execution.position import Trade
from backend.app.trading.oms.engine import OMS
from backend.app.trading.persistence import NullTradingPersistence, TradingPersistencePort
from backend.app.trading.portfolio.live_snapshot import LivePortfolioSnapshot
from backend.app.trading.portfolio.portfolio import Portfolio
from backend.app.trading.portfolio.synchronizer import PortfolioSynchronizer
from backend.app.trading.strategy.engine import StrategyEngine
from backend.app.trading.strategy.interfaces import StrategyContext


@dataclass(frozen=True)
class LivePipelineReport:
    report: AnalyticsReport
    json: str
    markdown: str
    csv: str


@dataclass(frozen=True)
class LivePipelineResult:
    event: TickEvent
    tick_result: TickProcessingResult
    order: Optional[Order]
    trade: Optional[Trade]
    portfolio_snapshot: LivePortfolioSnapshot
    metrics: PerformanceMetrics
    report: LivePipelineReport


class LiveTradingPipeline(MarketDataSubscriber):
    """Connect streaming ticks to strategy, OMS, portfolio, analytics and reporting."""

    def __init__(
        self,
        *,
        strategy_engine: StrategyEngine,
        oms: OMS,
        portfolio: Portfolio,
        portfolio_id: str = "live_portfolio",
        currency: str = "USD",
        analytics_calculator: Optional[PortfolioAnalyticsCalculator] = None,
        report_renderer: Optional[AnalyticsReportRenderer] = None,
        report_service: Optional[AnalyticsReportService] = None,
        persistence: Optional[TradingPersistencePort] = None,
        metrics_collector: Optional[TradingMetrics] = None,
    ) -> None:
        self._strategy_engine = strategy_engine
        self._tick_processor = TickProcessor(strategy_engine)
        self._oms = oms
        self._portfolio_sync = PortfolioSynchronizer(portfolio, portfolio_id=portfolio_id)
        self._portfolio = portfolio
        self._portfolio_id = portfolio_id
        self._currency = currency
        self._analytics_calculator = analytics_calculator or PortfolioAnalyticsCalculator()
        self._report_renderer = report_renderer or AnalyticsReportRenderer()
        self._report_service = report_service or AnalyticsReportService()
        self._persistence = persistence or NullTradingPersistence()
        self._metrics_collector = metrics_collector or TradingMetrics()
        self._bar_index = 0
        self._last_result: LivePipelineResult | None = None

    @property
    def last_result(self) -> LivePipelineResult | None:
        return self._last_result

    @property
    def processed_ticks(self) -> int:
        return self._bar_index

    @property
    def portfolio_synchronizer(self) -> PortfolioSynchronizer:
        return self._portfolio_sync

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, TickEvent):
            await self.handle_tick(event)

    async def consume(self, events: AsyncIterable[BaseEvent]) -> None:
        async for event in events:
            await self.on_event(event)

    async def handle_tick(self, event: TickEvent) -> LivePipelineResult:
        price = float(event.price)
        timestamp = event.occurred_at
        self._metrics_collector.record_tick()
        self._update_position_marks(event.symbol, price)
        self._portfolio.mark(timestamp, price)

        context = self._context_from_tick(event)
        tick_result = self._tick_processor.process(event, context)
        order: Order | None = None
        trade: Trade | None = None

        if tick_result.actionable:
            order = await self._oms.process_signal(tick_result.strategy_result.signal, tick_result.strategy_result.context or context, price)
            if order is not None:
                if order.status.value == "rejected":
                    self._metrics_collector.record_order_rejected()
                else:
                    self._metrics_collector.record_order_submitted()
                await self._persistence.save_order(order)
                if order.fill is not None:
                    self._metrics_collector.record_fill()
                    await self._persistence.save_fill(order)
                for decision in self._oms.risk_decisions:
                    if decision.order_id == order.order_id:
                        await self._persistence.save_risk_decision(decision)
                sync_result = self._portfolio_sync.apply_order(
                    order,
                    bar_index=self._bar_index,
                    mark_price=price,
                    timestamp=timestamp,
                )
                trade = sync_result.trade
                if sync_result.applied and order.fill is not None:
                    self._strategy_engine.on_order_fill(order.fill, self._context_from_tick(event))
                    if trade is not None:
                        self._strategy_engine.on_position_close(trade, self._context_from_tick(event))

        snapshot = self._portfolio_sync.snapshot(mark_price=price, timestamp=timestamp)
        self._metrics_collector.set_portfolio(active_positions=1 if snapshot.position_quantity > 0 else 0, equity=snapshot.equity)
        await self._persistence.save_portfolio_snapshot(snapshot)
        metrics = self._metrics()
        report = self._build_report(metrics)
        await self._persistence.save_analytics_snapshot({"portfolio_id": self._portfolio_id, "report": report.json})
        await self._persist_broker_sync_state()
        result = LivePipelineResult(
            event=event,
            tick_result=tick_result,
            order=order,
            trade=trade,
            portfolio_snapshot=snapshot,
            metrics=metrics,
            report=report,
        )
        self._last_result = result
        self._bar_index += 1
        return result

    def _context_from_tick(self, event: TickEvent) -> StrategyContext:
        price = float(event.price)
        position_quantity = self._portfolio.position.quantity if self._portfolio.position.is_open else 0.0
        synchronizer = self._oms.position_synchronizer
        if synchronizer is not None:
            broker_position = synchronizer.get_position(event.symbol)
            if broker_position is not None:
                position_quantity = broker_position.quantity
        return TickProcessor.context_from_tick(
            event,
            cash=self._portfolio.cash,
            equity=self._portfolio.equity(price),
            position_quantity=position_quantity,
            open_positions=1 if position_quantity > 0 else 0,
        )

    def _update_position_marks(self, symbol: str, price: float) -> None:
        synchronizer = self._oms.position_synchronizer
        if synchronizer is not None:
            synchronizer.update_price(symbol, price)

    def _metrics(self) -> PerformanceMetrics:
        return compute_metrics(
            self._portfolio.equity_curve,
            self._portfolio.trades,
            self._portfolio.starting_capital,
            total_brokerage=self._portfolio.total_brokerage,
            total_slippage=self._portfolio.total_slippage,
        )

    def _build_report(self, metrics: PerformanceMetrics) -> LivePipelineReport:
        portfolio_analytics = self._analytics_calculator.calculate(
            portfolio_id=self._portfolio_id,
            portfolio=self._portfolio,
            metrics=metrics,
            currency=self._currency,
        )
        report = self._report_service.create_report(
            title=f"Live Trading Report - {self._portfolio_id}",
            portfolio_analytics=(portfolio_analytics,),
        )
        return LivePipelineReport(
            report=report,
            json=self._report_renderer.to_json(report),
            markdown=self._report_renderer.to_markdown(report),
            csv=self._report_renderer.to_csv(report),
        )

    async def _persist_broker_sync_state(self) -> None:
        order_sync = self._oms.order_synchronizer
        if order_sync is None:
            return
        decisions = [decision.__dict__ for decision in order_sync.decisions]
        await self._persistence.save_broker_sync_state({"decisions": decisions})


__all__ = ["LivePipelineReport", "LivePipelineResult", "LiveTradingPipeline"]
