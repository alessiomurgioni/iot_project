import threading
import time
import requests
import config

# ── Outdoor temperature (external feed, not twin/control logic) ────────────
# This stays separate from the Digital Twin: it's a read-only external data
# source (Open-Meteo), not a decision the house makes about itself. The DR's
# own "outdoor_temp" field is a snapshot copied in by api.py's /state route;
# this module is the live cache the poller writes to.
_lock = threading.Lock()
_outdoor_temp = None


def outdoor_temp():
    """Returns the latest polled outdoor temperature, or None if not fetched yet."""
    with _lock:
        return _outdoor_temp


def fetch_outdoor_temp():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={config.LATITUDE}&longitude={config.LONGITUDE}"
        f"&current=temperature_2m"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()["current"]["temperature_2m"]


def poller():
    global _outdoor_temp
    while True:
        try:
            t = fetch_outdoor_temp()
            with _lock:
                _outdoor_temp = t
            print(f"[CLIMATE] Outdoor temperature updated: {t} C")
        except Exception as exc:
            print(f"[CLIMATE] Outdoor fetch error: {exc}")
        time.sleep(config.OUTDOOR_REFRESH_S)


def start_poller():
    threading.Thread(target=poller, daemon=True).start()
