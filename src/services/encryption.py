import hashlib
import hmac
import json
from datetime import datetime
from typing import Any

from cryptography.fernet import Fernet

from config import settings

"""
App-wide encryption-at-rest helpers, built on a single Fernet key
(config.settings.DB_ENCRYPTION_KEY). Two building blocks:

- encrypt_payload/decrypt_payload: turn any JSON-serializable value (dicts,
  numbers, strings, datetimes) into an opaque token and back. Used to store
  Digital Replica readings/status/location and device coordinates as
  ciphertext instead of plain fields.
- pseudonymize: a deterministic HMAC-SHA256 of a value under the same key.
  Fernet tokens are randomized (a new IV each call), so they can't be used as
  a lookup key — pseudonymize gives Mongo a stable, non-reversible id to
  index/query on (e.g. in place of a plaintext device id) while the real
  value stays recoverable only via decrypt_payload for whoever holds the key.

Everything here works with the shared DB_ENCRYPTION_KEY, so anyone with that
key (server-side only, never shipped to the browser or the device firmware)
can decrypt. That's the same trust boundary as SECRET_KEY: protects a DB dump
or backup falling into the wrong hands, not against someone with full access
to the running server.
"""

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
    """Encrypt any JSON-serializable value into an opaque base64 token."""
    raw = json.dumps(value, default=_json_default).encode("utf-8")
    return _fernet.encrypt(raw).decode("utf-8")


def decrypt_payload(token: str) -> Any:
    """Inverse of encrypt_payload. Raises cryptography.fernet.InvalidToken if
    the token is malformed or was encrypted under a different key."""
    raw = _fernet.decrypt(token.encode("utf-8"))
    return json.loads(raw.decode("utf-8"), object_hook=_json_object_hook)


def pseudonymize(value: str) -> str:
    """Deterministic, non-reversible index derived from the encryption key +
    value. Same input always maps to the same output (so it works as a Mongo
    _id/lookup key), but it can't be turned back into the original value."""
    return hmac.new(
        settings.DB_ENCRYPTION_KEY.encode(), value.encode("utf-8"), hashlib.sha256
    ).hexdigest()
