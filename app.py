import socket
from flask import Flask
from flask_cors import CORS

from src.virtualization.digital_replica.schema_registry import SchemaRegistry
from src.virtualization.digital_replica.dr_factory import DRFactory
from src.services.database_service import DatabaseService
from src.digital_twin.DHome.DHome_dt_factory import DHomeDTFactory
from src.application.DHome.api import register_api_blueprints
from src.application.auth import limiter
from src.application.DHome import climate
from config.config_loader import ConfigLoader
from config import settings

"""
Application entrypoint, following the reference framework's FlaskServer shape:
build the SchemaRegistry, DatabaseService (from config/database.yaml via
ConfigLoader), DRFactory, and DTFactory; store them on app.config; register all
blueprints; then run.

Domotic additions: the session secret + rate limiter for the auth layer, and
the per-house outdoor-temperature poller started when the server actually runs.
There is no single-house bootstrap — twins are created on demand when users
claim devices.
"""



class FlaskServer:
    def __init__(self):
        # Flask finds ./templates and ./static next to this file.
        self.app = Flask(__name__)
        self.app.secret_key = settings.SECRET_KEY
        self.app.config.update(
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Lax",
            # SESSION_COOKIE_SECURE=True,   # enable once served over HTTPS
        )
        CORS(self.app)
        self._init_components()
        self._register_blueprints()

    def _init_components(self):
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

    def _register_blueprints(self):
        limiter.init_app(self.app)
        register_api_blueprints(self.app)

    def run(self, host="0.0.0.0", port=None, debug=False):
        port = port or settings.PORT
        climate.start_poller(self.app.config["DT_FACTORY"])
        self._banner(port)
        try:
            self.app.run(host=host, port=port, debug=debug, threaded=True)
        finally:
            if "DB_SERVICE" in self.app.config:
                self.app.config["DB_SERVICE"].disconnect()

    def _banner(self, port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            ip = "127.0.0.1"
        print("\n=== Domotic Digital-Twin platform ===")
        print(f"Home / Login : http://{ip}:{port}")
        print(f"Sign up      : http://{ip}:{port}/signup")


if __name__ == "__main__":
    server = FlaskServer()
    server.run()
