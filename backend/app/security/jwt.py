from datetime import datetime, timedelta
import jwt
from backend.app.configuration.loader import settings


class JwtService:
    def create_token(self, subject: str) -> str:
        expiration = datetime.utcnow() + timedelta(seconds=settings.jwt_expiration_seconds)
        payload = {
            "sub": subject,
            "exp": expiration,
            "iss": settings.app_name,
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    def decode_token(self, token: str) -> dict:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
