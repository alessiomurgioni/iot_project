class DigitalTwin:
    def __init__(self):
        self.digital_replicas: list = []
        self.active_services: dict = {}

    def add_digital_replica(self, dr) -> None:
        self.digital_replicas.append(dr)

    def add_service(self, service) -> None:
        if isinstance(service, type):
            service = service()
        self.active_services[service.name] = service

    def list_services(self):
        return list(self.active_services.keys())

    def execute_service(self, service_name: str, **kwargs):
        if service_name not in self.active_services:
            raise ValueError(f"Service {service_name} not found")
        data = {"digital_replicas": self.digital_replicas}
        return self.active_services[service_name].execute(data, **kwargs)
