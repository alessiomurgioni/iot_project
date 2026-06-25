import re
import threading
import time
from functools import wraps

from werkzeug.security import check_password_hash, generate_password_hash
from flask import (
    Blueprint, redirect, render_template, request, session, url_for, jsonify
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config
import db

auth_bp = Blueprint("auth", __name__)

# ── Rate limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ── Failure lockout ────────────────────────────────────
class LockoutTracker:

    def __init__(self, threshold=5, base_delay=30, max_delay=1800):
        self.threshold = threshold
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._lock = threading.Lock()
        self._fails = {}
        self._until = {}

    def locked_for(self, key):
        """
        Returns the remaining seconds util the lock expires
        for the given key parameter (ip address or username), or 0 if not locked.

        Input:
        - key: the ip address or username

        Output:
        - the remaining seconds until the lock expires
        """
        with self._lock:
            remaining = self._until.get(key, 0) - time.time()
            return int(remaining) + 1 if remaining > 0 else 0

    def record_failure(self, key):
        """
        Keep tracks of the number of failures for the given IP or account.
        Once the threshold is surpassed, set/extend the lock time with exponential backoff.
        Returns the lock time in seconds or 0 if the threshold has not been reached yet.

        Input:
        - key: the ip address or username
        Output:
        - the lock time in seconds or 0 if the threshold has not been reached yet

        """
        with self._lock:
            n = self._fails.get(key, 0) + 1
            self._fails[key] = n
            if n >= self.threshold:
                over = n - self.threshold
                delay = min(self.base_delay * (2 ** over), self.max_delay)
                self._until[key] = time.time() + delay
                return int(delay)
            return 0

    def reset(self, key):
        """
        Clear all failure state for the given IP or account

        Input:
        - key: the ip address or username
        """
        with self._lock:
            self._fails.pop(key, None)
            self._until.pop(key, None)


# ── Lockout rules ───────────────────────────────────────────────────
login_lockout = LockoutTracker(threshold=5, base_delay=30, max_delay=1800)
signup_lockout = LockoutTracker(threshold=5, base_delay=60, max_delay=3600)
unlock_lockout = LockoutTracker(threshold=3, base_delay=60, max_delay=1800)

# A throwaway hash so a missing username still costs one hash comparison,
# keeping login timing uniform and not leaking which usernames exist.
_DUMMY_HASH = generate_password_hash("timing-equalizer")

# ── Input validation rules ───────────────────────────────────────────────────
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD_LEN = 8
MAX_USERNAME_LEN = 32
MAX_SECRET_LEN = 256


# ── Input validation rules ───────────────────────────────────────────────────
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


# ── Token Management ───────────────────────────────────────────────────
def verify_device_token(token: str) -> bool:
    if not token:
        return False
    if token in _verified_tokens:
        return True
    if check_password_hash(config.DEVICE_TOKEN_HASH, token):
        _verified_tokens.add(token)
        return True
    return False


def verify_owner_key(key: str) -> bool:
    if not key:
        return False
    if key in _verified_owner_keys:
        return True
    if check_password_hash(config.OWNER_KEY_HASH, key):
        _verified_owner_keys.add(key)
        return True
    return False


# ── Page Routing ───────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute; 30 per hour", methods=["POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        key = get_remote_address()
        wait = login_lockout.locked_for(key)
        if wait:
            error = f"Too many failed attempts. Try again in {wait}s."
            return render_template("login.html", error=error)

        if len(username) > MAX_USERNAME_LEN or len(password) > MAX_SECRET_LEN:
            locked = login_lockout.record_failure(key)
            error = (f"Too many failed attempts. Locked for {locked}s." if locked
                     else "Wrong username or password.")
            return render_template("login.html", error=error)

        user = db.get_user(username)
        if user and check_password_hash(user["password"], password):
            login_lockout.reset(key)
            session["user"] = user["username"]
            return redirect(url_for("dashboard"))

        if not user:
            check_password_hash(_DUMMY_HASH, password)

        locked = login_lockout.record_failure(key)
        if locked:
            error = f"Too many failed attempts. Locked for {locked}s."
        else:
            error = "Wrong username or password."
    return render_template("login.html", error=error)


@auth_bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per minute; 30 per hour", methods=["POST"])
def signup():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        token = request.form.get("device_token", "").strip()

        key = get_remote_address()
        wait = signup_lockout.locked_for(key)
        if wait:
            error = f"Too many invalid device-token attempts. Try again in {wait}s."
            return render_template("signup.html", error=error)

        if not token or len(token) > MAX_SECRET_LEN or not verify_device_token(token):
            locked = signup_lockout.record_failure(key)
            if locked:
                error = f"Too many invalid device-token attempts. Locked for {locked}s."
            else:
                error = "A valid device token is required to register."
        elif not username or not password:
            error = "Username and password are required."
        elif not USERNAME_RE.match(username):
            error = "Username must be 3-32 characters: letters, digits, _ . - only."
        elif len(password) < MIN_PASSWORD_LEN:
            error = f"Password must be at least {MIN_PASSWORD_LEN} characters."
        elif len(password) > MAX_SECRET_LEN:
            error = "Password is too long."
        elif password != confirm:
            error = "Passwords do not match."
        elif db.get_user(username):
            error = "That username is already taken."
        else:
            signup_lockout.reset(key)
            db.create_user(username, password)
            session["user"] = username
            return redirect(url_for("dashboard"))

    return render_template("signup.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


_verified_tokens = set()
_verified_owner_keys = set()
