import socket
from flask import Flask
from flask_cors import CORS

from src.virtualization.digital_replica.schema_registry import SchemaRegistry
from src.virtualization.digital_replica.dr_factory import DRFactory
from src.services.database_service import DatabaseService
from src.digital_twin.DHome.dt_factory import DHomeDTFactory
from src.application.api import register_api_blueprints
from src.application.auth import limiter
from src.application.DHome import climate
from config.config_loader import ConfigLoader
from config import settings


class FlaskServer:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.secret_key = settings.SECRET_KEY
        self.app.config.update(
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Lax",
            # SESSION_COOKIE_SECURE=True,   # enable once served over HTTPS
        )
        CORS(self.app)
        self.init_components()
        self.register_blueprints()

    def init_components(self):
        """
        Set up the schema registry, DB connection, and DT/DR factories.
        """
        schema_registry = SchemaRegistry()
        schema_registry.load_schema(settings.SCHEMA_TYPE, settings.SCHEMA_PATH)

        db_config = ConfigLoader.load_database_config()
        connection_string = ConfigLoader.build_connection_string(db_config)

        db_service = DatabaseService(
            connection_string=connection_string,
            db_name=db_config["settings"]["name"],
            schema_registry=schema_registry,
        )
        db_service.connect()

        dr_factory = DRFactory(settings.SCHEMA_PATH)
        dt_factory = DHomeDTFactory(db_service, schema_registry, dr_factory)

        self.app.config["SCHEMA_REGISTRY"] = schema_registry
        self.app.config["DB_SERVICE"] = db_service
        self.app.config["DR_FACTORY"] = dr_factory
        self.app.config["DT_FACTORY"] = dt_factory

    def register_blueprints(self):
        """
        Initialize the rate limiter and register all Flask blueprints.
        """
        limiter.init_app(self.app)
        register_api_blueprints(self.app)

    def run(self, host="0.0.0.0", port=None, debug=False):
        """
        Start the outdoor-temp poller and run the Flask server.

        Inputs:
        - host: bind address
        - port: bind port (defaults to settings.PORT)
        - debug: Flask debug mode flag
        """
        port = port or settings.PORT
        climate.start_poller(self.app.config["DT_FACTORY"])
        self.banner(port)
        try:
            self.app.run(host=host, port=port, debug=debug, threaded=True)
        finally:
            if "DB_SERVICE" in self.app.config:
                self.app.config["DB_SERVICE"].disconnect()

    def banner(self, port):
        """
        Print the local network URL the app is reachable at.

        Inputs:
        - port: port to include in the printed URL
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            ip = "127.0.0.1"
        print("\n=== Domotic Digital-Twin platform ===")
        print(f"Home         : http://{ip}:{port}")


if __name__ == "__main__":
    server = FlaskServer()
    server.run()
