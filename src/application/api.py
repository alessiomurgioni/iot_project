from flask import Blueprint, request, jsonify, current_app, session
from src.application.auth import twin_member_required, verify_device_token

twin_api = Blueprint("twin_api", __name__, url_prefix="/api/twins")


# ----------------------------------------
#       Utility Functions
# ----------------------------------------
def factory():
    """
    Get the app's DT factory.

    Output:
    - the DT factory instance
    """
    return current_app.config["DT_FACTORY"]


def db():
    """
    Get the app's DatabaseService.

    Output:
    - the DatabaseService instance
    """
    return current_app.config["DB_SERVICE"]


def get_twin(dt_id):
    """
    Get the given twin instance.

    Input:
    - dt_id: the twin's id

    Output:
    - Twin instance on success, None otherwise
    """
    dt = factory().get_dt_instance(dt_id)
    if not dt or not dt.digital_replicas:
        return None, (jsonify({"error": "Twin not provisioned."}), 503)
    return dt, None


def twin_for_device(device_id):
    """
    Look up which twin a device has been claimed into.

    Input:
    - device_id: the device's id

    Output:
    - the twin id, or None
    """
    device = db().get_device(device_id)
    return device.get("claimed_by_dt") if device else None


def authorize_device(device_id: str):
    """
    Verify a device's token and resolve it to its twin.

    Input:
    - device_id: the device's id

    Output:
    - dt_id on success, None otherwise
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, (jsonify({"error": "Missing or invalid Authorization header"}), 401)
    token = auth_header[len("Bearer "):].strip()

    if not verify_device_token(device_id, token):
        return None, (jsonify({"error": "bad token"}), 403)
    dt_id = twin_for_device(device_id)
    if not dt_id:
        return None, (jsonify({"error": "device not claimed yet"}), 409)
    return dt_id, None


# ----------------------------------------
#       Flask routes
# ----------------------------------------
@twin_api.route("/<dt_id>/members/leave", methods=["POST"])
@twin_member_required
def leave_device(dt_id):
    """
    Remove the current user's membership from a twin.

    Input:
    - dt_id: the twin's id
    """
    username = session["user"]

    removed = db().remove_membership(username, dt_id)

    if not removed:
        return jsonify({"error": "You are not associated with this device."}), 404

    return jsonify({"ok": True})


def register_api_blueprints(app):
    """
    Register all Flask blueprints on the app.

    Input:
    - app: the Flask application instance
    """
    from src.application.auth import auth_bp
    from src.application.web import web_bp
    from src.application.DHome.api import device_api

    app.register_blueprint(auth_bp)
    app.register_blueprint(web_bp)
    app.register_blueprint(twin_api)
    app.register_blueprint(device_api)
