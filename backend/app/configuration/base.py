try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings


class BaseConfiguration(BaseSettings):
    """Shared base configuration model."""

    class Config:
        env_prefix = ""
        case_sensitive = False
