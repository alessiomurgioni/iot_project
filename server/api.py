"""
JSON API.

  Owner (browser):
    GET  /api/state          live readings + control          (login required)
    POST /api/control        change AC mode / threshold /      (login required,
                             window                              account must
                                                                  have can_control)

  Device (NodeMCU, token-authenticated):
    GET  /api/outdoor-temp   read the current outdoor temperature
    POST /api/report         push sensor readings (indoor, people, fire, ac,
                             windows); reply carries the desired command
    GET  /api/command        pull desired AC mode + threshold + window

Account management (view/remove accounts, grant/revoke can_control) lives in
owner.py, gated by the separate owner key rather than by anything here.
"""
import climate
import db
from auth import login_required, verify_device_token
from flask import Blueprint, jsonify, request, session

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _device_authorized() -> bool:
    token = request.args.get("token") or request.headers.get("X-Device-Token")
    return verify_device_token(token)


# ── Owner endpoints ──────────────────────────────────────────────────────────
@api_bp.route("/state")
@login_required
def state():
    snap, ctrl = climate.snapshot()
    snap["online"] = climate.is_online()
    snap["control"] = ctrl   # control now includes "window"

    user = db.get_user(session["user"])
    snap["can_control"] = bool(user.get("can_control", True)) if user else False
    return jsonify(snap)


@api_bp.route("/control", methods=["POST"])
@login_required
def control():
    # The same can_control permission gates BOTH the AC and the windows.
    user = db.get_user(session["user"])
    if not user or not user.get("can_control", True):
        return jsonify({"error": "Your account cannot change AC/window settings."}), 403

    data = request.get_json(silent=True) or request.form
    ctrl = climate.set_control(
        mode=data.get("mode"),
        threshold=data.get("threshold"),
        window=data.get("window"),
    )
    print(f"[API] Control updated by {session['user']}: {ctrl}")
    return jsonify(ctrl)


# ── Device endpoints (NodeMCU) ───────────────────────────────────────────────
@api_bp.route("/outdoor-temp")
def outdoor_temp():
    """NodeMCU reads the outdoor temperature the server fetched from open-meteo."""
    if not _device_authorized():
        return jsonify({"error": "bad token"}), 403
    t = climate.outdoor_temp()
    if t is None:
        return jsonify({"error": "not available yet"}), 503
    return jsonify({"outdoor_temp": t})


@api_bp.route("/report", methods=["GET", "POST"])
def report():
    """
    Query-string friendly so the ESP8266 can build it without composing JSON:
        POST /api/report?token=...&indoor=23.4&people=2&fire=0&ac=cool&windows=closed
    Replies with the current command so the device can report + refresh at once.
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
    if not _device_authorized():
        return jsonify({"error": "bad token"}), 403
    ctrl = climate.get_command()
    return jsonify({
        "mode": ctrl["mode"],
        "threshold": ctrl["threshold"],
        "window": ctrl["window"],
    })