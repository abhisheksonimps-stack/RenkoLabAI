"""FastAPI production route modules."""

from backend.app.api.routes.auth import router as auth_router
from backend.app.api.routes.backtesting import router as backtesting_router
from backend.app.api.routes.brokers import router as brokers_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.market_data import router as market_data_router
from backend.app.api.routes.orders import router as orders_router
from backend.app.api.routes.portfolio import router as portfolio_router
from backend.app.api.routes.positions import router as positions_router
from backend.app.api.routes.production_health import router as production_health_router
from backend.app.api.routes.runtime import router as runtime_router
from backend.app.api.routes.strategies import router as strategies_router
from backend.app.api.routes.analytics import router as production_analytics_router

__all__ = [
    "auth_router",
    "backtesting_router",
    "brokers_router",
    "health_router",
    "market_data_router",
    "orders_router",
    "portfolio_router",
    "positions_router",
    "production_analytics_router",
    "production_health_router",
    "runtime_router",
    "strategies_router",
]
