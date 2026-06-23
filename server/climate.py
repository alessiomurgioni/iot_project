"""
Live house state held in memory.

Sensor readings are ephemeral and high-frequency, so they live here rather than
in MongoDB (Mongo only stores accounts). A background thread refreshes the
outdoor temperature from open-meteo.
"""
import threading
import time

import requests

import config

_lock = threading.Lock()

_state = {
    "indoor_temp":   None,    # °C, from the DHT11 (reported by NodeMCU)
    "outdoor_temp":  None,    # °C, from open-meteo (fetched here)
    "people_inside": 0,
    "fire":          False,
    "ac_blowing":    "off",   # what the AC is actually doing: cool | heat | off
    "last_report":   None,    # epoch seconds of the last device report
}

# What the owner wants the AC to do; the NodeMCU pulls this and acts on it.
_control = {
    "mode":      "auto",      # auto | cool | heat | off
    "threshold": 25.0,        # auto: cool above this temp, heat below it
}


def snapshot():
    """Return thread-safe copies of (state, control)."""
    with _lock:
        return dict(_state), dict(_control)


def is_online() -> bool:
    with _lock:
        last = _state["last_report"]
    return last is not None and (time.time() - last) <= config.STALE_AFTER_S


def set_control(mode=None, threshold=None):
    with _lock:
        if mode in ("auto", "cool", "heat", "off"):
            _control["mode"] = mode
        if threshold is not None:
            try:
                _control["threshold"] = max(10.0, min(35.0, float(threshold)))
            except (TypeError, ValueError):
                pass
        return dict(_control)


def get_command():
    with _lock:
        return dict(_control)


def outdoor_temp():
    """Latest outdoor temperature, or None if not fetched yet."""
    with _lock:
        return _state["outdoor_temp"]


def update_from_device(indoor=None, people=None, fire=None, ac=None):
    with _lock:
        if indoor not in (None, ""):
            try:
                _state["indoor_temp"] = float(indoor)
            except ValueError:
                pass
        if people not in (None, ""):
            try:
                _state["people_inside"] = int(float(people))
            except ValueError:
                pass
        if fire not in (None, ""):
            _state["fire"] = fire in ("1", "true", "True")
        if ac in ("cool", "heat", "off"):
            _state["ac_blowing"] = ac
        _state["last_report"] = time.time()
        return dict(_control)


def _fetch_outdoor_temp():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={config.LATITUDE}&longitude={config.LONGITUDE}"
        f"&current=temperature_2m"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()["current"]["temperature_2m"]


def _poller():
    while True:
        try:
            t = _fetch_outdoor_temp()
            with _lock:
                _state["outdoor_temp"] = t
            print(f"[CLIMATE] Outdoor temperature updated: {t} C")
        except Exception as exc:
            print(f"[CLIMATE] Outdoor fetch error: {exc}")
        time.sleep(config.OUTDOOR_REFRESH_S)


def start_poller():
    threading.Thread(target=_poller, daemon=True).start()
