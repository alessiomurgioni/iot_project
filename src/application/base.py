from abc import ABC, abstractmethod
from typing import Dict


class BaseApplication(ABC):
    """Base class for all applications"""

    def __init__(self):
        self.name = self.__class__.__name__

    @abstractmethod
    def process_data(self, data: Dict) -> Dict:
        """Process input data and return results"""
        pass
