#!/usr/bin/env python3
"""
Provision a physical device so the platform will accept it. Factory step, run
once per unit. Stores only hashes; the raw token and owner key go on the box.

Usage (from the project root):
    python -m scripts.provision_device DEVICE_ID DEVICE_TOKEN OWNER_KEY

Example:
    python -m scripts.provision_device dhome-001 tok-secret-001 owner-key-001 42.36028 -71.05778

DEVICE_ID + DEVICE_TOKEN must match nodemcu_webapp.ino. A user then claims the
device from the web home page with DEVICE_ID + DEVICE_TOKEN, optionally adding
OWNER_KEY to gain management rights.
"""
# !/usr/bin/env python3


import sys
from werkzeug.security import generate_password_hash
from config.config_loader import ConfigLoader
from src.virtualization.digital_replica.schema_registry import SchemaRegistry
from src.services.database_service import DatabaseService
from src.services.encryption import encrypt_payload


def main():
    if len(sys.argv) != 6:
        print(
            "Usage: python -m scripts.provision_device "
            "DEVICE_ID DEVICE_TOKEN OWNER_KEY LATITUDE LONGITUDE"
        )
        sys.exit(1)

    device_id = sys.argv[1]
    device_token = sys.argv[2]
    owner_key = sys.argv[3]
    latitude = sys.argv[4]
    longitude = sys.argv[5]

    db_config = ConfigLoader.load_database_config()
    conn = ConfigLoader.build_connection_string(db_config)

    db = DatabaseService(
        conn,
        db_config["settings"]["name"],
        SchemaRegistry()
    )

    db.connect()

    try:
        db.save_device(
            device_id=device_id,
            token_hash=generate_password_hash(device_token),
            owner_key_hash=generate_password_hash(owner_key),
            latitude=encrypt_payload(float(latitude)),
            longitude=encrypt_payload(float(longitude)),
        )
    finally:
        db.disconnect()

    print(f"Provisioned device '{device_id}' (secrets stored hashed). Ready to be claimed.")


if __name__ == "__main__":
    main()
