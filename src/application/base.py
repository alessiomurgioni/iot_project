from abc import ABC, abstractmethod

class BaseApplication(ABC):

    def __init__(self):
        self.name = self.__class__.__name__

    @abstractmethod
    def process_data(self, data: dict) -> dict:
        pass
