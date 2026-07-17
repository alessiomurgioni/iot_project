from datetime import datetime
from src.services.base import BaseService


class ClimateControlService(BaseService):
    def execute(self, data: dict, dr_type: str = None, attribute: str = None,
                action: str = None, **kwargs):
        """
        Dispatch to set_control (owner command) or update_from_device (sensor report).

        Inputs:
        - data: the twin's Digital Replica data
        - action: "set_control" or "update_from_device"
        - kwargs: action-specific fields (mode, threshold, windows, indoor, people, fire, ac)

        Output:
        - the updated Digital Replica
        """
        dr = data["digital_replicas"][0]
        d = dr["data"]
        if action == "set_control":
            self._set_control(d, kwargs.get("mode"), kwargs.get("threshold"), kwargs.get("windows"))
        elif action == "update_from_device":
            self._update_from_device(
                d, kwargs.get("indoor"), kwargs.get("people"),
                kwargs.get("fire"), kwargs.get("ac"), kwargs.get("windows"),
            )
        else:
            raise ValueError(f"Unknown action: {action}")
        return dr

    def _set_control(self, d, mode, threshold, windows):
        """
        Apply an owner/member control change.

        Inputs:
        - d: the replica's data dict, mutated in place
        - mode: "auto" | "cool" | "heat" | "off", or None to leave unchanged
        - threshold: target temperature, or None to leave unchanged
        - windows: "open" | "closed", or None to leave unchanged
        """
        if d.get("fire"):
            d["mode"], d["windows"] = "off", "closed"
            return
        if windows in ("open", "closed"):
            d["windows"] = windows
            if windows == "open":
                d["mode"] = "off"
        if d["windows"] == "closed":
            if mode in ("auto", "cool", "heat", "off"):
                d["mode"] = mode
            if threshold is not None:
                d["threshold"] = max(10.0, min(35.0, float(threshold)))

    def _update_from_device(self, d, indoor, people, fire, ac, windows):
        """
        Merge a NodeMCU sensor report into the twin's data, validating each field.

        Inputs:
        - d: the replica's data dict, mutated in place
        - indoor: reported indoor temperature
        - people: reported people count
        - fire: reported fire-alarm state
        - ac: reported AC blowing state
        - windows: reported window state
        """
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
            if windows == "open":
                d["mode"] = "off"
        elif windows not in (None, ""):
            print(f"[CLIMATE_CONTROL] Ignoring malformed windows: {windows!r}")

        d["last_report"] = datetime.utcnow()
