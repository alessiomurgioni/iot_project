import socket
from flask import Flask, render_template, session
import climate
import config
from api import api_bp
from security import auth_bp, limiter, login_required
from owner import owner_bp

# ── Webapp Construction ──────────────────────────────────────────────────────────
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
    Builds and configures the Flask application. It sets the session secret
    key, hardens the session cookies, wires up the rate limiter, and registers
    the auth, API, and owner blueprints; then returns the configured app instance.
    SameSite=Lax stops the session cookie from being sent on cross-site POSTs.
    It attaches the cookies only when the request is coming from the same site,
    so a malicious page can't submit authenticated requests by stealing those cookies.
    """
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        #SESSION_COOKIE_SECURE=True,
    )
    limiter.init_app(app)          # wire up rate limiting
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