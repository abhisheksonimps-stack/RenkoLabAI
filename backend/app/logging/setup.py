"""Logging configuration."""

from __future__ import annotations

import logging
import sys

from backend.app.observability.structured_logging import JsonLogFormatter


def configure_logging(settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if getattr(settings, "app_env", "development").lower() in {"production", "prod"}:
        formatter = JsonLogFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
