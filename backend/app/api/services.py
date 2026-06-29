"""Application service registry used by production FastAPI routers."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from backend.app.analytics.reporting import AnalyticsReportRenderer
from backend.app.configuration.loader import settings
from backend.app.health.production import ProductionHealthRegistry
from backend.app.metrics.production import TradingMetrics
from backend.app.security.base import KillSwitch
from backend.app.security.credentials import BrokerCredentialManager, BrokerCredentials
from backend.app.trading.broker.ccxt_adapter import CCXTAdapter
from backend.app.trading.broker.live_executor import LiveExecutor
from backend.app.trading.live_pipeline import LiveTradingPipeline
from backend.app.trading.oms.engine import OMS
from backend.app.trading.oms.positions import PositionSynchronizer
from backend.app.trading.persistence import JsonlTradingPersistence, TradingPersistencePort
from backend.app.trading.portfolio.portfolio import Portfolio
from backend.app.trading.runtime import LiveRuntimeOrchestrator
from backend.app.trading.strategy.engine import StrategyEngine
from backend.app.trading.strategy.factory import StrategyFactory


class RuntimeNotConfiguredError(RuntimeError):
    """Raised when live runtime is requested before broker setup."""


class ProductionServiceRegistry:
    """Runtime service registry preserving Sprint 12 components and exposing API state."""

    def __init__(self) -> None:
        self.strategy_factory = StrategyFactory()
        self.metrics = TradingMetrics()
        self.health = ProductionHealthRegistry()
        self.kill_switch = KillSwitch()
        self.credentials = BrokerCredentialManager(file_path=settings.broker_credentials_file)
        self.persistence: TradingPersistencePort = JsonlTradingPersistence(settings.trading_persistence_path)
        self._portfolio = Portfolio(100_000.0)
        self._position_sync: PositionSynchronizer | None = None
        self._oms: OMS | None = None
        self._pipeline: LiveTradingPipeline | None = None
        self._runtime: LiveRuntimeOrchestrator | None = None
        self._report_renderer = AnalyticsReportRenderer()
        self._register_health_checks()

    @property
    def portfolio(self) -> Portfolio:
        return self._portfolio

    @property
    def oms(self) -> OMS | None:
        return self._oms

    @property
    def runtime(self) -> LiveRuntimeOrchestrator | None:
        return self._runtime

    @property
    def pipeline(self) -> LiveTradingPipeline | None:
        return self._pipeline

    def configure_live_runtime(
        self,
        *,
        exchange_id: str,
        strategy_name: str,
        strategy_parameters: dict[str, Any] | None = None,
        starting_capital: float | None = None,
    ) -> dict[str, object]:
        """Create a live runtime from existing Sprint 12 components and a real broker adapter."""
        if starting_capital is not None:
            self._portfolio = Portfolio(float(starting_capital))
        credentials = self.credentials.load(exchange_id)
        broker = CCXTAdapter(credentials.exchange_id, credentials.to_ccxt_config())
        executor = LiveExecutor(broker)
        self._position_sync = PositionSynchronizer(broker)
        self._oms = OMS(executor, broker=broker, position_synchronizer=self._position_sync)
        strategy = self.strategy_factory.create(strategy_name, **(strategy_parameters or {}))
        strategy_engine = StrategyEngine(strategy)
        self._pipeline = LiveTradingPipeline(
            strategy_engine=strategy_engine,
            oms=self._oms,
            portfolio=self._portfolio,
            persistence=self.persistence,
            metrics_collector=self.metrics,
        )
        from backend.app.marketdata.streaming.manager import StreamingManager

        streaming_manager = StreamingManager()
        self._runtime = LiveRuntimeOrchestrator(streaming_manager=streaming_manager, live_pipeline=self._pipeline, oms=self._oms)
        return {"configured": True, "exchange_id": exchange_id, "strategy": strategy_name}

    def require_oms(self) -> OMS:
        if self._oms is None:
            raise RuntimeNotConfiguredError("Live OMS is not configured. Configure broker and runtime first.")
        return self._oms

    def require_runtime(self) -> LiveRuntimeOrchestrator:
        if self._runtime is None:
            raise RuntimeNotConfiguredError("Live runtime is not configured. Configure broker and runtime first.")
        return self._runtime

    async def runtime_status(self) -> dict[str, object]:
        if self._runtime is None:
            return {"configured": False, "running": False, "reason": "runtime not configured"}
        health = await self._runtime.health()
        return asdict(health)

    async def health_summary(self) -> dict[str, object]:
        return await self.health.summary()

    def portfolio_snapshot(self, mark_price: float | None = None) -> dict[str, object]:
        price = mark_price or (self._portfolio.equity_curve[-1].equity if self._portfolio.equity_curve else self._portfolio.cash)
        if mark_price is None and self._portfolio.position.is_open:
            price = self._portfolio.position.average_entry_price
        return {
            "starting_capital": self._portfolio.starting_capital,
            "cash": self._portfolio.cash,
            "reserved": self._portfolio.reserved,
            "available_capital": self._portfolio.available_capital,
            "buying_power": self._portfolio.buying_power,
            "equity": self._portfolio.equity(float(price)),
            "open_position": self._portfolio.position.is_open,
            "position_quantity": self._portfolio.position.quantity,
            "trade_count": len(self._portfolio.trades),
            "order_count": len(self._portfolio.orders),
            "equity_points": len(self._portfolio.equity_curve),
        }

    def _register_health_checks(self) -> None:
        async def database() -> dict[str, object]:
            return {"status": "ok", "configured": True, "host": settings.database_host, "database": settings.database_name}

        async def redis() -> dict[str, object]:
            from backend.app.infrastructure.redis_client import RedisClient

            client = RedisClient(settings)
            await client.connect()
            result = await client.health()
            await client.close()
            return result

        async def runtime() -> dict[str, object]:
            return await self.runtime_status()

        async def portfolio() -> dict[str, object]:
            return {"status": "ok", **self.portfolio_snapshot()}

        async def analytics() -> dict[str, object]:
            return {"status": "ok", "renderer": self._report_renderer.__class__.__name__}

        async def reporting() -> dict[str, object]:
            return {"status": "ok", "formats": ["json", "markdown", "csv"]}

        self.health.register("database", database)
        self.health.register("redis", redis)
        self.health.register("runtime", runtime)
        self.health.register("portfolio", portfolio)
        self.health.register("analytics", analytics)
        self.health.register("reporting", reporting)


production_services = ProductionServiceRegistry()


__all__ = ["ProductionServiceRegistry", "RuntimeNotConfiguredError", "production_services"]
