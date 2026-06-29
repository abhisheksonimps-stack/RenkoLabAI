"""OpenTelemetry instrumentation bootstrap."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TelemetryStatus:
    enabled: bool
    service_name: str
    reason: str | None = None


class OpenTelemetryBootstrap:
    """Initialize OpenTelemetry when optional instrumentation is installed."""

    def __init__(self, service_name: str) -> None:
        self._service_name = service_name
        self._status = TelemetryStatus(False, service_name, "not initialized")

    def initialize(self) -> TelemetryStatus:
        try:
            from opentelemetry import trace  # type: ignore
            from opentelemetry.sdk.resources import Resource  # type: ignore
            from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        except Exception as exc:  # pragma: no cover - optional deployment extra
            self._status = TelemetryStatus(False, self._service_name, f"OpenTelemetry unavailable: {exc}")
            return self._status
        provider = TracerProvider(resource=Resource.create({"service.name": self._service_name}))
        trace.set_tracer_provider(provider)
        self._status = TelemetryStatus(True, self._service_name, None)
        return self._status

    @property
    def status(self) -> TelemetryStatus:
        return self._status


__all__ = ["OpenTelemetryBootstrap", "TelemetryStatus"]
