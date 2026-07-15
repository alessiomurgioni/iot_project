from typing import Dict, List, Optional, Any
from pymongo import MongoClient, ASCENDING
from datetime import datetime
from src.virtualization.digital_replica.schema_registry import SchemaRegistry
from src.services.encryption import encrypt_payload, decrypt_payload, pseudonymize


class DatabaseService:
    def __init__(self, connection_string: str, db_name: str,
                 schema_registry: SchemaRegistry):
        self.connection_string = connection_string
        self.db_name = db_name
        self.schema_registry = schema_registry
        self.client = None
        self.db = None

    def connect(self) -> None:
        try:
            self.client = MongoClient(self.connection_string)
            self.db = self.client[self.db_name]
            self._ensure_platform_indexes()
        except Exception as e:
            raise ConnectionError(f"Failed to connect to MongoDB: {str(e)}")

    def disconnect(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
            self.db = None

    def is_connected(self) -> bool:
        return self.client is not None and self.db is not None

    def _ensure_platform_indexes(self) -> None:
        try:
            self.db["users"].create_index([("username", ASCENDING)], unique=True)
            self.db["users"].create_index([("email_index", ASCENDING)], unique=True, sparse=True)
            self.db["memberships"].create_index(
                [("username", ASCENDING), ("dt_id", ASCENDING)], unique=True)
            self.db["memberships"].create_index([("dt_id", ASCENDING)])
        except Exception as exc:
            print(f"[DB] Warning creating platform indexes: {exc}")

    def _decrypt_dr_doc(self, doc: Optional[Dict]) -> Optional[Dict]:
        if not doc:
            return doc
        enc = doc.pop("enc", None)
        if enc is not None:
            payload = decrypt_payload(enc)
            doc["_id"] = payload.get("device_id", doc["_id"])
            doc["data"] = payload.get("data", {})
            doc["profile"] = payload.get("profile", {})
        return doc

    def save_dr(self, dr_type: str, dr_data: Dict) -> str:
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")
        collection_name = self.schema_registry.get_collection_name(dr_type)
        self.schema_registry.get_validation_schema(dr_type)  # ensures schema is loaded
        real_id = dr_data["_id"]
        doc = {
            "_id": pseudonymize(real_id),
            "type": dr_data.get("type", dr_type),
            "metadata": dr_data.get("metadata", {}),
            "enc": encrypt_payload({
                "device_id": real_id,
                "data": dr_data.get("data", {}),
                "profile": dr_data.get("profile", {}),
            }),
        }
        self.db[collection_name].insert_one(doc)
        return real_id

    def get_dr(self, dr_type: str, dr_id: str) -> Optional[Dict]:
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")
        collection_name = self.schema_registry.get_collection_name(dr_type)
        doc = self.db[collection_name].find_one({"_id": pseudonymize(dr_id)})
        return self._decrypt_dr_doc(doc)

    def query_drs(self, dr_type: str, query: Dict = None) -> List[Dict]:
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")
        collection_name = self.schema_registry.get_collection_name(dr_type)
        docs = list(self.db[collection_name].find(query or {}))
        return [self._decrypt_dr_doc(d) for d in docs]

    def update_dr(self, dr_type: str, dr_id: str, update_data: Dict) -> None:
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")
        collection_name = self.schema_registry.get_collection_name(dr_type)
        metadata = dict(update_data.get("metadata") or {})
        metadata["updated_at"] = datetime.utcnow()
        set_fields = {
            "type": update_data.get("type", dr_type),
            "metadata": metadata,
            "enc": encrypt_payload({
                "device_id": dr_id,
                "data": update_data.get("data", {}),
                "profile": update_data.get("profile", {}),
            }),
        }
        result = self.db[collection_name].update_one(
            {"_id": pseudonymize(dr_id)}, {"$set": set_fields}
        )
        if result.matched_count == 0:
            raise ValueError(f"Digital Replica not found: {dr_id}")

    def delete_dr(self, dr_type: str, dr_id: str) -> None:
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")
        collection_name = self.schema_registry.get_collection_name(dr_type)
        result = self.db[collection_name].delete_one({"_id": pseudonymize(dr_id)})
        if result.deleted_count == 0:
            raise ValueError(f"Digital Replica not found: {dr_id}")

    def _decrypt_user_doc(self, doc: Optional[Dict]) -> Optional[Dict]:
        if not doc:
            return doc
        enc = doc.pop("email_enc", None)
        doc.pop("email_index", None)
        if enc:
            try:
                doc["email"] = decrypt_payload(enc)
            except Exception:
                doc["email"] = None
        elif doc.get("email"):
            legacy_email = doc["email"]
            self.db["users"].update_one(
                {"username": doc["username"]},
                {"$set": {"email_index": pseudonymize(legacy_email),
                          "email_enc": encrypt_payload(legacy_email)},
                 "$unset": {"email": ""}},
            )
        return doc

    def create_user(self, username: str, password_hash: str, email: str = None) -> None:
        doc = {"username": username, "password": password_hash}
        if email:
            doc["email_index"] = pseudonymize(email)
            doc["email_enc"] = encrypt_payload(email)
        self.db["users"].insert_one(doc)

    def get_user(self, username: str) -> Optional[Dict]:
        doc = self.db["users"].find_one({"username": username})
        return self._decrypt_user_doc(doc)

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        doc = self.db["users"].find_one(
            {"$or": [{"email_index": pseudonymize(email)}, {"email": email}]}
        )
        return self._decrypt_user_doc(doc)

    def list_member_emails(self, dt_id: str) -> List[str]:
        emails = []
        for m in self.db["memberships"].find({"dt_id": dt_id}, {"username": 1, "_id": 0}):
            user = self.get_user(m["username"])
            if user and user.get("email"):
                emails.append(user["email"])
        return emails

    def list_users(self) -> List[Dict]:
        docs = list(self.db["users"].find({}, {"password": 0, "_id": 0}))
        return [self._decrypt_user_doc(d) for d in docs]

    def delete_user(self, username: str) -> int:
        return self.db["users"].delete_one({"username": username}).deleted_count

    def save_device(self, device_id: str, token_hash: str, owner_key_hash: str, latitude: str, longitude: str) -> None:
        self.db["devices"].update_one(
            {"_id": device_id},
            {"$setOnInsert": {
                "_id": device_id,
                "token_hash": token_hash,
                "owner_key_hash": owner_key_hash,
                "latitude": latitude,
                "longitude": longitude,
                "claimed_by_dt": None,
            }},
            upsert=True,
        )

    def get_device(self, device_id: str) -> Optional[Dict]:
        if not device_id:
            return None
        return self.db["devices"].find_one({"_id": device_id})

    def set_device_twin(self, device_id: str, dt_id: str) -> None:
        self.db["devices"].update_one({"_id": device_id}, {"$set": {"claimed_by_dt": dt_id}})

    def add_membership(self, username: str, dt_id: str, role: str = "member",
                       can_control: bool = True, label: str = None) -> None:
        set_fields = {"role": role, "can_control": bool(can_control)}
        if label:
            set_fields["label"] = label
        self.db["memberships"].update_one(
            {"username": username, "dt_id": dt_id},
            {"$set": set_fields, "$setOnInsert": {"added_at": datetime.utcnow()}},
            upsert=True,
        )

    def get_membership(self, username: str, dt_id: str) -> Optional[Dict]:
        return self.db["memberships"].find_one({"username": username, "dt_id": dt_id})

    def list_memberships_for_user(self, username: str) -> List[Dict]:
        return list(self.db["memberships"].find({"username": username}, {"_id": 0}))

    def list_memberships_for_twin(self, dt_id: str) -> List[Dict]:
        return list(self.db["memberships"].find({"dt_id": dt_id}, {"_id": 0}))

    def set_can_control(self, username: str, dt_id: str, can_control: bool) -> int:
        return self.db["memberships"].update_one(
            {"username": username, "dt_id": dt_id},
            {"$set": {"can_control": bool(can_control)}},
        ).matched_count

    def remove_membership(self, username: str, dt_id: str) -> int:
        return self.db["memberships"].delete_one(
            {"username": username, "dt_id": dt_id}).deleted_count

    def count_owners(self, dt_id: str) -> int:
        return self.db["memberships"].count_documents({"dt_id": dt_id, "role": "owner"})
