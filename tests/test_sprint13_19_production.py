from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.security.credentials import BrokerCredentialManager, BrokerCredentials


def _client() -> TestClient:
    return TestClient(app)


def _token(client: TestClient) -> str:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "change-me-now"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_sprint13_14_authenticated_production_apis() -> None:
    client = _client()
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/strategies", headers=headers).status_code == 200
    assert client.get("/api/v1/runtime/status", headers=headers).status_code == 200
    assert client.get("/api/v1/orders", headers=headers).status_code == 200
    assert client.get("/api/v1/positions", headers=headers).status_code == 200
    assert client.get("/api/v1/portfolio/snapshot", headers=headers).status_code == 200
    assert client.get("/api/v1/production-analytics/snapshot", headers=headers).status_code in {200, 404}
    assert client.get("/api/v1/production/health", headers=headers).status_code == 200
    assert client.get("/api/v1/production/metrics", headers=headers).status_code == 200


def test_production_endpoints_require_authentication() -> None:
    client = _client()
    response = client.get("/api/v1/strategies")
    assert response.status_code == 401


def test_broker_credentials_are_stored_without_exposing_secret(tmp_path) -> None:
    manager = BrokerCredentialManager(file_path=tmp_path / "creds.json", environ={})
    manager.save(BrokerCredentials(exchange_id="binance", api_key="key", secret="secret", sandbox=True))
    loaded = manager.load("binance")
    assert loaded.api_key == "key"
    public = manager.list_public()[0]
    assert public == {"exchange_id": "binance", "has_api_key": True, "sandbox": True}
    assert "secret" not in public


def test_backtesting_api_runs_with_real_strategy() -> None:
    client = _client()
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "strategy_name": "ema_crossover",
        "starting_capital": 10000,
        "bricks": [
            {"close_price": 100, "direction": "up"},
            {"close_price": 101, "direction": "up"},
            {"close_price": 102, "direction": "up"},
            {"close_price": 103, "direction": "up"},
            {"close_price": 104, "direction": "up"},
        ],
    }
    response = client.post("/api/v1/backtesting/run", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    assert "metrics" in response.json()
