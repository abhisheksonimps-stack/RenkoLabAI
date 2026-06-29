from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.analytics.api.routes import router as analytics_router
from backend.app.api.routes import (
    auth_router,
    backtesting_router,
    brokers_router,
    health_router,
    market_data_router,
    orders_router,
    portfolio_router,
    positions_router,
    production_analytics_router,
    production_health_router,
    runtime_router,
    strategies_router,
)
from backend.app.configuration.loader import settings
from backend.app.infrastructure.di import configure_container
from backend.app.logging.setup import configure_logging
from backend.app.observability.telemetry import OpenTelemetryBootstrap

configure_logging(settings)
telemetry = OpenTelemetryBootstrap(settings.otel_service_name)
telemetry.initialize()
container = configure_container()

app = FastAPI(title=settings.app_name, version="0.1.0")
app.container = container

origins = [origin.strip() for origin in settings.allowed_cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public compatibility endpoints.
app.include_router(health_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")

# Production Sprint 13-19 endpoints.
for router in (
    auth_router,
    strategies_router,
    backtesting_router,
    runtime_router,
    orders_router,
    positions_router,
    portfolio_router,
    production_analytics_router,
    market_data_router,
    production_health_router,
    brokers_router,
):
    app.include_router(router, prefix="/api/v1")


@app.on_event("startup")
async def on_startup() -> None:
    await container.init_resources()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await container.shutdown_resources()
