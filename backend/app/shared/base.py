class ApplicationError(Exception):
    """Base application exception."""

    pass

class NotFoundError(ApplicationError):
    """Entity not found exception."""

    pass

class ValidationError(ApplicationError):
    """Validation failure exception."""

    pass

class DependencyError(ApplicationError):
    """Dependency resolution exception."""

    pass
