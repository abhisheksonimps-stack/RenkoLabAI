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
