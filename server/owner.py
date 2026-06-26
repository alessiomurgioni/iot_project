from flask import (
    Blueprint, jsonify, redirect, render_template, request, session, url_for
)
import db
from security import (
    login_required, owner_required, verify_owner_key, limiter, unlock_lockout,
    MAX_SECRET_LEN
)
from flask_limiter.util import get_remote_address

owner_bp = Blueprint("owner", __name__, url_prefix="/owner")


@owner_bp.route("/unlock", methods=["GET", "POST"])
@login_required
@limiter.limit("3 per minute; 10 per hour", methods=["POST"])
def unlock():
    """
    Lets a logged-in user elevate their session to owner mode by submitting
    the owner key. On success, sets session["owner"] and redirects
    to the management page. On failure, records it against the lockout
    logic and shows an error or the remaining lockout time.
    """
    error = None
    if request.method == "POST":
        key = get_remote_address()
        wait = unlock_lockout.locked_for(key)
        if wait:
            error = f"Too many failed attempts. Try again in {wait}s."
            return render_template("owner_unlock.html", error=error)

        owner_key = request.form.get("owner_key", "")
        if len(owner_key) <= MAX_SECRET_LEN and verify_owner_key(owner_key):
            unlock_lockout.reset(key)
            session["owner"] = True
            return redirect(url_for("owner.manage"))

        locked = unlock_lockout.record_failure(key)
        if locked:
            error = f"Too many failed attempts. Locked for {locked}s."
        else:
            error = "Incorrect owner key."
    return render_template("owner_unlock.html", error=error)


@owner_bp.route("/lock")
@login_required
def lock():
    """
    De-elevates the current session out of owner mode, then sends the user
    back to the dashboard. The account stays logged in; only the owner
    privilege is dropped.
    """
    session.pop("owner", None)
    return redirect(url_for("dashboard"))


@owner_bp.route("/")
@owner_required
def manage():
    """
    Renders the owner account-management page. Requires both being logged
    in and an owner-elevated session, so a regular account can never reach
    this view even by guessing the URL.
    """
    return render_template("owner_manage.html", username=session["user"])


@owner_bp.route("/api/accounts")
@owner_required
def api_accounts():
    """
    Returns every registered account, for the owner management page's accounts
    table.
    """
    return jsonify(db.list_users())


@owner_bp.route("/api/accounts/delete", methods=["POST"])
@owner_required
def api_accounts_delete():
    """
    Permanently deletes the given account. Refuses to delete the account
    currently logged in, to avoid the owner locking themselves out
    mid-session.

    Input:
    - username: the account to delete
    """
    data = request.get_json(silent=True) or request.form
    raw_username = data.get("username")

    if not isinstance(raw_username, str):
        return jsonify({"error": "No username provided."}), 400
    target = raw_username.strip()

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
    """
    Grants or revokes an account's permission to change AC/window settings.

    Inputs:
    - username: the account to update
    - can_control: whether the account may change AC/window settings
    """
    data = request.get_json(silent=True) or request.form
    raw_username = data.get("username")

    if not isinstance(raw_username, str):
        return jsonify({"error": "No username provided."}), 400
    target = raw_username.strip()

    can_control = data.get("can_control")
    if can_control is None:
        return jsonify({"error": "No can_control value provided."}), 400

    if isinstance(can_control, str):
        can_control = can_control.strip().lower() in ("1", "true", "yes")

    matched = db.set_can_control(target, bool(can_control))

    if matched == 0:
        return jsonify({"error": "No such account."}), 404
    print(f"[OWNER] {session['user']} set can_control={bool(can_control)} for '{target}'")
    return jsonify({"username": target, "can_control": bool(can_control)})
