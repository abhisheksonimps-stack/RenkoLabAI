"""JWT token service."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable

try:
    import jwt
except ImportError:  # pragma: no cover
    jwt = None  # type: ignore[assignment]

from backend.app.configuration.loader import settings


class JwtService:
    """Create and validate signed JWT tokens."""

    def create_token(
        self,
        subject: str,
        *,
        token_type: str = "access",
        roles: Iterable[str] = (),
        permissions: Iterable[str] = (),
        expires_seconds: int | None = None,
    ) -> str:
        expiration = datetime.now(timezone.utc) + timedelta(seconds=expires_seconds or settings.jwt_expiration_seconds)
        payload = {
            "sub": subject,
            "typ": token_type,
            "roles": list(roles),
            "permissions": list(permissions),
            "exp": expiration,
            "iat": datetime.now(timezone.utc),
            "jti": secrets.token_urlsafe(24),
            "iss": settings.app_name,
        }
        if jwt is not None:
            return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        return self._encode_fallback(payload)

    def decode_token(self, token: str) -> dict:
        if jwt is not None:
            return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], issuer=settings.app_name)
        return self._decode_fallback(token)

    def _encode_fallback(self, payload: dict) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        safe_payload = dict(payload)
        for key in ("exp", "iat"):
            if isinstance(safe_payload.get(key), datetime):
                safe_payload[key] = int(safe_payload[key].timestamp())
        signing_input = b".".join([self._b64(header), self._b64(safe_payload)])
        signature = hmac.new(settings.jwt_secret.encode(), signing_input, hashlib.sha256).digest()
        return b".".join([signing_input, base64.urlsafe_b64encode(signature).rstrip(b"=")]).decode()

    def _decode_fallback(self, token: str) -> dict:
        try:
            header_b64, payload_b64, sig_b64 = token.split(".")
            signing_input = f"{header_b64}.{payload_b64}".encode()
            expected = base64.urlsafe_b64encode(
                hmac.new(settings.jwt_secret.encode(), signing_input, hashlib.sha256).digest()
            ).rstrip(b"=").decode()
            if not hmac.compare_digest(expected, sig_b64):
                raise ValueError("invalid token signature")
            payload = json.loads(self._b64decode(payload_b64))
            if payload.get("iss") != settings.app_name:
                raise ValueError("invalid token issuer")
            if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
                raise ValueError("token expired")
            return payload
        except Exception as exc:
            raise ValueError("invalid token") from exc

    @staticmethod
    def _b64(payload: dict) -> bytes:
        return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)
