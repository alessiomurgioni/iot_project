from flask import (
    Blueprint, jsonify, redirect, render_template, request, session, url_for
)
import db
from auth import login_required, owner_required, verify_owner_key

owner_bp = Blueprint("owner", __name__, url_prefix="/owner")


@owner_bp.route("/unlock", methods=["GET", "POST"])
@login_required
def unlock():
    error = None
    if request.method == "POST":
        key = request.form.get("owner_key", "")
        if verify_owner_key(key):
            session["owner"] = True
            return redirect(url_for("owner.manage"))
        error = "Incorrect owner key."
    return render_template("owner_unlock.html", error=error)


@owner_bp.route("/lock")
@login_required
def lock():
    session.pop("owner", None)
    return redirect(url_for("views.dashboard"))


@owner_bp.route("/")
@owner_required
def manage():
    return render_template("owner_manage.html", username=session["user"])


# -- API: account management, owner key required ----------------------------------
@owner_bp.route("/api/accounts")
@owner_required
def api_accounts():
    return jsonify(db.list_users())


@owner_bp.route("/api/accounts/delete", methods=["POST"])
@owner_required
def api_accounts_delete():
    data = request.get_json(silent=True) or request.form
    target = (data.get("username") or "").strip()

    if not target:
        return jsonify({"error": "No username provided."}), 400
    if target == session["user"]:
        return jsonify({"error": "You cannot delete the account you're logged in with."}), 400

    removed = db.delete_user(target)
    if removed == 0:
        return jsonify({"error": "No such account."}), 404
    print(f"[OWNER] {session['user']} removed account '{target}'")
    return jsonify({"deleted": target})


@owner_bp.route("/api/accounts/permission", methods=["POST"])
@owner_required
def api_accounts_permission():
    data = request.get_json(silent=True) or request.form
    target = (data.get("username") or "").strip()
    can_control = data.get("can_control")

    if not target:
        return jsonify({"error": "No username provided."}), 400
    if can_control is None:
        return jsonify({"error": "No can_control value provided."}), 400

    # Accept JSON booleans or "true"/"false" strings from a plain form post.
    if isinstance(can_control, str):
        can_control = can_control.strip().lower() in ("1", "true", "yes")

    matched = db.set_can_control(target, bool(can_control))
    if matched == 0:
        return jsonify({"error": "No such account."}), 404
    print(f"[OWNER] {session['user']} set can_control={bool(can_control)} for '{target}'")
    return jsonify({"username": target, "can_control": bool(can_control)})
