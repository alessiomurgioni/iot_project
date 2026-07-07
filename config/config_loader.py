import yaml
from typing import Dict
import os

_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "database.yaml"
)


class ConfigLoader:
    @staticmethod
    def load_database_config(config_path: str = _DEFAULT_CONFIG_PATH) -> Dict:
        """Load database configuration from YAML file"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        if not config or "database" not in config:
            raise ValueError("Invalid configuration file: missing database section")
        return config["database"]

    @staticmethod
    def build_connection_string(config: Dict) -> str:
        """Build MongoDB connection string from configuration"""
        conn = config["connection"]
        host = conn["host"]
        port = conn["port"]
        auth = ""
        if conn.get("username") and conn.get("password"):
            auth = f"{conn['username']}:{conn['password']}@"
        return f"mongodb://{auth}{host}:{port}"
