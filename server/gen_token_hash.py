"""
Generate a hash for a secret -- either the device token or the owner key.
Both use the same hashing scheme, so this script works for either.

Usage:
    python gen_token_hash.py                 # prompts for the secret (hidden)
    python gen_token_hash.py my-secret-here  # secret as an argument

Paste the printed line into config.py (DEVICE_TOKEN_HASH or OWNER_KEY_HASH) or
export it as the matching environment variable:
    export DEVICE_TOKEN_HASH='pbkdf2:sha256:...'
    export OWNER_KEY_HASH='pbkdf2:sha256:...'

The device token: flashed into the NodeMCU and printed on the unit; anyone
who knows it can register an account. The owner key: a separate, stronger
secret known only to you; proving it unlocks account management (viewing,
removing accounts, and granting/revoking their ability to control the AC).
The server only ever stores hashes of either value.
"""
import getpass
import sys

from werkzeug.security import generate_password_hash


def main():
    if len(sys.argv) > 1:
        secret = sys.argv[1]
    else:
        secret = getpass.getpass("Secret to hash (device token or owner key): ")
        if secret != getpass.getpass("Confirm: "):
            print("Values do not match.")
            sys.exit(1)

    if not secret:
        print("Empty secret.")
        sys.exit(1)

    h = generate_password_hash(secret, method="pbkdf2:sha256")
    print("\nHash (paste into DEVICE_TOKEN_HASH or OWNER_KEY_HASH):")
    print(h)


if __name__ == "__main__":
    main()
