import climate
import db
from security import login_required, verify_device_token
from flask import Blueprint, jsonify, request, session

api_bp = Blueprint("api", __name__, url_prefix="/api")

# ── Whitelist Values ──────────────────────────────────────────────────────────
ALLOWED_MODES = {"auto", "cool", "heat", "off"}
ALLOWED_WINDOWS = {"open", "close"}
THRESHOLD_MIN, THRESHOLD_MAX = 10.0, 35.0


# ── Requests Checker ──────────────────────────────────────────────────────────
def _device_authorized() -> bool:
    """
    Checks whether the current request carries a valid device token, read
    from either the token query parameter or the X-Device-Token header.
    """
    token = request.args.get("token") or request.headers.get("X-Device-Token")
    return verify_device_token(token)


# ── Webapp Management ──────────────────────────────────────────────────────────
@api_bp.route("/state")
@login_required
def state():
    """
    Returns the current house state: temperature, people count, AC mode, fire
    alarm, device status and windows status; for the dashboard. It is called
    every few seconds to refresh the UI. Also reports whether the logged-in
    account is allowed to change AC/window settings, so the
    dashboard can grey out the controls for read-only accounts.
    """
    snap, ctrl = climate.snapshot()
    snap["online"] = climate.is_online()
    snap["control"] = ctrl  # control now includes "window"

    user = db.get_user(session["user"])
    snap["can_control"] = bool(user.get("can_control", True)) if user else False
    return jsonify(snap)


@api_bp.route("/control", methods=["POST"])
@login_required
def control():
    """
    Lets a logged-in owner change AC mode, threshold, or window command from
    the dashboard. Requires can_control permission on the account. Every
    field is validated against its whitelist before anything is applied.
    On success, applies the change and returns the resulting control state.
    """
    # The same can_control permission gates BOTH the AC and the windows.
    user = db.get_user(session["user"])
    if not user or not user.get("can_control", True):
        return jsonify({"error": "Your account cannot change AC/window settings."}), 403

    data = request.get_json(silent=True) or request.form
    mode = data.get("mode")
    window = data.get("window")
    threshold = data.get("threshold")

    # Validate every field against its whitelist before modifying state.
    if mode is not None and mode not in ALLOWED_MODES:
        return jsonify({"error": "Invalid mode."}), 400
    if window is not None and window not in ALLOWED_WINDOWS:
        return jsonify({"error": "Invalid window command."}), 400
    if threshold is not None:
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            return jsonify({"error": "Threshold must be a number."}), 400
        if not (THRESHOLD_MIN <= threshold <= THRESHOLD_MAX):
            return jsonify({"error": f"Threshold out of range ({THRESHOLD_MIN:g}-{THRESHOLD_MAX:g})."}), 400
    if mode is None and window is None and threshold is None:
        return jsonify({"error": "Nothing to update."}), 400

    ctrl = climate.set_control(mode=mode, threshold=threshold, window=window)
    print(f"[API] Control updated by {session['user']}: {ctrl}")
    return jsonify(ctrl)


# ── NodeMCU Management ───────────────────────────────────────────────
@api_bp.route("/outdoor-temp")
def outdoor_temp():
    """
    Returns the reported outdoor temperature for the NodeMCU to read by calling
    Open-Meteo in the background. this function just hands back the value.
    """
    if not _device_authorized():
        return jsonify({"error": "bad token"}), 403
    t = climate.outdoor_temp()
    if t is None:
        return jsonify({"error": "not available yet"}), 503
    return jsonify({"outdoor_temp": t})


@api_bp.route("/report", methods=["GET", "POST"])
def report():
    """
    Receives the NodeMCU's information: indoor temp, people count, fire sensor, AC blowing state,
    window state.
    """
    if not _device_authorized():
        return jsonify({"error": "bad token"}), 403

    src = request.values
    ctrl = climate.update_from_device(
        indoor=src.get("indoor"),
        people=src.get("people"),
        fire=src.get("fire"),
        ac=src.get("ac"),
        windows=src.get("windows"),
    )
    return jsonify({
        "mode": ctrl["mode"],
        "threshold": ctrl["threshold"],
        "window": ctrl["window"],
    })


@api_bp.route("/command")
def command():
    """
    Returns the current desired command: mode, threshold, window; to the NodeMCU.
    """
    if not _device_authorized():
        return jsonify({"error": "bad token"}), 403
    ctrl = climate.get_command()
    return jsonify({
        "mode": ctrl["mode"],
        "threshold": ctrl["threshold"],
        "window": ctrl["window"],
    })
