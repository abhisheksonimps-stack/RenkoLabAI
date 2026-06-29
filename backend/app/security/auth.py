"""Authentication application service."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backend.app.configuration.loader import settings
from backend.app.security.base import Principal, TradingPermission
from backend.app.security.jwt import JwtService
from backend.app.security.users import FileUserRepository, PasswordHasher, User, UserRepository


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRevocationStore:
    """Durable revoked token id store."""

    def __init__(self, path: str | Path = "data/revoked_tokens.json") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def revoke(self, token_id: str) -> None:
        ids = self._read()
        ids.add(token_id)
        self._write(ids)

    async def is_revoked(self, token_id: str | None) -> bool:
        return bool(token_id and token_id in self._read())

    def _read(self) -> set[str]:
        if not self._path.exists():
            return set()
        return set(json.loads(self._path.read_text(encoding="utf-8") or "[]"))

    def _write(self, values: set[str]) -> None:
        self._path.write_text(json.dumps(sorted(values), indent=2), encoding="utf-8")
        try:
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


class AuthenticationService:
    """Authenticate users and mint/validate JWT tokens."""

    def __init__(
        self,
        *,
        users: UserRepository | None = None,
        hasher: PasswordHasher | None = None,
        jwt_service: JwtService | None = None,
        revoked_tokens: TokenRevocationStore | None = None,
    ) -> None:
        self._users = users or FileUserRepository()
        self._hasher = hasher or PasswordHasher()
        self._jwt = jwt_service or JwtService()
        self._revoked = revoked_tokens or TokenRevocationStore()

    async def login(self, username: str, password: str) -> TokenPair:
        user = await self._users.get(username)
        if user is None or not user.is_active or not self._hasher.verify(password, user.password_hash):
            raise PermissionError("Invalid username or password")
        return self._tokens_for_user(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        payload = self._jwt.decode_token(refresh_token)
        if payload.get("typ") != "refresh":
            raise PermissionError("Invalid refresh token")
        if await self._revoked.is_revoked(payload.get("jti")):
            raise PermissionError("Refresh token has been revoked")
        user = await self._users.get(str(payload.get("sub", "")))
        if user is None or not user.is_active:
            raise PermissionError("User is not active")
        return self._tokens_for_user(user)

    async def logout(self, token: str) -> None:
        payload = self._jwt.decode_token(token)
        await self._revoked.revoke(str(payload.get("jti", "")))

    async def principal_from_token(self, token: str) -> Principal:
        payload = self._jwt.decode_token(token)
        if payload.get("typ") != "access":
            raise PermissionError("Access token required")
        if await self._revoked.is_revoked(payload.get("jti")):
            raise PermissionError("Token has been revoked")
        permissions = frozenset(TradingPermission(value) for value in payload.get("permissions", []))
        return Principal(subject=str(payload["sub"]), roles=frozenset(payload.get("roles", [])), permissions=permissions)

    def _tokens_for_user(self, user: User) -> TokenPair:
        roles = tuple(sorted(user.roles))
        permissions = tuple(sorted(permission.value for permission in user.permissions))
        access = self._jwt.create_token(
            user.username,
            token_type="access",
            roles=roles,
            permissions=permissions,
            expires_seconds=settings.jwt_expiration_seconds,
        )
        refresh = self._jwt.create_token(
            user.username,
            token_type="refresh",
            roles=roles,
            permissions=permissions,
            expires_seconds=max(settings.jwt_expiration_seconds * 24, 86_400),
        )
        return TokenPair(access_token=access, refresh_token=refresh)


_user_repository = FileUserRepository()
_user_repository.ensure_user(
    settings.admin_username,
    settings.admin_password,
    roles=("admin",),
)
authentication_service = AuthenticationService(users=_user_repository)


__all__ = ["AuthenticationService", "TokenPair", "TokenRevocationStore", "authentication_service"]
