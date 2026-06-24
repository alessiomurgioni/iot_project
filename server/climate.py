"""
Live house state held in memory.

Sensor readings are ephemeral and high-frequency, so they live here rather than
in MongoDB (Mongo only stores accounts). A background thread refreshes the
outdoor temperature from open-meteo.

This module is the single source of truth for what the owner wants the house to
do (`_control`: AC mode + threshold + window command). The NodeMCU pulls
`_control` and acts on it; it pushes back the actual measured state via
`update_from_device`.
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
    "windows":       "closed",# ACTUAL window state reported by the device: open | closed
}

# What the owner wants; the NodeMCU pulls this and acts on it.
_control = {
    "mode":      "auto",      # auto | cool | heat | off
    "threshold": 25.0,        # auto: cool above this temp, heat below it
    "window":    "close",     # desired window command: open | close
}


def snapshot():
    """Return thread-safe copies of (state, control)."""
    with _lock:
        return dict(_state), dict(_control)


def is_online() -> bool:
    with _lock:
        last = _state["last_report"]
    return last is not None and (time.time() - last) <= config.STALE_AFTER_S


def set_control(mode=None, threshold=None, window=None):
    """
    Apply an owner command. Each call is "last write wins": this is what makes
    the empty-house auto-off in update_from_device overridable -- a webapp
    command that arrives afterwards simply replaces it.
    """
    with _lock:
        # Apply the window command first -- it decides whether the AC may change.
        if window in ("open", "close"):
            _control["window"] = window
            # Opening the windows forces the AC off (also enforced physically on
            # the Arduino). Reflect it here so the dashboard shows reality.
            if window == "open":
                _control["mode"] = "off"

        # The AC can only be changed while the windows are CLOSED. While they
        # are open it stays forced off and any mode/threshold change is ignored.
        # The dashboard greys the section out, but enforce it here too so a
        # direct API call can't bypass the lock.
        if _control["window"] == "close":
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


def update_from_device(indoor=None, people=None, fire=None, ac=None, windows=None):
    with _lock:
        prev_people = _state["people_inside"]

        if indoor not in (None, ""):
            try:
                _state["indoor_temp"] = float(indoor)
            except ValueError:
                pass

        if people not in (None, ""):
            try:
                new_people = int(float(people))
                _state["people_inside"] = new_people
                # Edge trigger: the house just emptied (>=1 -> 0).
                # Turn the AC off and close the windows. This is a ONE-SHOT
                # default, not a lock: a later webapp command (set_control)
                # overwrites _control and "goes through".
                if prev_people >= 1 and new_people == 0:
                    _control["mode"] = "off"
                    _control["window"] = "close"
            except ValueError:
                pass

        if fire not in (None, ""):
            fire_on = fire in ("1", "true", "True")
            _state["fire"] = fire_on
            # Fire => windows must be closed (the Arduino also does this on its
            # own; we set the command so the desired state stays consistent).
            if fire_on:
                _control["window"] = "close"

        if ac in ("cool", "heat", "off"):
            _state["ac_blowing"] = ac

        if windows in ("open", "closed"):
            _state["windows"] = windows

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