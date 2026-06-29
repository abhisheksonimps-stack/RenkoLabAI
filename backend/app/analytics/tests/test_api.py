from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.analytics.api.routes import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_analytics_health_endpoint() -> None:
    response = _client().get("/api/v1/analytics/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "analytics"}


def test_analytics_capabilities_endpoint() -> None:
    response = _client().get("/api/v1/analytics/capabilities")
    assert response.status_code == 200
    payload = response.json()
    assert "descending" in payload["supported_ranking_directions"]
    assert "daily" in payload["supported_return_periods"]
    assert "markdown" in payload["supported_report_formats"]
