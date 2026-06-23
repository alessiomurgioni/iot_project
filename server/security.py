"""
Device-token and owner-key verification.

Both secrets are stored only as hashes (config.DEVICE_TOKEN_HASH /
config.OWNER_KEY_HASH). We verify any presented value against the matching
hash. Each gets its own small cache of values already proven true during this
process, so the (deliberately slow) hash check runs once per distinct value
rather than on every request. The cache only ever holds values the caller
already sent us in clear, so it adds no exposure beyond what the request
itself contained, and it never caches failed attempts.
"""
from werkzeug.security import check_password_hash

import config

_verified_tokens = set()
_verified_owner_keys = set()


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
