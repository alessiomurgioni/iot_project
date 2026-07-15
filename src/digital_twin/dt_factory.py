from typing import Dict, List, Optional
from datetime import datetime
from bson import ObjectId

from src.services.database_service import DatabaseService
from src.virtualization.digital_replica.schema_registry import SchemaRegistry
from src.virtualization.digital_replica.dr_factory import DRFactory
from src.digital_twin.core import DigitalTwin
from src.services.encryption import encrypt_payload, decrypt_payload, pseudonymize
from config import catalog


class DTFactory:
    def __init__(self, db_service: DatabaseService, schema_registry: SchemaRegistry,
                 dr_factory: DRFactory = None):
        self.db_service = db_service
        self.schema_registry = schema_registry
        self.dr_factories: Dict[str, DRFactory] = {}
        for product in catalog.list_products():
            stype, spath = product["schema_type"], product["schema_path"]
            if stype not in self.schema_registry.schemas:
                self.schema_registry.load_schema(stype, spath)
            if stype not in self.dr_factories:
                self.dr_factories[stype] = DRFactory(spath)

        self._init_dt_collection()

    def dr_factory_for(self, schema_type: str) -> DRFactory:
        if schema_type not in self.dr_factories:
            raise ValueError(f"No DRFactory for schema type '{schema_type}'")
        return self.dr_factories[schema_type]

    def _get_service_module_mapping(self) -> Dict[str, str]:
        return {}

    def create_dt(self, name: str, product: str = None, schema_type: str = None) -> str:
        dt_data = {
            "_id": str(ObjectId()),
            "name": pseudonymize(name),
            "product": product,
            "schema_type": schema_type,
            "digital_replicas": [],
            "services": [],
            "metadata": {
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "status": "active",
            },
        }
        self.db_service.db["digital_twins"].insert_one(dt_data)
        return dt_data["_id"]

    def add_digital_replica(self, dt_id: str, dr_type: str, dr_id: str) -> None:
        dr = self.db_service.get_dr(dr_type, dr_id)
        if not dr:
            raise ValueError(f"Digital Replica not found: {dr_id}")
        self.db_service.db["digital_twins"].update_one(
            {"_id": dt_id},
            {"$push": {"digital_replicas": {"type": dr_type, "id_enc": encrypt_payload(dr_id)}},
             "$set": {"metadata.updated_at": datetime.utcnow()}},
        )

    def _decrypt_dt_doc(self, doc: Optional[Dict]) -> Optional[Dict]:
        if not doc:
            return doc
        doc["digital_replicas"] = [
            {"type": r.get("type"), "id": decrypt_payload(r["id_enc"])}
            for r in doc.get("digital_replicas", [])
        ]
        return doc

    def add_service(self, dt_id: str, service_name: str, service_config: Dict = None) -> None:
        mapping = self._get_service_module_mapping()
        if service_name not in mapping:
            raise ValueError(f"Service {service_name} not configured in module mapping")
        module_name = mapping[service_name]
        try:
            service_module = __import__(module_name, fromlist=[service_name])
            getattr(service_module, service_name)()
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Failed to load service {service_name} from {module_name}: {e}")
        self.db_service.db["digital_twins"].update_one(
            {"_id": dt_id},
            {"$push": {"services": {
                "name": service_name, "config": service_config or {},
                "status": "active", "added_at": datetime.utcnow()}},
                "$set": {"metadata.updated_at": datetime.utcnow()}},
        )

    def get_dt(self, dt_id: str) -> Optional[Dict]:
        doc = self.db_service.db["digital_twins"].find_one({"_id": dt_id})
        return self._decrypt_dt_doc(doc)

    def list_dts(self) -> List[Dict]:
        docs = list(self.db_service.db["digital_twins"].find())
        return [self._decrypt_dt_doc(d) for d in docs]

    def _init_dt_collection(self) -> None:
        if not self.db_service.is_connected():
            raise ConnectionError("Database service not connected")
        db = self.db_service.db
        if "digital_twins" not in db.list_collection_names():
            db.create_collection("digital_twins")
            dt = db["digital_twins"]
            dt.create_index("name", unique=True)
            dt.create_index("metadata.created_at")
            dt.create_index("metadata.updated_at")

    def create_dt_from_data(self, dt_data: dict) -> DigitalTwin:
        dt = DigitalTwin()
        for dr_ref in dt_data.get("digital_replicas", []):
            dr = self.db_service.get_dr(dr_ref["type"], dr_ref["id"])
            if dr:
                dt.add_digital_replica(dr)
        mapping = self._get_service_module_mapping()
        for service_data in dt_data.get("services", []):
            service_name = service_data["name"]
            if service_name in mapping:
                try:
                    module = __import__(mapping[service_name], fromlist=[service_name])
                    dt.add_service(getattr(module, service_name)())
                except Exception as e:
                    print(f"[DT] Error adding service {service_name}: {e}")
        return dt

    def get_dt_instance(self, dt_id: str) -> Optional[DigitalTwin]:
        dt_data = self.get_dt(dt_id)
        if not dt_data:
            return None
        return self.create_dt_from_data(dt_data)

    def _dr_type_of(self, dt: DigitalTwin) -> str:
        return dt.digital_replicas[0]["type"]

    def persist_dr(self, dt: DigitalTwin) -> None:
        dr = dt.digital_replicas[0]
        self.db_service.update_dr(dr["type"], dr["_id"], dr)
