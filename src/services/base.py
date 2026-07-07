from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseService(ABC):
    """Base class for all services in the pool"""

    def __init__(self):
        self.name = self.__class__.__name__

    @abstractmethod
    def execute(self, data: Dict, dr_type: str = None, attribute: str = None) -> Any:
        """Execute the service on provided data"""
        pass
