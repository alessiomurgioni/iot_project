import hashlib
import hmac
import json
from datetime import datetime
from typing import Any

from cryptography.fernet import Fernet

from config import settings

_fernet = Fernet(
    settings.DB_ENCRYPTION_KEY.encode()
    if isinstance(settings.DB_ENCRYPTION_KEY, str)
    else settings.DB_ENCRYPTION_KEY
)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return {"__datetime__": obj.isoformat()}
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json_object_hook(obj: dict) -> Any:
    if "__datetime__" in obj:
        return datetime.fromisoformat(obj["__datetime__"])
    return obj


def encrypt_payload(value: Any) -> str:
    raw = json.dumps(value, default=_json_default).encode("utf-8")
    return _fernet.encrypt(raw).decode("utf-8")


def decrypt_payload(token: str) -> Any:
    raw = _fernet.decrypt(token.encode("utf-8"))
    return json.loads(raw.decode("utf-8"), object_hook=_json_object_hook)


def pseudonymize(value: str) -> str:
    return hmac.new(
        settings.DB_ENCRYPTION_KEY.encode(), value.encode("utf-8"), hashlib.sha256
    ).hexdigest()
