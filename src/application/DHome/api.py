import threading

from flask import Blueprint, request, jsonify, current_app, session

from src.application.auth import (
    twin_member_required, verify_device_token, can_control, is_owner,
)
from src.application.DHome import climate
from src.services.DHome.fire_notification import send_fire_alert
from config import settings


# Domotic blueprints
twin_api = Blueprint("twin_api", __name__, url_prefix="/api/twins")
device_api = Blueprint("device_api", __name__, url_prefix="/api")

# Reference generic blueprints
dt_api = Blueprint("dt_api", __name__, url_prefix="/api/dt")
dr_api = Blueprint("dr_api", __name__, url_prefix="/api/dr")

ALLOWED_MODES = {"auto", "cool", "heat", "off"}
ALLOWED_WINDOWS = {"open", "closed"}


def _factory():
    return current_app.config["DT_FACTORY"]


def _db():
    return current_app.config["DB_SERVICE"]


def _get_twin(dt_id):
    dt = _factory().get_dt_instance(dt_id)
    if not dt or not dt.digital_replicas:
        return None, (jsonify({"error": "Twin not provisioned."}), 503)
    return dt, None


def _twin_for_device(device_id):
    device = _db().get_device(device_id)
    return device.get("claimed_by_dt") if device else None


# ── Twin-scoped (member-gated) ───────────────────────────────────────────────
@twin_api.route("/<dt_id>/state")
@twin_member_required
def state(dt_id):
    dt, err = _get_twin(dt_id)
    if err:
        return err
    d = dt.digital_replicas[0]["data"]
    snap = dict(d)
    live = climate.outdoor_temp(dt_id)
    snap["outdoor_temp"] = live if live is not None else d.get("outdoor_temp")
    snap["online"] = _factory().is_online(dt_id)
    snap["control"] = {"mode": d.get("mode"), "threshold": d.get("threshold"),
                       "window": d.get("windows")}
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

    dt, err = _get_twin(dt_id)
    if err:
        return err
    dr = dt.execute_service("ClimateControlService", action="set_control",
                            mode=mode, threshold=threshold, window=(window or None))
    _factory().persist_dr(dt)
    d = dr["data"]
    print(f"[API] {dt_id} control by {session['user']}: "
          f"mode={d['mode']} threshold={d['threshold']} window={d['windows']}")
    return jsonify({"mode": d["mode"], "threshold": d["threshold"], "window": d["windows"]})


@twin_api.route("/<dt_id>/monitoring")
@twin_member_required
def monitoring(dt_id):
    dt, err = _get_twin(dt_id)
    if err:
        return err
    return jsonify(dt.execute_service("MonitoringService", action="summary",
                                      stale_after_s=settings.STALE_AFTER_S))


@twin_api.route("/<dt_id>/members/leave", methods=["POST"])
@twin_member_required
def leave_device(dt_id):
    username = session["user"]

    removed = _db().remove_membership(username,dt_id )

    if not removed:
        return jsonify({"error": "You are not associated with this device."}), 404

    return jsonify({"ok": True})


# ── Device-facing (device_id + token) ────────────────────────────────────────
def _authorize_device(device_id: str):
    """Shared by every device-facing route: a Bearer token in the Authorization
    header, verified against the device_id the caller already extracted (from
    a JSON body for POST-only routes, from query args for the still-GET ones).
    Never trusts device_id/token sitting in a URL or form field on their own —
    the header is what proves possession."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, (jsonify({"error": "Missing or invalid Authorization header"}), 401)
    token = auth_header[len("Bearer "):].strip()

    if not verify_device_token(device_id, token):
        return None, (jsonify({"error": "bad token"}), 403)
    dt_id = _twin_for_device(device_id)
    if not dt_id:
        return None, (jsonify({"error": "device not claimed yet"}), 409)
    return dt_id, None


@device_api.route("/report", methods=["POST"])
def report():
    """POST + JSON only (no GET, no query/form fields) — device_id, token
    (via Authorization: Bearer) and telemetry never appear in a URL or
    server/proxy access log."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body required"}), 400

    device_id = (payload.get("device_id") or "").strip()
    dt_id, err = _authorize_device(device_id)
    if err:
        return err
    dt, terr = _get_twin(dt_id)
    if terr:
        return terr
    was_on_fire = bool(dt.digital_replicas[0]["data"].get("fire"))
    dr = dt.execute_service("ClimateControlService", action="update_from_device",
                            indoor=payload.get("indoor"), people=payload.get("people"),
                            fire=payload.get("fire"), ac=payload.get("ac"),
                            windows=payload.get("windows"))
    _factory().persist_dr(dt)
    d = dr["data"]
    if d.get("fire") and not was_on_fire:
        _alert_fire(dt, dt_id, device_id, dr)
    return jsonify({"mode": d["mode"], "threshold": d["threshold"], "window": d["windows"]})


