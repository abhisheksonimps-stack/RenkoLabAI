"""User, role, permission and password storage primitives."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Protocol

from backend.app.security.base import TradingPermission


@dataclass(frozen=True)
class User:
    """Authenticated platform user."""

    username: str
    password_hash: str
    roles: frozenset[str] = field(default_factory=lambda: frozenset({"viewer"}))
    permissions: frozenset[TradingPermission] = field(default_factory=frozenset)
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)

    def public_dict(self) -> dict[str, object]:
        return {
            "username": self.username,
            "roles": sorted(self.roles),
            "permissions": sorted(permission.value for permission in self.permissions),
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }


class UserRepository(Protocol):
    async def get(self, username: str) -> User | None:
        ...

    async def save(self, user: User) -> None:
        ...

    async def list(self) -> list[User]:
        ...


class PasswordHasher:
    """PBKDF2 password hasher using only Python standard library primitives."""

    def __init__(self, iterations: int = 260_000) -> None:
        self._iterations = int(iterations)

    def hash(self, password: str, *, salt: bytes | None = None) -> str:
        if not password:
            raise ValueError("password cannot be empty")
        salt = salt or secrets.token_bytes(32)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, self._iterations)
        return f"pbkdf2_sha256${self._iterations}${salt.hex()}${digest.hex()}"

    def verify(self, password: str, encoded: str) -> bool:
        try:
            algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            expected = self.hash(password, salt=bytes.fromhex(salt_hex))
            # Preserve iteration count in stored value.
            stored = f"{algorithm}${iterations}${salt_hex}${digest_hex}"
            if expected.split("$", 2)[0] != algorithm:
                return False
            calc_digest = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
            ).hex()
            calculated = f"{algorithm}${iterations}${salt_hex}${calc_digest}"
            return hmac.compare_digest(stored, calculated)
        except Exception:
            return False


class FileUserRepository:
    """Small durable JSON user repository for single-node deployments and tests."""

    def __init__(self, path: str | Path = "data/users.json") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def get(self, username: str) -> User | None:
        return self._read().get(username)

    async def save(self, user: User) -> None:
        users = self._read()
        users[user.username] = user
        self._write(users)

    async def list(self) -> list[User]:
        return sorted(self._read().values(), key=lambda user: user.username)

    def ensure_user(self, username: str, password: str, *, roles: Iterable[str]) -> User:
        users = self._read()
        if username in users:
            return users[username]
        hasher = PasswordHasher()
        user = User(username=username, password_hash=hasher.hash(password), roles=frozenset(roles))
        users[username] = user
        self._write(users)
        return user

    def _read(self) -> dict[str, User]:
        if not self._path.exists():
            return {}
        raw = json.loads(self._path.read_text(encoding="utf-8") or "{}")
        users: dict[str, User] = {}
        for username, payload in raw.items():
            users[username] = User(
                username=username,
                password_hash=payload["password_hash"],
                roles=frozenset(payload.get("roles", [])),
                permissions=frozenset(TradingPermission(value) for value in payload.get("permissions", [])),
                is_active=bool(payload.get("is_active", True)),
                created_at=datetime.fromisoformat(payload["created_at"]),
            )
        return users

    def _write(self, users: dict[str, User]) -> None:
        payload: dict[str, object] = {}
        for username, user in users.items():
            data = asdict(user)
            data["roles"] = sorted(user.roles)
            data["permissions"] = sorted(permission.value for permission in user.permissions)
            data["created_at"] = user.created_at.isoformat()
            payload[username] = data
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        try:
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


__all__ = ["FileUserRepository", "PasswordHasher", "User", "UserRepository"]
