"""Broker credential management and secrets resolution."""

from __future__ import annotations

import base64
import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
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

    def public_dict(self) -> dict[str, object]:
        return {"exchange_id": self.exchange_id, "has_api_key": bool(self.api_key), "sandbox": self.sandbox}


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


class FileBrokerCredentialStore:
    """Durable broker credential store for deployments without a managed secret backend.

    Values are base64 encoded and the file mode is restricted to the process user. In
    production, prefer environment variables or a managed secret store mounted into
    the process.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, credentials: BrokerCredentials) -> None:
        data = self._read()
        data[credentials.exchange_id] = {
            key: self._encode(value) if isinstance(value, str) else value for key, value in asdict(credentials).items()
        }
        self._write(data)

    def load(self, exchange_id: str) -> BrokerCredentials:
        data = self._read().get(exchange_id)
        if data is None:
            raise RuntimeError(f"Missing broker credentials for {exchange_id}")
        return BrokerCredentials(
            exchange_id=self._decode(str(data["exchange_id"])),
            api_key=self._decode(str(data["api_key"])),
            secret=self._decode(str(data["secret"])),
            password=self._decode(str(data["password"])) if data.get("password") else None,
            sandbox=bool(data.get("sandbox", False)),
        )

    def list_public(self) -> list[dict[str, object]]:
        items = []
        for key in self._read():
            try:
                credentials = self.load(key)
                items.append(credentials.public_dict())
            except RuntimeError:
                continue
        return sorted(items, key=lambda item: str(item["exchange_id"]))

    def _read(self) -> dict[str, dict[str, object]]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8") or "{}")

    def _write(self, data: dict[str, dict[str, object]]) -> None:
        self._path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        try:
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    @staticmethod
    def _encode(value: str) -> str:
        return base64.urlsafe_b64encode(value.encode()).decode()

    @staticmethod
    def _decode(value: str) -> str:
        return base64.urlsafe_b64decode(value.encode()).decode()


class BrokerCredentialManager:
    """Credential resolution facade with environment-first precedence."""

    def __init__(self, *, file_path: str | Path, environ: Mapping[str, str] | None = None) -> None:
        self._env = EnvironmentBrokerCredentialStore(environ)
        self._file = FileBrokerCredentialStore(file_path)

    def save(self, credentials: BrokerCredentials) -> None:
        self._file.save(credentials)

    def load(self, exchange_id: str) -> BrokerCredentials:
        try:
            return self._env.load(exchange_id)
        except RuntimeError:
            return self._file.load(exchange_id)

    def list_public(self) -> list[dict[str, object]]:
        return self._file.list_public()


__all__ = [
    "BrokerCredentialManager",
    "BrokerCredentials",
    "EnvironmentBrokerCredentialStore",
    "FileBrokerCredentialStore",
]
