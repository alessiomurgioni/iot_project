import os

"""
Application-level settings that sit alongside the reference framework's Mongo
config (config/database.yaml + ConfigLoader). Kept separate so the DB config
stays exactly in the reference format while the domotic/multi-tenant app adds
its own knobs here.
"""

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Flask session signing key — override with WEBAPP_SECRET in production.
SECRET_KEY = os.environ.get(
    "WEBAPP_SECRET",
    "f654111eabeba73ecb7758faa65425dc1a9b95c6a4391e02ea36289fa429f300",
)

# Web server port (the NodeMCU firmware must target the same one).
PORT = int(os.environ.get("WEBAPP_PORT", "8000"))

# App-wide symmetric key used to encrypt sensitive data at rest (Digital
# Replica readings/status/location, device coordinates) via src/services/
# encryption.py. Must be a 32 url-safe base64-encoded key (what
# cryptography.fernet.Fernet.generate_key() produces) — override with
# DB_ENCRYPTION_KEY in production. The fallback below is a fixed dev-only key
# so a fresh checkout runs without extra setup; anyone with this repo can
# decrypt a dev database, so never reuse it outside local development.
DB_ENCRYPTION_KEY = os.environ.get(
    "DB_ENCRYPTION_KEY",
    "rnAvD-ZLeNqPRmyfWPZnfE8S48sxRc9Q5frI2Hu_iTU=",
)

# Digital Replica schema for the house: the schema TYPE key and the YAML path.
SCHEMA_TYPE = "house"
SCHEMA_PATH = os.environ.get(
    "SCHEMA_PATH",
    os.path.join(_BASE, "src", "virtualization", "templates", "DHome.yaml"),
)

# Outdoor-temperature feed (per-house coords live in each DR profile; these are
# the fallback when a house hasn't recorded its own location).
OUTDOOR_REFRESH_S = int(os.environ.get("OUTDOOR_REFRESH_S", "150"))

# Seconds of NodeMCU silence before the device is considered offline.
STALE_AFTER_S = int(os.environ.get("STALE_AFTER_S", "45"))

# Outgoing email for fire-alarm alerts
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "NetwatchHomeController@gmail.com"
SMTP_PASSWORD = "rlal hxxq hzur qrat"
SMTP_USE_TLS = True
ALERT_FROM_EMAIL = "NetwatchHomeController@gmail.com"