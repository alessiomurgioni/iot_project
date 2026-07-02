from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseService(ABC):
    def __init__(self):
        self.name = self.__class__.__name__

    @abstractmethod
    def execute(self, data: Dict, **kwargs) -> Any:
        pass
