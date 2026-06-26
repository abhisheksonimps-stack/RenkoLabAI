import os
from functools import lru_cache

try:
    from pydantic_settings import BaseSettings
    from pydantic import Field
except ImportError:
    from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    app_name: str = Field(default="RenkoLabAI")
    app_env: str = Field(default="development")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    database_host: str = Field(default="postgres")
    database_port: int = Field(default=5432)
    database_name: str = Field(default="renkolab")
    database_user: str = Field(default="renko")
    database_password: str = Field(default="renko123")

    redis_host: str = Field(default="redis")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)

    jwt_secret: str = Field(default="replace-with-secure-secret")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiration_seconds: int = Field(default=3600)

    class Config:
        env_file = os.getenv("ENV_FILE", ".env")
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
