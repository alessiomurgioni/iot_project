from datetime import datetime

# FIX: relative import instead of the hardcoded "server_perlamerda.src...." path.
from .base import BaseService


class ClimateControlService(BaseService):
    """
    Owner AC/window control, plus ingestion of NodeMCU device reports.
    Same rules as the original climate.py:
      - Fire detected overrides everything: AC off, windows closed.
      - Opening the windows forces the AC off.
      - AC mode/threshold only change while the windows are closed.
      - House emptying (people_inside: 1 -> 0) forces AC off, windows closed.
    """

    def execute(self, data, action=None, **kwargs):
        dr = data["digital_replicas"][0]
        d = dr["data"]

        if action == "set_control":
            self._set_control(d, kwargs.get("mode"), kwargs.get("threshold"), kwargs.get("window"))
        elif action == "update_from_device":
            self._update_from_device(
                d, kwargs.get("indoor"), kwargs.get("people"),
                kwargs.get("fire"), kwargs.get("ac"), kwargs.get("windows"),
            )
        else:
            raise ValueError(f"Unknown action: {action}")
        return dr

    def _set_control(self, d, mode, threshold, window):
        # Fire always wins
        if d["fire"]:
            d["mode"], d["windows"] = "off", "closed"
            return
        # Windows open forces AC off. `window` here must already be the
        # schema value ("open"/"closed") — translation from the dashboard's
        # "close" happens at the API boundary, not here.
        if window in ("open", "closed"):
            d["windows"] = window
            if window == "open":
                d["mode"] = "off"
        # AC only changes while windows are closed
        if d["windows"] == "closed":
            if mode in ("auto", "cool", "heat", "off"):
                d["mode"] = mode
            if threshold is not None:
                d["threshold"] = max(10.0, min(35.0, float(threshold)))

    def _update_from_device(self, d, indoor, people, fire, ac, windows):
        prev_people = d["people_inside"]
        if indoor not in (None, ""):
            d["indoor_temp"] = float(indoor)
        if people not in (None, ""):
            new_people = int(float(people))
            d["people_inside"] = new_people
            if prev_people >= 1 and new_people == 0:
                d["mode"], d["windows"] = "off", "closed"
        if fire not in (None, ""):
            d["fire"] = fire in ("1", "true", "True")
            if d["fire"]:
                d["mode"], d["windows"] = "off", "closed"
        if ac in ("cool", "heat", "off"):
            d["ac_blowing"] = ac
        if windows in ("open", "closed"):
            d["windows"] = windows

        # FIX (was missing): stamp every device report as a liveness signal.
        # DTFactory.is_online() depends on this field to decide "Device online".
        d["last_report"] = datetime.utcnow()
