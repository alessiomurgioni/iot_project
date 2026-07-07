from datetime import datetime
from typing import Dict, Any
from src.services.base import BaseService


class MonitoringService(BaseService):
    """Read-only analytics over a house's Digital Replica (never mutates it).
    action='summary' bundles temp delta, threshold distance, device liveness,
    and raw fire/occupancy for the dashboard."""

    def execute(self, data: Dict, dr_type: str = None, attribute: str = None,
                action: str = "summary", stale_after_s: int = 45, **kwargs) -> Any:
        drs = data.get("digital_replicas", [])
        if not drs:
            raise ValueError("No digital replica available for MonitoringService")
        d = drs[0]["data"]

        if action == "temp_delta":
            return self._temp_delta(d)
        elif action == "threshold_distance":
            return self._threshold_distance(d)
        elif action == "device_status":
            return self._device_status(d, stale_after_s)
        elif action == "summary":
            return {
                **self._temp_delta(d),
                **self._threshold_distance(d),
                **self._device_status(d, stale_after_s),
                "fire": d.get("fire", False),
                "people_inside": d.get("people_inside", 0),
            }
        raise ValueError(f"Unknown action for MonitoringService: {action}")

    def _temp_delta(self, d):
        indoor, outdoor = d.get("indoor_temp"), d.get("outdoor_temp")
        if indoor is None or outdoor is None:
            return {"temp_delta": None}
        return {"temp_delta": round(indoor - outdoor, 1)}

    def _threshold_distance(self, d):
        indoor, threshold = d.get("indoor_temp"), d.get("threshold")
        if indoor is None or threshold is None or d.get("mode") != "auto":
            return {"threshold_distance": None}
        return {"threshold_distance": round(indoor - threshold, 1)}

    def _device_status(self, d, stale_after_s):
        last = d.get("last_report")
        if not last:
            return {"online": False, "seconds_since_last_report": None}
        elapsed = (datetime.utcnow() - last).total_seconds()
        return {"online": elapsed <= stale_after_s,
                "seconds_since_last_report": round(elapsed, 1)}
