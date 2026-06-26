from pymongo import MongoClient, ASCENDING
from werkzeug.security import generate_password_hash, check_password_hash
import config

# ── Database Connection Establishment ────────────────────────────────────────────────
_client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
_db = _client[config.MONGO_DB]
users = _db["users"]
house_state = _db["house_state"]

try:

    users.create_index([("username", ASCENDING)], unique=True)
except Exception as exc:
    print(f"[DB] Warning: could not create index now ({exc}). "
          f"Is MongoDB running at {config.MONGO_URI}?")


# ── Users DB Management Functions ────────────────────────────────────────────────
def get_user(username: str):
    """
    Returns the raw Mongo document for the given username (including the
    password hash and can_control flag), or None if no such account exists.

    Input:
    - username: username to look for
    """
    return users.find_one({"username": username})


def create_user(username: str, password: str, can_control: bool = True):
    """
    Creates a new account: hashes the password and sets can_control,
    which gates whether this account is allowed to change AC/window settings.
    Defaults to True so a normal signup can control the house unless the owner later revokes it.

    Inputs:
    - username: username
    - password: password
    - can_control: whether this account is allowed to change AC/window settings

    """
    users.insert_one({
        "username": username,
        "password": generate_password_hash(password),
        "can_control": bool(can_control),
    })


def list_users():
    """
    Returns every account as a list of dicts, with the password
    hash and Mongo _id stripped out. Used by the owner management page to
    populate the accounts table.
    """
    return list(users.find({}, {"password": 0, "_id": 0}))


def set_can_control(username: str, can_control: bool) -> int:
    """
    Edits the can_control parameter to set whether the given account is allowed to change AC/window
    settings.

    Inputs:
    - username: username
    - can_control: whether the specified account is allowed to change AC/window settings
    """
    result = users.update_one(
        {"username": username},
        {"$set": {"can_control": bool(can_control)}},
    )
    return result.matched_count


def delete_user(username: str) -> int:
    """
    Permanently removes the given account.

    Input:
    - username: username
    """
    return users.delete_one({"username": username}).deleted_count

# ── States DB Management Functions ────────────────────────────────────────────────
def save_house_state(state: dict, control: dict):
    """
    Saves the house state to the database.

    Inputs:
    - state: copy of each state parameter
    - control: copy of each control parameter
    """
    doc = {}
    doc.update(state)
    doc.update(control)
    house_state.update_one(
        {"_id": "latest"},
        {"$set": doc},
        upsert=True,
    )