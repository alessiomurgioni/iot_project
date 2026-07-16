import hashlib
import hmac
import json
from datetime import datetime

from cryptography.fernet import Fernet

from config import settings

_fernet = Fernet(
    settings.DB_ENCRYPTION_KEY.encode()
    if isinstance(settings.DB_ENCRYPTION_KEY, str)
    else settings.DB_ENCRYPTION_KEY
)

# ----------------------------------------
#       Utility Functions
# ----------------------------------------
def _json_default(obj):
    """
    Serialize datetimes so they can be encrypted.

    Input:
    - obj: object the default JSON encoder can't serialize

    Output:
    - a JSON-serializable representation of obj
    """
    if isinstance(obj, datetime):
        return {"__datetime__": obj.isoformat()}
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json_object_hook(obj: dict):
    """
    JSON decoder hook: restore serialized datetimes.

    Input:
    - obj: dict decoded from JSON

    Output:
    - the original obj
    """
    if "__datetime__" in obj:
        return datetime.fromisoformat(obj["__datetime__"])
    return obj

# ----------------------------------------
#       Cryptographic Functions
# ----------------------------------------
def encrypt_payload(value) -> str:
    """
    Serialize and encrypt a value for storage.

    Input:
    - value: any JSON-serializable value

    Output:
    - encrypted string token
    """
    raw = json.dumps(value, default=_json_default).encode("utf-8")
    return _fernet.encrypt(raw).decode("utf-8")


def decrypt_payload(token: str):
    """
    Decrypt and deserialize a value previously encrypted with encrypt_payload.

    Input:
    - token: encrypted string token

    Output:
    - the original decrypted value
    """
    raw = _fernet.decrypt(token.encode("utf-8"))
    return json.loads(raw.decode("utf-8"), object_hook=_json_object_hook)


def pseudonymize(value: str) -> str:
    """
    Hash a value to pseudonymize it.

    Inputs
    - value: the string to pseudonymize

    Output:
    - hex-encoded HMAC-SHA256
    """
    return hmac.new(
        settings.DB_ENCRYPTION_KEY.encode(), value.encode("utf-8"), hashlib.sha256
    ).hexdigest()
