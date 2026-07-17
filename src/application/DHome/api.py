import threading

from flask import Blueprint, request, jsonify, session

from src.application.api import factory, db, twin_api, get_twin, authorize_device
from src.application.auth import twin_member_required, can_control, is_owner
from src.application.DHome import climate
from src.services.DHome.fire_notification import send_fire_alert

# Product-specific blueprint (endpoints only DHome exposes).
device_api = Blueprint("device_api", __name__, url_prefix="/api")

ALLOWED_MODES = {"auto", "cool", "heat", "off"}
ALLOWED_WINDOWS = {"open", "closed"}


# ----------------------------------------
#       Utility Functions
# ----------------------------------------
def alert_fire(dt, dt_id, device_id, dr):
    """
    Notify all members of a twin about a newly detected fire,
    through the fire notification service, in a background thread.

    Inputs:
    - dt: the twin instance
    - dt_id: the twin's id
    - device_id: the device's id
    - dr: the twin's current Digital Replica document
    """
    house_label = (dr.get("profile") or {}).get("house_name") or device_id
    emails = db().list_member_emails(dt_id)

    def run():
        try:
            dt.execute_service("FireNotificationService", action="notify_fire",
                               emails=emails, house_label=house_label, device_id=device_id)
        except ValueError:
            try:
                factory().add_service(dt_id, "FireNotificationService")
            except Exception as exc:
                print(f"[NOTIFY] Could not attach FireNotificationService to {dt_id}: {exc}")
            send_fire_alert(emails, house_label, device_id)

    threading.Thread(target=run, daemon=True).start()


# ----------------------------------------
#       Flask routes
# ----------------------------------------
@twin_api.route("/<dt_id>/state")
@twin_member_required
def state(dt_id):
    dt, err = get_twin(dt_id)
    if err:
        return err
    d = dt.digital_replicas[0]["data"]
    snap = dict(d)
    live = climate.outdoor_temp(dt_id)
    snap["outdoor_temp"] = live if live is not None else d.get("outdoor_temp")
    snap["online"] = factory().is_online(dt_id)
    snap["control"] = {"mode": d.get("mode"), "threshold": d.get("threshold"),
                       "windows": d.get("windows")}
    snap["can_control"] = can_control(session["user"], dt_id)
    snap["is_owner"] = is_owner(session["user"], dt_id)
    return jsonify(snap)


@twin_api.route("/<dt_id>/control", methods=["POST"])
@twin_member_required
def control(dt_id):
    if not can_control(session["user"], dt_id):
        return jsonify({"error": "Your account cannot change AC/window settings."}), 403

    data = request.get_json(silent=True) or request.form
    mode = data.get("mode")
    windows = data.get("windows")
    threshold = data.get("threshold")

    if mode is not None and mode not in ALLOWED_MODES:
        return jsonify({"error": "Invalid mode."}), 400
    if windows is not None and windows not in ALLOWED_WINDOWS:
        return jsonify({"error": "Invalid windows command."}), 400
    if threshold is not None:
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            return jsonify({"error": "Threshold must be a number."}), 400
    if mode is None and windows is None and threshold is None:
        return jsonify({"error": "Nothing to update."}), 400

    dt, err = get_twin(dt_id)
    if err:
        return err
    dr = dt.execute_service("ClimateControlService", action="set_control",
                            mode=mode, threshold=threshold, windows=(windows or None))
    factory().save_dr(dt)
    d = dr["data"]
    print(f"[API] {dt_id} control by {session['user']}: "
          f"mode={d['mode']} threshold={d['threshold']} windows={d['windows']}")
    return jsonify({"mode": d["mode"], "threshold": d["threshold"], "windows": d["windows"]})


@device_api.route("/report", methods=["POST"])
def report():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body required"}), 400

    device_id = (payload.get("device_id") or "").strip()
    dt_id, err = authorize_device(device_id)
    if err:
        return err
    dt, terr = get_twin(dt_id)
    if terr:
        return terr
    was_on_fire = bool(dt.digital_replicas[0]["data"].get("fire"))
    dr = dt.execute_service("ClimateControlService", action="update_from_device",
                            indoor=payload.get("indoor"), people=payload.get("people"),
                            fire=payload.get("fire"), ac=payload.get("ac"),
                            windows_state=payload.get("windows_state"))
    factory().save_dr(dt)
    d = dr["data"]
    if d.get("fire") and not was_on_fire:
        alert_fire(dt, dt_id, device_id, dr)
    return jsonify({"mode": d["mode"], "threshold": d["threshold"], "windows": d["windows"]})


@device_api.route("/outdoor-temp")
def outdoor_temp():
    """
    Get the last polled outdoor temperature for a device's twin.

    Inputs:
    - query/form field: device_id

    Outputs:
    - JSON {outdoor_temp} on success, or an error with status code
    """
    device_id = request.values.get("device_id", "")
    dt_id, err = authorize_device(device_id)
    if err:
        return err
    t = climate.outdoor_temp(dt_id)
    if t is None:
        return jsonify({"error": "not available yet"}), 503
    return jsonify({"outdoor_temp": t})
