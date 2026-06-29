"""Broker credential management and secrets resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class BrokerCredentials:
    exchange_id: str
    api_key: str
    secret: str
    password: str | None = None
    sandbox: bool = False

    def to_ccxt_config(self) -> dict[str, object]:
        config: dict[str, object] = {"apiKey": self.api_key, "secret": self.secret, "enableRateLimit": True}
        if self.password:
            config["password"] = self.password
        if self.sandbox:
            config["sandbox"] = True
        return config


class EnvironmentBrokerCredentialStore:
    """Resolve broker credentials from environment variables."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ or os.environ

    def load(self, exchange_id: str) -> BrokerCredentials:
        prefix = f"BROKER_{exchange_id.upper()}"
        api_key = self._environ.get(f"{prefix}_API_KEY")
        secret = self._environ.get(f"{prefix}_SECRET")
        if not api_key or not secret:
            raise RuntimeError(f"Missing broker credentials for {exchange_id}")
        return BrokerCredentials(
            exchange_id=exchange_id,
            api_key=api_key,
            secret=secret,
            password=self._environ.get(f"{prefix}_PASSWORD"),
            sandbox=self._environ.get(f"{prefix}_SANDBOX", "false").lower() == "true",
        )


__all__ = ["BrokerCredentials", "EnvironmentBrokerCredentialStore"]
