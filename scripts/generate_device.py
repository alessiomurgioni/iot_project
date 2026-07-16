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
            "\nThis script will generate a device with given DEVICE_ID, DEVICE_TOKEN and position!"
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

    print(f"Device '{device_id}' Generated successfully!")


if __name__ == "__main__":
    main()
