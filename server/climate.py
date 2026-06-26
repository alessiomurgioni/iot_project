import threading
import time
import requests
import config
import db

# ── Variables ──────────────────────────────────────────────────────────
_lock = threading.Lock()
_state = {
    "indoor_temp": None,
    "outdoor_temp": None,
    "people_inside": 0,
    "fire": False,
    "ac_blowing": "off",
    "last_report": None,
    "windows": "closed", }
_control = {
    "mode": "auto",
    "threshold": 25.0,
    "window": "close", }


# ── Utility Functions ───────────────────────────────────────────────────
def snapshot():
    """
    Returns thread-safe copies of state and control variables for the dashboard to
    render them consistently.
    """
    with _lock:
        return dict(_state), dict(_control)


def is_online() -> bool:
    """
    Returns whether the device is currently considered online or not.
    """
    with _lock:
        last = _state["last_report"]
    return last is not None and (time.time() - last) <= config.STALE_AFTER_S


def set_control(mode=None, threshold=None, window=None):
    """
    Applies the various possible commands to the dashboard state.
    The commands follows an hierarchical structure:
        - if a fire is detected every windows / AC command is overrided and AC and Windows are automatically
          shut of and closed.
        - in normal operating situation the windows status is able to override the AC commands.
          If the windows are opened the AC is automatically turned off.

    Inputs:
    - mode: commanded AC working mode
    - threshold: commanded temperature threshold
    - window: commanded home's windows status

    Output:
    - result: a dictionary with the various control values
    """
    with _lock:
        if _state["fire"]:
            _control["mode"] = "off"
            _control["window"] = "close"
        else:
            if window in ("open", "close"):
                _control["window"] = window
                if window == "open":
                    _control["mode"] = "off"

            if _control["window"] == "close":
                if mode in ("auto", "cool", "heat", "off"):
                    _control["mode"] = mode
                if threshold is not None:
                    try:
                        _control["threshold"] = max(10.0, min(35.0, float(threshold)))
                    except (TypeError, ValueError):
                        pass

        result = dict(_control)

    db.save_house_state(*snapshot())
    return result


def get_command():
    """
    Returns a copy of the current desired control state.
    """
    with _lock:
        return dict(_control)


def outdoor_temp():
    """
    Returns the latest outdoor temperature stored in _state, or None if the
    API hasn't fetched one yet.
    """
    with _lock:
        return _state["outdoor_temp"]


def update_from_device(indoor=None, people=None, fire=None, ac=None, windows=None):
    """
    Updates the actual measured state and stamps last_report with the current time.
    Also applies two other control measures:
    - if the house just emptied (people count dropping from >=1 to 0), the AC is turned off and the
      windows commanded closed. If after this the user sends another command it simply overwrites it.

    - If fire is reported, the windows are forced closed and the AC forced off.
      Unlike the empty-house default above, this is enforced again
      in set_control() so a later user command can't override it while the fire is still active.

    Inputs:
    - indoor: indoor temperature
    - people: number of persons inside the house
    - fire: flag that notifies if a fire is detected
    - ac: AC state
    - windows: home's windows status

    Output:
    - result: a dictionary with the various control values
    """

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
                if prev_people >= 1 and new_people == 0:
                    _control["mode"] = "off"
                    _control["window"] = "close"
            except ValueError:
                pass

        if fire not in (None, ""):
            fire_on = fire in ("1", "true", "True")
            _state["fire"] = fire_on
            if fire_on:
                _control["window"] = "close"
                _control["mode"] = "off"

        if ac in ("cool", "heat", "off"):
            _state["ac_blowing"] = ac

        if windows in ("open", "closed"):
            _state["windows"] = windows

        _state["last_report"] = time.time()
        result = dict(_control)

    db.save_house_state(*snapshot())
    return result


# ── Outdoor temperature related functions ────────────────────────────────────────────────
def fetch_outdoor_temp():
    """
    Calls the Open-Meteo API for the current outdoor temperature at the
    configured latitude/longitude and returns it as a float.
    """
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={config.LATITUDE}&longitude={config.LONGITUDE}"
        f"&current=temperature_2m"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()["current"]["temperature_2m"]


def poller():
    """
    Background loop that refreshes the outdoor temperature on a fixed
    interval.
    """
    while True:
        try:
            t = fetch_outdoor_temp()
            with _lock:
                _state["outdoor_temp"] = t
            print(f"[CLIMATE] Outdoor temperature updated: {t} C")
        except Exception as exc:
            print(f"[CLIMATE] Outdoor fetch error: {exc}")
        time.sleep(config.OUTDOOR_REFRESH_S)


def start_poller():
    """
    Starts the background outdoor-temperature poller as a daemon thread, so
    it runs for the lifetime of the process. Called once at app startup.
    """
    threading.Thread(target=poller, daemon=True).start()
