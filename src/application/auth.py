import re
import threading
import time
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
from flask import (
    Blueprint, redirect, render_template, request, session, url_for, jsonify,
    current_app,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

auth_bp = Blueprint("auth", __name__)
limiter = Limiter(key_func=get_remote_address)


# ----------------------------------------
#       Utility Functions
# ----------------------------------------
def db():
    """
    Get the app's DatabaseService.

    Output:
    - the DatabaseService instance
    """
    return current_app.config["DB_SERVICE"]


def is_api() -> bool:
    """
    Check whether the current request path is under /api/.

    Output:
    - True if the current request is an API call, else False
    """
    return "/api/" in request.path


# ----------------------------------------
#       Lockout Mechanism
# ----------------------------------------
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
        Get the remaining lockout time for an ip.

        Input:
        - key: the tracked IP address

        Output:
        - seconds remaining before the IP can retry communication
        """
        with self._lock:
            remaining = self._until.get(key, 0) - time.time()
            return int(remaining) + 1 if remaining > 0 else 0

    def record_failure(self, key):
        """
        Record a failed attempt for an IP.

        Input:
        - key: the tracked IP address

        Output:
        - the lockout delay in seconds if triggered
        """
        with self._lock:
            n = self._fails.get(key, 0) + 1
            self._fails[key] = n
            if n >= self.threshold:
                delay = min(self.base_delay * (2 ** (n - self.threshold)), self.max_delay)
                self._until[key] = time.time() + delay
                return int(delay)
            return 0

    def reset(self, key):
        """
        Clear failure history for an IP after a successful attempt.

        Input:
          - key: the tracked IP address
        """
        with self._lock:
            self._fails.pop(key, None)
            self._until.pop(key, None)


# ----------------------------------------
#    Utility Constants and Variables
# ----------------------------------------
login_lockout = LockoutTracker(threshold=5, base_delay=30, max_delay=1800)
claim_lockout = LockoutTracker(threshold=5, base_delay=60, max_delay=3600)

_DUMMY_HASH = generate_password_hash("timing-equalizer")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 8
MAX_USERNAME_LEN = 32
MAX_EMAIL_LEN = 254
MAX_SECRET_LEN = 256


# ----------------------------------------
#       Privileges Checks
# ----------------------------------------
def is_owner(username, dt_id):
    """
    Check whether a user has the owner role on a twin.

    Inputs:
    - username: the account's username
    - dt_id: the twin's id

    Output:
    - True if the user is an owner of the twin, else False
    """
    m = db().get_membership(username, dt_id)
    return bool(m and m.get("role") == "owner")


def can_control(username, dt_id):
    """
    Check whether a user is allowed to change control settings on a twin.

    Inputs:
    - username: the account's username
    - dt_id: the twin's id

    Output:
    - True if the user can control the twin, else False
    """
    m = db().get_membership(username, dt_id)
    return bool(m and m.get("can_control"))


_verified_device_tokens = set()  # cached list of verified tokens to speed up the lookup process
_verified_owner_keys = set()  # cached list of verified tokens to speed up the lookup process


def verify_device_token(device_id: str, token: str) -> bool:
    """
    Check a device's auth token against its stored hash.

    Inputs:
    - device_id: the device's id
    - token: the token to check

    Output:
    - True if the token is valid, else False
    """
    if not device_id or not token:
        return False
    if (device_id, token) in _verified_device_tokens:
        return True
    d = db().get_device(device_id)
    if d and check_password_hash(d["token_hash"], token):
        _verified_device_tokens.add((device_id, token))
        return True
    return False


def verify_owner_key(device_id: str, key: str) -> bool:
    """
    Check a device's owner key against its stored hash.

    Inputs:
    - device_id: the device's id
    - key: the owner key to check

    Output:
    - True if the key is valid, else False
    """
    if not device_id or not key:
        return False
    if (device_id, key) in _verified_owner_keys:
        return True
    d = db().get_device(device_id)
    if d and check_password_hash(d["owner_key_hash"], key):
        _verified_owner_keys.add((device_id, key))
        return True
    return False


# ----------------------------------------
#      Flask route decorators
# ----------------------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        username = session.get("user")
        if not username or not db().get_user(username):
            session.clear()
            if is_api():
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return wrapper


def twin_member_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        username = session.get("user")
        dt_id = kwargs.get("dt_id")
        if not username or not db().get_user(username):
            session.clear()
            if is_api():
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("auth.login"))
        if not db().get_membership(username, dt_id):
            if is_api():
                return jsonify({"error": "forbidden"}), 403
            return redirect(url_for("web.home"))
        return f(*args, **kwargs)

    return wrapper


def twin_owner_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        username = session.get("user")
        dt_id = kwargs.get("dt_id")
        if not username or not db().get_user(username):
            session.clear()
            if is_api():
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("auth.login"))
        if not is_owner(username, dt_id):
            if is_api():
                return jsonify({"error": "owner rights required"}), 403
            return redirect(url_for("web.home"))
        return f(*args, **kwargs)

    return wrapper


# ----------------------------------------
#      Flask routes
# ----------------------------------------
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
            return render_template("login.html", error=f"Too many attempts. Try again in {wait}s.")
        if len(username) > MAX_USERNAME_LEN or len(password) > MAX_SECRET_LEN:
            locked = login_lockout.record_failure(key)
            return render_template("login.html",
                                   error=(
                                       f"Too many attempts. Locked for {locked}s." if locked else "Wrong username or password."))

        user = db().get_user(username)
        if user and check_password_hash(user["password"], password):
            login_lockout.reset(key)
            session["user"] = user["username"]
            return redirect(url_for("web.home"))
        if not user:
            check_password_hash(_DUMMY_HASH, password)
        locked = login_lockout.record_failure(key)
        error = (f"Too many attempts. Locked for {locked}s." if locked else "Wrong username or password.")
    return render_template("login.html", error=error)


@auth_bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per minute; 30 per hour", methods=["POST"])
def signup():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not username or not password or not email:
            error = "Username, email and password are required."
        elif not USERNAME_RE.match(username):
            error = "Username must be 3-32 characters: letters, digits, _ . - only."
        elif len(email) > MAX_EMAIL_LEN or not EMAIL_RE.match(email):
            error = "Please enter a valid email address."
        elif len(password) < MIN_PASSWORD_LEN:
            error = f"Password must be at least {MIN_PASSWORD_LEN} characters."
        elif len(password) > MAX_SECRET_LEN:
            error = "Password is too long."
        elif password != confirm:
            error = "Passwords do not match."
        elif db().get_user(username):
            error = "That username is already taken."
        elif db().get_user_by_email(email):
            error = "An account with that email already exists."
        else:
            db().create_user(username, generate_password_hash(password), email)
            session["user"] = username
            return redirect(url_for("web.home"))
    return render_template("signup.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
