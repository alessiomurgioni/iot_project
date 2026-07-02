import os
import uuid
from datetime import datetime

# config.py lives at the project root; a plain import works because the
# project root is on sys.path when running `python app.py` from there.
# Note: no `import db` here anymore — DTFactory no longer depends on the
# root-level user-accounts module at all, only on DatabaseService's own
# MongoDB connection.
import config

from .core import DigitalTwin
from ..virtualization.digital_replica.schema_registry import SchemaRegistry
from ..virtualization.digital_replica.dr_factory import DRFactory
from ..services.database_service import DatabaseService
from ..services.climate_control import ClimateControlService
from ..services.monitoring_service import MonitoringService

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "schemas", "database.yaml")

# Mirrors the reference repo's _get_service_module_mapping(): the set of
# service classes a Digital Twin is allowed to be composed of.
_SERVICE_MAPPING = {
    "ClimateControlService": ClimateControlService,
    "MonitoringService": MonitoringService,
}


class DTFactory:
    """
    Factory for creating and loading Digital Twins.

    A Digital Twin is a persisted registry record (DatabaseService.digital_twins)
    that references which Digital Replica(s) and Service(s) it's composed of —
    it does NOT hold sensor data itself. The Digital Replica
    (DatabaseService.digital_replica) holds the actual house state.
    """

    def __init__(self):
        self.registry = SchemaRegistry()
        self.registry.load_schema("house_climate", _SCHEMA_PATH)
        self.dr_factory = DRFactory(self.registry, "house_climate")
        # DatabaseService owns its own MongoDB connection — DTFactory has
        # no direct Mongo dependency of its own.
        self.db_service = DatabaseService(self.registry)

    # ── Digital Twin registry ────────────────────────────────────────────
    def create_dt(self, name: str, description: str = "") -> str:
        dt_data = {
            "_id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "digital_replicas": [],  # [{type, id}, ...]
            "services": [],          # [{name, config, status, added_at}, ...]
            "metadata": {
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "status": "active",
            },
        }
        self.db_service.insert_dt(dt_data)
        return dt_data["_id"]

    def get_dt(self, dt_id: str):
        return self.db_service.get_dt(dt_id)

    def get_dt_by_name(self, name: str):
        return self.db_service.get_dt_by_name(name)

    def list_dts(self):
        return self.db_service.list_dts()

    def add_digital_replica(self, dt_id: str, dr_type: str, dr_id: str) -> None:
        dr = self.db_service.get_dr(dr_type, dr_id)
        if not dr:
            raise ValueError(f"Digital Replica not found: {dr_id}")
        self.db_service.push_dr_reference(dt_id, dr_type, dr_id)

    def add_service(self, dt_id: str, service_name: str, service_config: dict = None) -> None:
        if service_name not in _SERVICE_MAPPING:
            raise ValueError(f"Service {service_name} not found in service mapping")
        self.db_service.push_service_reference(dt_id, service_name, service_config)

    # ── Resolve a registry record into a live DigitalTwin object ────────
    def create_dt_from_data(self, dt_data: dict) -> DigitalTwin:
        dt = DigitalTwin()

        for dr_ref in dt_data.get("digital_replicas", []):
            dr = self.db_service.get_dr(dr_ref["type"], dr_ref["id"])
            if dr:
                dt.add_digital_replica(dr)

        for svc in dt_data.get("services", []):
            service_class = _SERVICE_MAPPING.get(svc["name"])
            if service_class:
                dt.add_service(service_class)

        return dt

    def get_dt_instance(self, dt_id: str):
        """Load a fully initialized DigitalTwin instance by twin ID."""
        dt_data = self.get_dt(dt_id)
        if not dt_data:
            return None
        return self.create_dt_from_data(dt_data)

    # ── Bootstrap: this app manages exactly one house, so ensure its
    #    twin registry entry exists once at startup rather than creating
    #    twins on the fly per-request ───────────────────────────────────
    def ensure_house_dt(self) -> str:
        existing = self.get_dt_by_name("home")
        if existing:
            dt_id = existing["_id"]
            # Backfill any service that's been added to _SERVICE_MAPPING
            # since this twin was first registered (e.g. MonitoringService
            # added after ClimateControlService was already in place).
            registered = {s["name"] for s in existing.get("services", [])}
            for service_name in _SERVICE_MAPPING:
                if service_name not in registered:
                    self.add_service(dt_id, service_name)
            return dt_id

        dr = self.db_service.get_dr("house_climate", "latest")
        if not dr or "data" not in dr or dr.get("type") != "house_climate":
            dr = self.dr_factory.create_dr({"house_name": "home"})
            self.db_service.save_dr("house_climate", dr)
            # save_dr() always stores single-house DRs under the fixed
            # Mongo _id "latest" regardless of the UUID DRFactory assigned
            # in memory — keep the reference consistent with what's
            # actually persisted.
            dr["_id"] = "latest"

        dt_id = self.create_dt(name="home", description="DHome climate digital twin")
        self.add_digital_replica(dt_id, "house_climate", dr["_id"])
        for service_name in _SERVICE_MAPPING:
            self.add_service(dt_id, service_name)
        return dt_id

    # ── Persistence for the Digital Replica after a service mutates it ──
    def persist_dr(self, dt: DigitalTwin) -> None:
        dr = dt.digital_replicas[0]
        dr["metadata"]["updated_at"] = datetime.utcnow()
        self.dr_factory.validate(dr)  # raises ValueError on schema violation
        self.db_service.update_dr("house_climate", dr["_id"], dr)

    def is_online(self) -> bool:
        """'Online' = the NodeMCU posted a /api/report within STALE_AFTER_S seconds."""
        dr = self.db_service.get_dr("house_climate", "latest")
        if not dr:
            return False
        last = dr.get("data", {}).get("last_report")
        if not last:
            return False
        return (datetime.utcnow() - last).total_seconds() <= config.STALE_AFTER_S
