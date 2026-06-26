"""Backend application package entry points."""

from backend.app.configuration.loader import settings
from backend.app.infrastructure.di import configure_container

__all__ = ["settings", "configure_container"]
