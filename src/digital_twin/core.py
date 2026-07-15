from typing import Dict, List, Any


class DigitalTwin:

    def __init__(self):
        self.digital_replicas: List = []
        self.active_services: Dict = {}

    def add_digital_replica(self, dr_instance: Any) -> None:
        self.digital_replicas.append(dr_instance)

    def add_service(self, service):
        if isinstance(service, type):
            service = service()
        self.active_services[service.name] = service

    def list_services(self):
        return list(self.active_services.keys())

    def remove_service(self, service_name: str) -> None:
        if service_name in self.active_services:
            del self.active_services[service_name]

    def get_dt_data(self):
        return {"digital_replicas": self.digital_replicas}

    def execute_service(self, service_name: str, **kwargs):
        if service_name not in self.active_services:
            raise ValueError(f"Service {service_name} not found")
        service = self.active_services[service_name]
        data = {"digital_replicas": self.digital_replicas}
        return service.execute(data, **kwargs)
