from fastapi import FastAPI
from backend.app.api.routes.health import router as health_router
from backend.app.analytics.api.routes import router as analytics_router
from backend.app.configuration.loader import settings
from backend.app.logging.setup import configure_logging
from backend.app.infrastructure.di import configure_container

configure_logging(settings)
container = configure_container()

app = FastAPI(title=settings.app_name, version="0.1.0")
app.container = container

app.include_router(health_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")

@app.on_event("startup")
async def on_startup() -> None:
    await container.init_resources()

@app.on_event("shutdown")
async def on_shutdown() -> None:
    await container.shutdown_resources()
