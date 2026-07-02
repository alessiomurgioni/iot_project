from typing import Dict, Optional
from datetime import datetime

from pymongo import MongoClient

import config
from ..virtualization.digital_replica.schema_registry import SchemaRegistry

# Single-house deployment: one Digital Replica document, always keyed "latest".
_DR_DOC_ID = "latest"


class DatabaseService:
    """
    Owns the MongoDB connection for the Digital Twin architecture's own data:
    Digital Replicas (db: digital_replica) and the Digital Twin registry
    (db: digital_twins). Deliberately independent of the project's root
    db.py, which only manages user accounts — the same separation the
    reference repo has, where its DatabaseService connects to Mongo
    directly rather than depending on a module that also handles
    unrelated concerns (auth, accounts).

    Two MongoClients pointing at the same physical MongoDB instance is a
    fine tradeoff here: it keeps "the twin's persistence" and "the app's
    user database" from depending on each other's code, so either could
    be swapped out (different DB, different auth system) independently.
    """

    def __init__(self, schema_registry: SchemaRegistry,
                 connection_string: str = None, db_name: str = None):
        self.schema_registry = schema_registry
        self.client = MongoClient(connection_string or config.MONGO_URI,
                                   serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name or config.MONGO_DB]
        self.digital_replica = self.db["digital_replica"]
        self.digital_twins = self.db["digital_twins"]

    def is_connected(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    # ── Digital Replica persistence ─────────────────────────────────────
    def save_dr(self, dr_type: str, dr_data: Dict) -> str:
        doc = dict(dr_data)
        doc["_id"] = _DR_DOC_ID
        self.digital_replica.update_one({"_id": _DR_DOC_ID}, {"$set": doc}, upsert=True)
        return _DR_DOC_ID

    def get_dr(self, dr_type: str, dr_id: str) -> Optional[Dict]:
        return self.digital_replica.find_one({"_id": dr_id})

    def update_dr(self, dr_type: str, dr_id: str, dr_data: Dict) -> None:
        self.save_dr(dr_type, dr_data)

    # ── Digital Twin registry persistence ───────────────────────────────
    def insert_dt(self, dt_data: Dict) -> None:
        self.digital_twins.insert_one(dt_data)

    def get_dt(self, dt_id: str) -> Optional[Dict]:
        return self.digital_twins.find_one({"_id": dt_id})

    def get_dt_by_name(self, name: str) -> Optional[Dict]:
        return self.digital_twins.find_one({"name": name})

    def list_dts(self):
        return list(self.digital_twins.find())

    def push_dr_reference(self, dt_id: str, dr_type: str, dr_id: str) -> None:
        self.digital_twins.update_one(
            {"_id": dt_id},
            {
                "$push": {"digital_replicas": {"type": dr_type, "id": dr_id}},
                "$set": {"metadata.updated_at": datetime.utcnow()},
            },
        )

    def push_service_reference(self, dt_id: str, service_name: str, service_config: Dict = None) -> None:
        self.digital_twins.update_one(
            {"_id": dt_id},
            {
                "$push": {"services": {
                    "name": service_name,
                    "config": service_config or {},
                    "status": "active",
                    "added_at": datetime.utcnow(),
                }},
                "$set": {"metadata.updated_at": datetime.utcnow()},
            },
        )
