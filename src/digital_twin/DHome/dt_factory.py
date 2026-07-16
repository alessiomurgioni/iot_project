from src.digital_twin.dt_factory import DTFactory
from config import catalog


class DHomeDTFactory(DTFactory):
    def _get_service_module_mapping(self) -> dict:
        """
        Map DHome service names to their implementing modules.

        Output:
        - dict of service name -> module path
        """
        return {
            "ClimateControlService": "src.services.DHome.climate_control",
            "FireNotificationService": "src.services.DHome.fire_notification",
        }

    def create_twin_for_device(self, device_id: str, product: str = None,
                               house_name: str = None) -> str:
        """
        Create a twin for a device.

        Inputs:
        - device_id: physical device id, used as the Digital Replica id
        - product: product key
        - house_name: optional display name for the profile

        Output:
        - the new twin's id
        """
        product = product or catalog.DEFAULT_PRODUCT
        spec = catalog.get_product(product)
        if not spec:
            raise ValueError(f"Unknown product type: {product!r}")
        schema_type = spec["schema_type"]

        profile = {"house_name": house_name or device_id}

        dr = self.dr_factory_for(schema_type).create_dr(schema_type, {"profile": profile})
        dr["_id"] = device_id
        self.db_service.save_dr(schema_type, dr)

        dt_id = self.create_dt(name=device_id, product=product, schema_type=schema_type)
        self.add_digital_replica(dt_id, schema_type, dr["_id"])
        for service_name in spec["services"]:
            self.add_service(dt_id, service_name)
        return dt_id

    def is_online(self, dt_id: str) -> bool:
        """
        Check if a device is currently online.

        Input:
        - dt_id: the twin's id

        Output:
        - True if the device reported recently enough, else False
        """
        from config import settings
        from datetime import datetime

        reg = self.get_dt(dt_id)
        if not reg:
            return False
        refs = reg.get("digital_replicas", [])
        if not refs:
            return False
        dr = self.db_service.get_dr(refs[0]["type"], refs[0]["id"])
        if not dr:
            return False
        last = dr.get("data", {}).get("last_report")
        if not last:
            return False
        return (datetime.utcnow() - last).total_seconds() <= settings.STALE_AFTER_S
