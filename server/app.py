"""
Entry point for the domotic climate webapp.

Run:
    pip install -r requirements.txt
    # make sure MongoDB is running (mongod) or set MONGO_URI to an Atlas cluster
    python app.py

Then open http://<server-ip>:8000 on a device on the same network.
The first account you create at /signup becomes the admin.
"""
import socket

from flask import Flask

import climate
import config
from api import api_bp
from auth import auth_bp
from owner import owner_bp
from views import views_bp


def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(owner_bp)
    return app


app = create_app()


if __name__ == "__main__":
    climate.start_poller()

    local_ip = get_ip()
    print("\n=== Domotic climate webapp ===")
    print(f"Dashboard : http://{local_ip}:{config.PORT}")
    print(f"Sign up   : http://{local_ip}:{config.PORT}/signup  (enter device token = admin)")
    print(f"Device API: POST /api/report   GET /api/command   (token required)")
    print(f"MongoDB   : {config.MONGO_URI}{config.MONGO_DB}")
    print("==============================\n")

    app.run(host="0.0.0.0", port=config.PORT, threaded=True)
