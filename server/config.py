"""
Configuration for the domotic climate webapp.

Most values can be overridden with environment variables so you don't have to
edit code for deployment. CHANGE the secret key and device token before using
this anywhere real.
"""
import os

# Flask session signing key. A fixed value keeps people logged in across
# restarts; change it to a long random string and keep it secret.
SECRET_KEY = os.environ.get("WEBAPP_SECRET", "change-me-to-a-long-random-string")

# Port the webapp listens on. 8000 avoids the macOS AirPlay clash on 5000.
PORT = int(os.environ.get("WEBAPP_PORT", "8000"))

# -- Device token -------------------------------------------------------------
# The token is NEVER stored in clear on the server, only as a hash. It is given
# to the owner at purchase (printed on the device) and flashed into the NodeMCU.
# Two uses, both verified against this single hash:
#   1. The NodeMCU sends it with every /api/report and /api/command request.
#   2. A person enters it at /signup to be granted the admin role.
#
# To set your own token, run:  python gen_token_hash.py
# then paste the output here (or set the DEVICE_TOKEN_HASH env var).
# The default below is the hash of "node-secret-123" -- change it for real use.
DEVICE_TOKEN_HASH = os.environ.get(
    "DEVICE_TOKEN_HASH",
    "pbkdf2:sha256:1000000$W1tmWFAlwjQAVho2$"
    "d86943a58abee604799479ba92ccac62b98ff1b9e6ef2b09473fc67a44b609df",
)

# -- Owner key ------------------------------------------------------------------
# A second, stronger secret, separate from the device token. Anyone who proves
# they know it (via /owner/unlock) gets a session-scoped capability to manage
# accounts: view the list, remove accounts, and grant/revoke their ability to
# control the AC. It is NOT tied to any one account and is never stored in
# clear, only as a hash -- generate your own with gen_token_hash.py.
# The default below is the hash of "owner-master-456" -- change it for real use.
OWNER_KEY_HASH = os.environ.get(
    "OWNER_KEY_HASH",
    "pbkdf2:sha256:1000000$va6YH8HiyaIFVPHZ$"
    "e927ec202631e5ca2db53af0aeef4db23d979dd864a74823d7be6446c0f8fd68",
)

# -- MongoDB ------------------------------------------------------------------
# Local mongod:  mongodb://localhost:27017/
# Atlas (cloud): mongodb+srv://user:pass@cluster.xxxx.mongodb.net/
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB  = os.environ.get("MONGO_DB", "domotics")

# -- Outdoor temperature source (Cagliari, Sardinia) --------------------------
LATITUDE  = 39.2238
LONGITUDE = 9.1217
OUTDOOR_REFRESH_S = 150   # refresh outdoor temp every 2.5 min
STALE_AFTER_S     = 45    # device counts as "offline" after this many seconds
