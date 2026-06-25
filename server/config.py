import os

# Flask session signing key.
SECRET_KEY = os.environ.get("WEBAPP_SECRET", "f654111eabeba73ecb7758faa65425dc1a9b95c6a4391e02ea36289fa429f300")

# Port the webapp listens on.
PORT = int(os.environ.get("WEBAPP_PORT", "8000"))

# ── Device Token's Hash ───────────────────────────────────────────────────
DEVICE_TOKEN_HASH = os.environ.get(
    "DEVICE_TOKEN_HASH",
    "pbkdf2:sha256:1000000$W1tmWFAlwjQAVho2$d86943a58abee604799479ba92ccac62b98ff1b9e6ef2b09473fc67a44b609df",
)

# ── Owner Key's Hash ───────────────────────────────────────────────────
OWNER_KEY_HASH = os.environ.get(
    "OWNER_KEY_HASH",
    "pbkdf2:sha256:1000000$va6YH8HiyaIFVPHZ$e927ec202631e5ca2db53af0aeef4db23d979dd864a74823d7be6446c0f8fd68",
)

# ── Mongo DB ─────────────────────────────────────────────────────────
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB  = os.environ.get("MONGO_DB", "domotics")

# ── Outdoor Temperature Parameters ───────────────────────────────────────────────────
LATITUDE  = 39.2238
LONGITUDE = 9.1217
OUTDOOR_REFRESH_S = 150   # refresh outdoor temp every 2.5 min
STALE_AFTER_S     = 45    # device counts as "offline" after this many seconds
