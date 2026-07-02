from flask import Blueprint, jsonify, request, session, current_app

# FIX: `climate` was used (climate.is_online(), climate.outdoor_temp()) but
# never imported -> NameError on every request. Also removed the unused
# `import server_perlamerda.config as config`.
import climate
from security import login_required, verify_device_token
import db

api_bp = Blueprint("api", __name__, url_prefix="/api")

ALLOWED_MODES = {"auto", "cool", "heat", "off"}
ALLOWED_WINDOWS = {"open", "closed"}



def _device_authorized() -> bool:
    token = request.args.get("token") or request.headers.get("X-Device-Token")
    return verify_device_token(token)


@api_bp.route("/state")
@login_required
def state():
    factory = current_app.config["DT_FACTORY"]
    dt = factory.get_dt_instance(current_app.config["DT_ID"])
    d = dt.digital_replicas[0]["data"]

    snap = dict(d)
    # Outdoor temperature is fetched by climate.py's background poller
    # (Open-Meteo), independent of the DR — prefer the live value, fall
    # back to whatever was last persisted on the DR.
    live_outdoor = climate.outdoor_temp()
    snap["outdoor_temp"] = live_outdoor if live_outdoor is not None else d.get("outdoor_temp")

    # FIX: was climate.is_online() — climate.py no longer owns _state.
    snap["online"] = factory.is_online()
    snap["control"] = {"mode": d["mode"], "threshold": d["threshold"], "window": d["windows"]}

    user = db.get_user(session["user"])
    snap["can_control"] = bool(user.get("can_control", True)) if user else False
    return jsonify(snap)


@api_bp.route("/control", methods=["POST"])
@login_required
def control():
    user = db.get_user(session["user"])
    if not user or not user.get("can_control", True):
        return jsonify({"error": "Your account cannot change AC/window settings."}), 403

    data = request.get_json(silent=True) or request.form
    mode = data.get("mode")
    window = data.get("window")
    threshold = data.get("threshold")

    if mode is not None and mode not in ALLOWED_MODES:
        return jsonify({"error": "Invalid mode."}), 400
    if window is not None and window not in ALLOWED_WINDOWS:
        return jsonify({"error": "Invalid window command."}), 400
    if threshold is not None:
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            return jsonify({"error": "Threshold must be a number."}), 400
    if mode is None and window is None and threshold is None:
        return jsonify({"error": "Nothing to update."}), 400

    schema_window = window if window else None

    factory = current_app.config["DT_FACTORY"]
    dt = factory.get_dt_instance(current_app.config["DT_ID"])
    dr = dt.execute_service(
        "ClimateControlService", action="set_control",
        mode=mode, threshold=threshold, window=schema_window,
    )

    # Schema violations (e.g. threshold out of range) return a clean 400
    # instead of an unhandled 500.
    try:
        factory.persist_dr(dt)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    d = dr["data"]
    print(f"[API] Control updated by {session['user']}: "
          f"mode={d['mode']} threshold={d['threshold']} window={d['windows']}")
    return jsonify({"mode": d["mode"], "threshold": d["threshold"], "window": d["windows"]})


@api_bp.route("/report", methods=["GET", "POST"])
def report():
    if not _device_authorized():
        return jsonify({"error": "bad token"}), 403

    src = request.values
    factory = current_app.config["DT_FACTORY"]
    dt = factory.get_dt_instance(current_app.config["DT_ID"])
    dr = dt.execute_service(
        "ClimateControlService", action="update_from_device",
        indoor=src.get("indoor"), people=src.get("people"),
        fire=src.get("fire"), ac=src.get("ac"), windows=src.get("windows"),
    )

    try:
        factory.persist_dr(dt)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    d = dr["data"]
    return jsonify({"mode": d["mode"], "threshold": d["threshold"], "window": d["windows"]})


@api_bp.route("/command")
def command():
    if not _device_authorized():
        return jsonify({"error": "bad token"}), 403
    factory = current_app.config["DT_FACTORY"]
    dt = factory.get_dt_instance(current_app.config["DT_ID"])
    d = dt.digital_replicas[0]["data"]
    return jsonify({"mode": d["mode"], "threshold": d["threshold"], "window": d["windows"]})


@api_bp.route("/monitoring")
@login_required
def monitoring():
    """
    Analytics/monitoring snapshot: indoor-vs-outdoor delta, distance from
    the auto threshold, device liveness, fire status, occupancy.
    Read-only — does not mutate the Digital Replica.
    """
    factory = current_app.config["DT_FACTORY"]
    dt = factory.get_dt_instance(current_app.config["DT_ID"])
    result = dt.execute_service("MonitoringService", action="summary")
    return jsonify(result)


@api_bp.route("/outdoor-temp")
def outdoor_temp():
    if not _device_authorized():
        return jsonify({"error": "bad token"}), 403
    t = climate.outdoor_temp()
    if t is None:
        return jsonify({"error": "not available yet"}), 503
    return jsonify({"outdoor_temp": t})
