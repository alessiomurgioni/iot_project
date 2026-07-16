class DigitalTwin:
    def __init__(self):
        self.digital_replicas = []
        self.active_services = {}

    def add_digital_replica(self, dr_instance) -> None:
        """
        Attach a Digital Replica to the twin.

        Input:
        - dr_instance: the Digital Replica document
        """
        self.digital_replicas.append(dr_instance)

    def add_service(self, service):
        """
        Attach a service instance to the twin.

        Input:
        - service: a service instance
        """
        if isinstance(service, type):
            service = service()
        self.active_services[service.name] = service

    def list_services(self):
        """
        List the services attached to the twin.

        Output:
        - list of attached service names
        """
        return list(self.active_services.keys())

    def remove_service(self, service_name: str) -> None:
        """
        Remove a service from the twin.

        Input:
        - service_name: name of the service to remove
        """
        if service_name in self.active_services:
            del self.active_services[service_name]

    def get_dt_data(self):
        """
        Get the twin's Digital Replicas as a dict.

        Output:
        - dict with a "digital_replicas" key
        """
        return {"digital_replicas": self.digital_replicas}

    def execute_service(self, service_name: str, **kwargs):
        """
        Run a given service.

        Inputs:
        - service_name: name of the service to run
        - kwargs: arguments forwarded to the service's execute()

        """
        if service_name not in self.active_services:
            raise ValueError(f"Service {service_name} not found")
        service = self.active_services[service_name]
        data = {"digital_replicas": self.digital_replicas}
        return service.execute(data, **kwargs)
