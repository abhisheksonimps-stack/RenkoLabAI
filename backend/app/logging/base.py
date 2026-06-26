from abc import ABC, abstractmethod

class BaseLoggingConfigurator(ABC):
    """Base logging configurator."""

    @abstractmethod
    def configure(self) -> None:
        raise NotImplementedError