def _alert_fire(dt, dt_id, device_id, dr):
    """Fire just went false -> true on this report (not re-sent on every
    subsequent report while it stays on). Emails every member with access to
    the twin, through the twin's own FireNotificationService when it has one;
    runs off-thread so a slow/unreachable SMTP server can't hold up the
    device's report request. Uses device_id (the real physical device id,
    e.g. 'cagliari-001') for the email, not dt_id (the twin's own internal
    id) -- dt_id is only used to scope the membership/service lookups below."""
    house_label = (dr.get("profile") or {}).get("house_name") or device_id
    emails = _db().list_member_emails(dt_id)

    def _run():
        try:
            dt.execute_service("FireNotificationService", action="notify_fire",
                               emails=emails, house_label=house_label, device_id=device_id)
        except ValueError:
            # Twin was provisioned before FireNotificationService was added to
            # the DHome catalog, so it's missing from its services list.
            # Attach it now (persisted, so future fires go through the
            # service normally) and send this one directly as a fallback.
            try:
                _factory().add_service(dt_id, "FireNotificationService")
            except Exception as exc:
                print(f"[NOTIFY] Could not attach FireNotificationService to {dt_id}: {exc}")
            send_fire_alert(emails, house_label, device_id)

    threading.Thread(target=_run, daemon=True).start()


@device_api.route("/command")
def command():
    # NOTE: still GET + query args, unlike /report -- same Authorization
    # header requirement, but device_id (not the token) is still visible in
    # the URL/access log here. Say the word if you want this locked down the
    # same way /report just was.
    device_id = request.values.get("device_id", "")
    dt_id, err = _authorize_device(device_id)
    if err:
        return err
    dt, terr = _get_twin(dt_id)
    if terr:
        return terr
    d = dt.digital_replicas[0]["data"]
    return jsonify({"mode": d["mode"], "threshold": d["threshold"], "window": d["windows"]})


@device_api.route("/outdoor-temp")
def outdoor_temp():
    device_id = request.values.get("device_id", "")
    dt_id, err = _authorize_device(device_id)
    if err:
        return err
    t = climate.outdoor_temp(dt_id)
    if t is None:
        return jsonify({"error": "not available yet"}), 503
    return jsonify({"outdoor_temp": t})


# ── Reference generic endpoints ──────────────────────────────────────────────
@dt_api.route("/<dt_id>", methods=["GET"])
def get_digital_twin(dt_id):
    dt = _factory().get_dt(dt_id)
    if not dt:
        return jsonify({"error": "Digital Twin not found"}), 404
    return jsonify(dt), 200


@dt_api.route("/", methods=["GET"])
def list_digital_twins():
    return jsonify(_factory().list_dts()), 200


@dr_api.route("/<dr_type>/<dr_id>", methods=["GET"])
def get_digital_replica(dr_type, dr_id):
    dr = _db().get_dr(dr_type, dr_id)
    if not dr:
        return jsonify({"error": "Digit al Replica not found"}), 404
    return jsonify(dr), 200


# ── Registration entrypoint (reference-style) ────────────────────────────────
def register_api_blueprints(app):
    """Register every blueprint: auth pages, web pages, domotic API, and the
    reference generic DT/DR API."""
    from src.application.auth import auth_bp
    from src.application.web import web_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(web_bp)
    app.register_blueprint(twin_api)
    app.register_blueprint(device_api)
    app.register_blueprint(dt_api)
    app.register_blueprint(dr_api)
