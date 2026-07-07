from typing import Dict

from src.digital_twin.dt_factory import DTFactory
from config import catalog

"""
Domotic-platform extension of the generic reference DTFactory. Everything
here is DHome-specific and has no business living in the reference-generic
dt_factory.py: which concrete service classes back which service names,
provisioning a twin for a freshly-claimed physical device (device-claiming is
a domotic-platform concept, not a reference one), and device liveness (reads
DHome's own "last_report" telemetry field).

A future product line (e.g. DGarage) would get its own subclass the same way,
each contributing its own services + provisioning flow without the two
stepping on each other or bloating the generic factory.
"""


class DHomeDTFactory(DTFactory):
    def _get_service_module_mapping(self) -> Dict[str, str]:
        return {
            "ClimateControlService": "src.services.DHome.climate_control",
            "MonitoringService": "src.services.DHome.monitoring",
            "FireNotificationService": "src.services.DHome.fire_notification",
        }

    def create_twin_for_device(self, device_id: str, product: str = None,
                               house_name: str = None) -> str:
        """Provision a fresh twin for a just-claimed device of the given product
        type. Looks the product up in the fixed catalog to pick the Digital
        Replica schema and the services to attach, builds a new DR (id ==
        device_id, unique per unit), registers the twin (recording its product
        + schema_type), links the DR, and attaches the product's services.
        Returns the twin id. Raises ValueError for an unknown product."""
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
        """Device liveness from the replica's last_report vs STALE_AFTER_S."""
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
