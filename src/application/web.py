from flask import (
    Blueprint, current_app, jsonify, redirect, render_template, request,
    session, url_for,
)
from flask_limiter.util import get_remote_address

from src.application.auth import (
    login_required, twin_member_required, twin_owner_required,
    verify_device_token, verify_owner_key, is_owner, limiter, claim_lockout,
    MAX_SECRET_LEN,
)
from config import catalog

web_bp = Blueprint("web", __name__)


def _db():
    return current_app.config["DB_SERVICE"]


def _factory():
    return current_app.config["DT_FACTORY"]


def _device_label(m, reg, dt_id):
    """This user's own pseudonym for a device (what they typed in "Name" when
    adding it), never a name shared globally with every other member of the
    same twin. Falls back to the real device id, then the twin id, if they
    never set one."""
    label = (m.get("label") or "").strip() if m else ""
    if label:
        return label
    if reg and reg.get("digital_replicas"):
        device_id = reg["digital_replicas"][0].get("id")
        if device_id:
            return device_id
    return dt_id


# ── Home + claim ─────────────────────────────────────────────────────────────
def _render_home(error=None, status=200):
    items = []
    for m in _db().list_memberships_for_user(session["user"]):
        reg = _factory().get_dt(m["dt_id"])
        product_key = reg.get("product") if reg else None
        items.append({
            "dt_id": m["dt_id"],
            "name": _device_label(m, reg, m["dt_id"]),
            "product_label": catalog.label_for(product_key),
            "role": m.get("role", "member"),
            "can_control": m.get("can_control", True),
        })
    return render_template("home.html", username=session["user"], devices=items,
                           products=catalog.list_products(),
                           error=error), status


@web_bp.route("/")
@login_required
def home():
    error = session.pop("add_device_error", None)
    return _render_home(error)


@web_bp.route("/devices/add", methods=["POST"])
@login_required
@limiter.limit("10 per minute; 40 per hour")
def add_device():
    """Claim a device. device_id + device_token prove possession; the optional
    owner_key, if correct, grants the owner role (management tab). First claim
    provisions the twin; later claims join it."""
    ip = get_remote_address()
    wait = claim_lockout.locked_for(ip)
    if wait:
        return _redirect_home_error(
            f"Too many invalid attempts. Try again in {wait}s."
        )
    device_id = (request.form.get("device_id") or "").strip()
    token = (request.form.get("device_token") or "").strip()
    owner_key = (request.form.get("owner_key") or "").strip()
    name = (request.form.get("name") or "").strip() or None
    product = (request.form.get("product") or catalog.DEFAULT_PRODUCT).strip()

    if not device_id or not token:
        return _redirect_home_error(
            "Device id and device token are required."
        )

    if len(token) > MAX_SECRET_LEN or len(owner_key) > MAX_SECRET_LEN:
        return _redirect_home_error(
            "Supplied credentials are too long."
        )

    if not catalog.get_product(product):
        return _redirect_home_error(
            "Please choose a valid device type."
        )

    if not verify_device_token(device_id, token):
        locked = claim_lockout.record_failure(ip)
        msg = (
            f"Too many invalid attempts. Locked for {locked}s."
            if locked
            else "Unknown device or wrong device token."
        )
        return _redirect_home_error(msg)
    claim_lockout.reset(ip)

    device = _db().get_device(device_id)
    dt_id = device.get("claimed_by_dt")
    if not dt_id:
        # First claim provisions the twin for the chosen product type. Later
        # claimers join whatever type the device already is.
        dt_id = _factory().create_twin_for_device(device_id, product=product, house_name=name)
        _db().set_device_twin(device_id, dt_id)

    role = "owner" if (owner_key and verify_owner_key(device_id, owner_key)) else "member"
    _db().add_membership(session["user"], dt_id, role=role, can_control=True, label=name)
    return redirect(url_for("web.home"))


# ── Per-twin dashboard ───────────────────────────────────────────────────────
@web_bp.route("/twins/<dt_id>")
@twin_member_required
def dashboard(dt_id):
    reg = _factory().get_dt(dt_id)
    m = _db().get_membership(session["user"], dt_id)
    name = _device_label(m, reg, dt_id)
    spec = catalog.get_product(reg.get("product")) if reg else None
    template = spec["dashboard_template"] if spec else "DHome/dashboard.html"
    return render_template(template, username=session["user"], dt_id=dt_id,
                           device_name=name, product_label=catalog.label_for(reg.get("product") if reg else None),
                           is_owner=is_owner(session["user"], dt_id))


# ── Per-twin management (owner only) ─────────────────────────────────────────
@web_bp.route("/twins/<dt_id>/manage")
@twin_owner_required
def manage(dt_id):
    reg = _factory().get_dt(dt_id)
    m = _db().get_membership(session["user"], dt_id)
    name = _device_label(m, reg, dt_id)
    return render_template("DHome/owner_manage_DHome.html", username=session["user"],
                           dt_id=dt_id, device_name=name)


@web_bp.route("/twins/<dt_id>/api/members")
@twin_owner_required
def api_members(dt_id):
    return jsonify(_db().list_memberships_for_twin(dt_id))


@web_bp.route("/twins/<dt_id>/api/members/permission", methods=["POST"])
@twin_owner_required
def api_members_permission(dt_id):
    data = request.get_json(silent=True) or request.form
    target = (data.get("username") or "").strip()
    cc = data.get("can_control")
    if not target:
        return jsonify({"error": "No username provided."}), 400
    if cc is None:
        return jsonify({"error": "No can_control value provided."}), 400
    if isinstance(cc, str):
        cc = cc.strip().lower() in ("1", "true", "yes")
    if _db().set_can_control(target, dt_id, bool(cc)) == 0:
        return jsonify({"error": "That account is not a member of this device."}), 404
    print(f"[MANAGE] {session['user']} set can_control={bool(cc)} for '{target}' on {dt_id}")
    return jsonify({"username": target, "can_control": bool(cc)})


@web_bp.route("/twins/<dt_id>/api/members/remove", methods=["POST"])
@twin_owner_required
def api_members_remove(dt_id):
    data = request.get_json(silent=True) or request.form
    target = (data.get("username") or "").strip()
    if not target:
        return jsonify({"error": "No username provided."}), 400
    if target == session["user"]:
        return jsonify({"error": "You can't remove yourself from this device."}), 400
    if is_owner(target, dt_id) and _db().count_owners(dt_id) <= 1:
        return jsonify({"error": "Can't remove the last owner of this device."}), 400
    if _db().remove_membership(target, dt_id) == 0:
        return jsonify({"error": "That account is not a member of this device."}), 404
    print(f"[MANAGE] {session['user']} removed '{target}' from {dt_id}")
    return jsonify({"removed": target})


def _redirect_home_error(message):
    session["add_device_error"] = message
    return redirect(url_for("web.home"))
