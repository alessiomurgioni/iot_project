import threading
import time
import requests
from config import settings
from src.services.encryption import decrypt_payload

"""
Per-house outdoor-temperature feed. A background thread iterates every twin,
polls Open-Meteo for that house's coordinates (from its Digital Replica
profile, falling back to the platform defaults), and caches the reading keyed
by dt_id. Read by the /state and /outdoor-temp routes. Kept out of the DT
control logic — it's a read-only external source.
"""

_lock = threading.Lock()
_outdoor_by_dt = {}


def outdoor_temp(dt_id: str):
    with _lock:
        return _outdoor_by_dt.get(dt_id)


def fetch_outdoor_temp(lat: float, lon: float) -> float:
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}&current=temperature_2m")
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()["current"]["temperature_2m"]


def _coords_for(factory, reg):
    refs = reg.get("digital_replicas", [])
    if not refs:
        return None, None
    device_id = refs[0]["id"]
    device = factory.db_service.get_device(device_id)
    if not device:
        return None, None
    lat_enc = device.get("latitude")
    lon_enc = device.get("longitude")
    if not lat_enc or not lon_enc:
        return None, None
    lat = float(decrypt_payload(lat_enc))
    lon = float(decrypt_payload(lon_enc))
    return lat, lon


def poller(factory):
    while True:
        try:
            for reg in factory.list_dts():
                dt_id = reg["_id"]
                try:
                    lat, lon = _coords_for(factory, reg)
                    t = fetch_outdoor_temp(lat, lon)
                    with _lock:
                        _outdoor_by_dt[dt_id] = t
                    print(f"[CLIMATE] {dt_id}: outdoor {t} C")
                except Exception as exc:
                    print(f"[CLIMATE] {dt_id}: outdoor fetch error: {exc}")
        except Exception as exc:
            print(f"[CLIMATE] Poller cycle error: {exc}")
        time.sleep(settings.OUTDOOR_REFRESH_S)


def start_poller(factory):
    threading.Thread(target=poller, args=(factory,), daemon=True).start()
