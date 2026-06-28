from __future__ import annotations


class RenkoConfigurationError(ValueError):
    pass


class InvalidBrickSize(RenkoConfigurationError):
    pass


class UnsupportedRenkoMode(RenkoConfigurationError):
    pass


class ValidationFailed(Exception):
    pass


class RenkoEngineError(RuntimeError):
    pass


class SnapshotError(RenkoEngineError):
    """Base error for engine snapshot / restore problems."""


class CorruptedSnapshotError(SnapshotError):
    """Raised when a snapshot cannot be parsed or is missing required fields."""


class SnapshotVersionError(SnapshotError):
    """Raised when a snapshot's schema_version is not supported."""


class IncompatibleSnapshotError(SnapshotError):
    """Raised when a snapshot targets an engine/provider/strategy/builder that
    is not available or not compatible with the current environment."""
