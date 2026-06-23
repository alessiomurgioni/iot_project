"""
MongoDB access layer for user accounts.

Every account requires the device token at signup, so every account that
exists is equally trusted to use the house -- but the owner (whoever holds the
separate, stronger owner key) can manage accounts and decide, per account,
whether it is allowed to change AC settings.

Collection: domotics.users
Document shape:
    {
        "username": "alice",
        "password": "<werkzeug hash>",   # NEVER the raw password
        "can_control": true              # may change AC mode/threshold
    }
"""
from pymongo import MongoClient, ASCENDING
from werkzeug.security import generate_password_hash, check_password_hash

import config

# serverSelectionTimeoutMS keeps the app from hanging forever if mongod is down;
# the actual connection is lazy (made on first real query).
_client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
_db = _client[config.MONGO_DB]
users = _db["users"]

try:
    # Enforce unique usernames at the database level.
    users.create_index([("username", ASCENDING)], unique=True)
except Exception as exc:  # mongod not reachable yet -- will surface on first use
    print(f"[DB] Warning: could not create index now ({exc}). "
          f"Is MongoDB running at {config.MONGO_URI}?")


def user_count() -> int:
    return users.count_documents({})


def get_user(username: str):
    return users.find_one({"username": username})


def create_user(username: str, password: str, can_control: bool = True):
    users.insert_one({
        "username": username,
        "password": generate_password_hash(password),
        "can_control": bool(can_control),
    })


def verify_user(username: str, password: str):
    """Return the user document if credentials are valid, else None."""
    u = get_user(username)
    if u and check_password_hash(u["password"], password):
        return u
    return None


def list_users():
    """All users, without password hashes or Mongo _id (JSON-safe)."""
    return list(users.find({}, {"password": 0, "_id": 0}))


def set_can_control(username: str, can_control: bool) -> int:
    result = users.update_one(
        {"username": username},
        {"$set": {"can_control": bool(can_control)}},
    )
    return result.matched_count


def delete_user(username: str) -> int:
    return users.delete_one({"username": username}).deleted_count
