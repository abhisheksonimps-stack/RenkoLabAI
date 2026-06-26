from abc import ABC, abstractmethod

class BaseService(ABC):
    """Base application service."""

    @abstractmethod
    async def execute(self, *args, **kwargs):
        raise NotImplementedError
