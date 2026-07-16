from abc import ABC, abstractmethod


class BaseService(ABC):
    def __init__(self):
        self.name = self.__class__.__name__

    @abstractmethod
    def execute(self, data: dict, dr_type: str = None, attribute: str = None):
        pass
