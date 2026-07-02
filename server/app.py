import socket
from flask import Flask, render_template, session
import climate
import config
from src_dt.application.api import api_bp
from security import auth_bp, limiter, login_required
from owner import owner_bp
from src_dt.digital_twin.dt_factory import DTFactory


def get_ip():
    """
    Returns the IP address. Falls back to localhost
    if the ip retrieval fails.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def create_app():
    """
    Builds and configures the Flask application.
    """
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # SESSION_COOKIE_SECURE=True,
    )
    limiter.init_app(app)  # wire up rate limiting

    # Digital Twin factory, built once at startup and shared across requests.
    # ensure_house_dt() registers (or loads) the "home" twin's identity
    # record via DatabaseService's own MongoDB connection (digital_twins
    # collection), referencing its Digital Replica and ClimateControlService
    # — see src/digital_twin/dt_factory.py and src/services/database_service.py.
    dt_factory = DTFactory()
    app.config["DT_FACTORY"] = dt_factory
    app.config["DT_ID"] = dt_factory.ensure_house_dt()

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(owner_bp)

    @app.route("/")
    @login_required
    def dashboard():
        return render_template("dashboard.html", username=session["user"])

    return app


app = create_app()


# ── Main Execution ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    climate.start_poller()

    local_ip = get_ip()
    print("\n=== Domotic climate webapp ===")
    print(f"Dashboard : http://{local_ip}:{config.PORT}")
    print(f"Sign up   : http://{local_ip}:{config.PORT}/signup ")
    print(f"MongoDB   : {config.MONGO_URI}{config.MONGO_DB}")
    print("==============================\n")

    app.run(host="0.0.0.0", port=config.PORT, threaded=True)
