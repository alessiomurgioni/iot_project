from datetime import datetime
from typing import Dict, Any
from src.services.base import BaseService


class ClimateControlService(BaseService):
    """
    Owner-control + device-telemetry handler for a house's Digital Replica.
    A BaseService in the framework's services pool; DigitalTwin.execute_service
    calls execute(data, **kwargs) with an 'action' selecting the handler.
    Twin-agnostic — operates on whatever DR the twin hands it.
    """

    def execute(self, data: Dict, dr_type: str = None, attribute: str = None,
                action: str = None, **kwargs) -> Any:
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
        """Apply a dashboard command with safety rules:
        1. Fire override — while d['fire'], force AC off / windows closed.
        2. Window vs AC — opening a window forces mode 'off'; mode/threshold
           changes only apply while windows are closed.
        3. Threshold clamped to 10.0-35.0."""
        if d.get("fire"):
            d["mode"], d["windows"] = "off", "closed"
            return
        if window in ("open", "closed"):
            d["windows"] = window
            if window == "open":
                d["mode"] = "off"
        if d["windows"] == "closed":
            if mode in ("auto", "cool", "heat", "off"):
                d["mode"] = mode
            if threshold is not None:
                d["threshold"] = max(10.0, min(35.0, float(threshold)))

    def _update_from_device(self, d, indoor, people, fire, ac, windows):
        """Apply a NodeMCU telemetry report leniently: a malformed field is
        logged and skipped, never crashing the report or clobbering others.
        Occupancy 1->0 auto-shuts AC + closes windows; a true fire reading
        forces the safety override and holds while d['fire'] is True."""
        prev_people = d.get("people_inside", 0)

        if indoor not in (None, ""):
            try:
                d["indoor_temp"] = float(indoor)
            except (TypeError, ValueError):
                print(f"[CLIMATE_CONTROL] Ignoring malformed indoor: {indoor!r}")

        if people not in (None, ""):
            try:
                new_people = int(float(people))
            except (TypeError, ValueError):
                print(f"[CLIMATE_CONTROL] Ignoring malformed people: {people!r}")
            else:
                d["people_inside"] = new_people
                if prev_people >= 1 and new_people == 0:
                    d["mode"], d["windows"] = "off", "closed"

        if fire in ("1", "true", "True"):
            d["fire"] = True
        elif fire in ("0", "false", "False"):
            d["fire"] = False
        elif fire not in (None, ""):
            print(f"[CLIMATE_CONTROL] Ignoring malformed fire: {fire!r}")
        if d.get("fire"):
            d["mode"], d["windows"] = "off", "closed"

        if ac in ("cool", "heat", "off"):
            d["ac_blowing"] = ac
        elif ac not in (None, ""):
            print(f"[CLIMATE_CONTROL] Ignoring malformed ac: {ac!r}")

        if windows in ("open", "closed"):
            d["windows"] = windows
        elif windows not in (None, ""):
            print(f"[CLIMATE_CONTROL] Ignoring malformed windows: {windows!r}")

        d["last_report"] = datetime.utcnow()
