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
        """
        Open the MongoDB connection and ensure it exist.
        """
        try:
            self.client = MongoClient(self.connection_string)
            self.db = self.client[self.db_name]
            self._ensure_platform_indexes()
        except Exception as e:
            raise ConnectionError(f"Failed to connect to MongoDB: {str(e)}")

    def disconnect(self) -> None:
        """
        Close the MongoDB connection.
        """
        if self.client:
            self.client.close()
            self.client = None
            self.db = None

    def is_connected(self) -> bool:
        """
        Check whether a MongoDB connection is currently open.

        Output:
        - True if connected, else False
        """
        return self.client is not None and self.db is not None

    def _ensure_platform_indexes(self) -> None:
        """
        Create the indexes used by the users/memberships collections.
        """
        try:
            self.db["users"].create_index([("username", ASCENDING)], unique=True)
            self.db["users"].create_index([("email_index", ASCENDING)], unique=True, sparse=True)
            self.db["memberships"].create_index(
                [("username", ASCENDING), ("dt_id", ASCENDING)], unique=True)
            self.db["memberships"].create_index([("dt_id", ASCENDING)])
        except Exception as exc:
            print(f"[DB] Warning creating platform indexes: {exc}")

    def _decrypt_dr_doc(self, doc: dict):
        """
        Decrypt the "enc" payload on a raw Digital Replica document.

        Inputs:
        - doc: raw Digital Replica document

        Output:
        - the document with decrypted data/profile fields, or None
        """
        if not doc:
            return doc
        enc = doc.pop("enc", None)
        if enc is not None:
            payload = decrypt_payload(enc)
            doc["_id"] = payload.get("device_id", doc["_id"])
            doc["data"] = payload.get("data", {})
            doc["profile"] = payload.get("profile", {})
        return doc

    def save_dr(self, dr_type: str, dr_data: dict) -> str:
        """
        Insert a new Digital Replica document.

        Inputs:
        - dr_type: the replica's schema type
        - dr_data: replica document with _id, data, profile, metadata

        Output:
        - the replica's real id
        """
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

    def get_dr(self, dr_type: str, dr_id: str):
        """
        Fetch and decrypt a Digital Replica by type + id.

        Inputs:
        - dr_type: the replica's schema type
        - dr_id: the replica's id

        Output:
        - the decrypted replica document, or None if not found
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")
        collection_name = self.schema_registry.get_collection_name(dr_type)
        doc = self.db[collection_name].find_one({"_id": pseudonymize(dr_id)})
        return self._decrypt_dr_doc(doc)

    def query_drs(self, dr_type: str, query: dict = None) -> list:
        """
        Query and decrypt Digital Replicas of a given type.

        Inputs:
        - dr_type: the replica's schema type
        - query: optional MongoDB filter dict

        Output:
        - list of decrypted replica documents
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")
        collection_name = self.schema_registry.get_collection_name(dr_type)
        docs = list(self.db[collection_name].find(query or {}))
        return [self._decrypt_dr_doc(d) for d in docs]

    def update_dr(self, dr_type: str, dr_id: str, update_data: dict) -> None:
        """
        Overwrite a Digital Replica's data/profile/metadata.

        Inputs:
        - dr_type: the replica's schema type
        - dr_id: the replica's id
        - update_data: new data/profile/metadata values

        Outputs:
        - None
        """
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
        """
        Delete a Digital Replica by type + id.

        Inputs:
        - dr_type: the replica's schema type
        - dr_id: the replica's id

        Outputs:
        - None
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")
        collection_name = self.schema_registry.get_collection_name(dr_type)
        result = self.db[collection_name].delete_one({"_id": pseudonymize(dr_id)})
        if result.deleted_count == 0:
            raise ValueError(f"Digital Replica not found: {dr_id}")

    def _decrypt_user_doc(self, doc: dict):
        """
        Decrypt a user's email.

        Input:
        - doc: raw user document, or None

        Output:
        - the document with a decrypted "email" field, or None
        """
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
        """
        Insert a new user account.

        Inputs:
        - username: the account's username
        - password_hash: hashed password
        - email: optional email address
        """
        doc = {"username": username, "password": password_hash}
        if email:
            doc["email_index"] = pseudonymize(email)
            doc["email_enc"] = encrypt_payload(email)
        self.db["users"].insert_one(doc)

    def get_user(self, username: str):
        """
        Fetch a user by username.

        Input:
        - username: the account's username

        Output:
        - the user document, or None if not found
        """
        doc = self.db["users"].find_one({"username": username})
        return self._decrypt_user_doc(doc)

    def get_user_by_email(self, email: str):
        """
        Fetch a user by email address.

        Input:
        - email: the account's email address

        Output:
        - the user document, or None if not found
        """
        doc = self.db["users"].find_one(
            {"$or": [{"email_index": pseudonymize(email)}, {"email": email}]}
        )
        return self._decrypt_user_doc(doc)

    def list_member_emails(self, dt_id: str) -> list:
        """
        List the emails of all users with a membership on a twin.

        Inputs:
        - dt_id: the twin's id

        Outputs:
        - list of member email addresses
        """
        emails = []
        for m in self.db["memberships"].find({"dt_id": dt_id}, {"username": 1, "_id": 0}):
            user = self.get_user(m["username"])
            if user and user.get("email"):
                emails.append(user["email"])
        return emails

    def list_users(self) -> list:
        """
        List all users.

        Output:
        - list of user documents
        """
        docs = list(self.db["users"].find({}, {"password": 0, "_id": 0}))
        return [self._decrypt_user_doc(d) for d in docs]

    def delete_user(self, username: str) -> int:
        """
        Delete a user account by username.

        Input:
        - username: the account's username

        Output:
        - number of documents deleted
        """
        return self.db["users"].delete_one({"username": username}).deleted_count

    def save_device(self, device_id: str, token_hash: str, owner_key_hash: str, latitude: str, longitude: str) -> None:
        """
        Register a new physical device.

        Inputs:
        - device_id: the device's id
        - token_hash: hashed device auth token
        - owner_key_hash: hashed owner key
        - latitude: encrypted latitude
        - longitude: encrypted longitude
        """
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

    def get_device(self, device_id: str):
        """
        Fetch a device document by id.

        Input:
        - device_id: the device's id

        Output:
        - the device document, or None if not found
        """
        if not device_id:
            return None
        return self.db["devices"].find_one({"_id": device_id})

    def set_device_twin(self, device_id: str, dt_id: str) -> None:
        """
        Record which twin a device has been claimed into.

        Inputs:
        - device_id: the device's id
        - dt_id: the twin's id
        """
        self.db["devices"].update_one({"_id": device_id}, {"$set": {"claimed_by_dt": dt_id}})

    def add_membership(self, username: str, dt_id: str, role: str = "member",
                       can_control: bool = True, label: str = None) -> None:
        """
        Create or update a user's membership on a twin.

        Inputs:
        - username: the account's username
        - dt_id: the twin's id
        - role: "member" or "owner"
        - can_control: whether the member can change control settings
        - label: optional display label
        """
        set_fields = {"role": role, "can_control": bool(can_control)}
        if label:
            set_fields["label"] = label
        self.db["memberships"].update_one(
            {"username": username, "dt_id": dt_id},
            {"$set": set_fields, "$setOnInsert": {"added_at": datetime.utcnow()}},
            upsert=True,
        )

    def get_membership(self, username: str, dt_id: str):
        """
        Fetch a user's membership on a twin.

        Inputs:
        - username: the account's username
        - dt_id: the twin's id

        Output:
        - the membership document, or None
        """
        return self.db["memberships"].find_one({"username": username, "dt_id": dt_id})

    def list_memberships_for_user(self, username: str) -> list:
        """
        List all twins a user belongs to.

        Inputs:
        - username: the account's username

        Outputs:
        - list of membership documents
        """
        return list(self.db["memberships"].find({"username": username}, {"_id": 0}))

    def list_memberships_for_twin(self, dt_id: str) -> list:
        """
        List all members of a twin.

        Inputs:
        - dt_id: the twin's id

        Outputs:
        - list of membership documents
        """
        return list(self.db["memberships"].find({"dt_id": dt_id}, {"_id": 0}))

    def set_can_control(self, username: str, dt_id: str, can_control: bool) -> int:
        """
        Update a member's control permission.

        Inputs:
        - username: the account's username
        - dt_id: the twin's id
        - can_control: new permission value
        """
        return self.db["memberships"].update_one(
            {"username": username, "dt_id": dt_id},
            {"$set": {"can_control": bool(can_control)}},
        ).matched_count

    def remove_membership(self, username: str, dt_id: str) -> int:
        """
        Remove a user's membership from a twin.

        Input:
        - username: the account's username
        - dt_id: the twin's id
        """
        return self.db["memberships"].delete_one(
            {"username": username, "dt_id": dt_id}).deleted_count

    def count_owners(self, dt_id: str) -> int:
        """
        Count the owner-role members of a twin.

        Input:
        - dt_id: the twin's id

        Output:
        - number of owner memberships
        """
        return self.db["memberships"].count_documents({"dt_id": dt_id, "role": "owner"})
