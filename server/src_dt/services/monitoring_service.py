from datetime import datetime

from .base import BaseService


class MonitoringService(BaseService):
    """
    Analytics/monitoring over the house's Digital Replica.

    Unlike ClimateControlService, this service is read-only: it never
    mutates the Digital Replica, it only derives metrics from its current
    snapshot. Kept as a separate service (rather than folded into
    ClimateControlService) so it matches the Services layer's stated
    responsibility split — "analytics and monitoring" as a distinct
    concern from control logic and persistence.
    """

    def execute(self, data, action: str = None, **kwargs):
        drs = data.get("digital_replicas", [])
        if not drs:
            raise ValueError("No digital replica available for MonitoringService")
        d = drs[0]["data"]

        if action == "temp_delta":
            return self._temp_delta(d)
        elif action == "threshold_distance":
            return self._threshold_distance(d)
        elif action == "device_status":
            return self._device_status(d, kwargs.get("stale_after_s", 45))
        elif action == "summary":
            return {
                **self._temp_delta(d),
                **self._threshold_distance(d),
                **self._device_status(d, kwargs.get("stale_after_s", 45)),
                "fire": d.get("fire", False),
                "people_inside": d.get("people_inside", 0),
            }
        else:
            raise ValueError(f"Unknown action for MonitoringService: {action}")

    # ── Individual metrics ───────────────────────────────────────────────
    def _temp_delta(self, d):
        """How much warmer/cooler it is inside than outside."""
        indoor, outdoor = d.get("indoor_temp"), d.get("outdoor_temp")
        if indoor is None or outdoor is None:
            return {"temp_delta": None}
        return {"temp_delta": round(indoor - outdoor, 1)}

    def _threshold_distance(self, d):
        """
        In auto mode, how close the indoor temp is to triggering a mode
        switch (positive = above threshold -> cooling zone, negative =
        below -> heating zone). Only meaningful while mode == "auto".
        """
        indoor, threshold = d.get("indoor_temp"), d.get("threshold")
        if indoor is None or threshold is None or d.get("mode") != "auto":
            return {"threshold_distance": None}
        return {"threshold_distance": round(indoor - threshold, 1)}

    def _device_status(self, d, stale_after_s):
        """Liveness check based on the last device report, same rule DTFactory.is_online() uses."""
        last = d.get("last_report")
        if not last:
            return {"online": False, "seconds_since_last_report": None}
        elapsed = (datetime.utcnow() - last).total_seconds()
        return {"online": elapsed <= stale_after_s, "seconds_since_last_report": round(elapsed, 1)}
