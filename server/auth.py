"""
Authentication: login, signup, logout, plus the access-control decorators used
across the app.

Every account requires the device token at signup -- that's the bar for using
the house at all. A second, separate secret -- the owner key -- is not tied to
any account; whoever proves they know it (via /owner/unlock) gets a
session-scoped capability to manage accounts.

Session keys:
    session["user"]   -> username (presence means logged in)
    session["owner"]  -> True once the owner key has been unlocked this session
"""
from functools import wraps

from flask import (
    Blueprint, redirect, render_template, request, session, url_for, jsonify
)

import db
import security

auth_bp = Blueprint("auth", __name__)


# -- Decorators -------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper


def owner_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("auth.login"))
        if not session.get("owner"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "owner key required"}), 403
            return redirect(url_for("owner.unlock"))
        return f(*args, **kwargs)
    return wrapper


# -- Routes ----------------------------------------------------------------------
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.verify_user(username, password)
        if user:
            session["user"] = user["username"]
            return redirect(url_for("views.dashboard"))
        error = "Wrong username or password."
    return render_template("login.html", error=error)


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")
        token    = request.form.get("device_token", "").strip()

        if not token or not security.verify_device_token(token):
            error = "A valid device token is required to register."
        elif not username or not password:
            error = "Username and password are required."
        elif password != confirm:
            error = "Passwords do not match."
        elif db.get_user(username):
            error = "That username is already taken."
        else:
            db.create_user(username, password)
            session["user"] = username
            return redirect(url_for("views.dashboard"))

    return render_template("signup.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
