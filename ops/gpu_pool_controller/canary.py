from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any

from .types import ComfyInstance, TaskProfile


@dataclass(frozen=True)
class CanaryResult:
    ok: bool
    checks: dict[str, bool]
    details: dict[str, Any]


class ComfyCanary:
    def __init__(self, timeout_seconds: float = 8.0):
        self.timeout_seconds = timeout_seconds

    def run(self, *, comfy: ComfyInstance, profile: TaskProfile) -> CanaryResult:
        details: dict[str, Any] = {}
        checks = {
            "system_stats": False,
            "queue_empty": False,
            "required_nodes": False,
            "min_vram": False,
        }
        stats = self._get_json(f"{comfy.api_url}/system_stats")
        details["system_stats"] = stats
        checks["system_stats"] = True

        queue = self._get_json(f"{comfy.api_url}/queue")
        details["queue"] = {
            "running": len(queue.get("queue_running") or []),
            "pending": len(queue.get("queue_pending") or []),
        }
        checks["queue_empty"] = (
            details["queue"]["running"] == 0 and details["queue"]["pending"] == 0
        )

        object_info = self._get_json(f"{comfy.api_url}/object_info")
        missing_nodes = sorted(set(profile.required_nodes) - set(object_info))
        details["missing_required_nodes"] = missing_nodes
        checks["required_nodes"] = not missing_nodes

        if profile.min_vram_gb is None:
            checks["min_vram"] = True
        else:
            devices = stats.get("devices") or []
            total_vram = float((devices[0] if devices else {}).get("vram_total") or 0)
            checks["min_vram"] = total_vram >= profile.min_vram_gb * 1000**3
            details["vram_total_gb"] = round(total_vram / 1000**3, 2)
            details["vram_total_gib"] = round(total_vram / 1024**3, 2)
            details["min_vram_gb"] = profile.min_vram_gb

        return CanaryResult(
            ok=all(checks.values()),
            checks=checks,
            details=details,
        )

    def _get_json(self, url: str) -> dict[str, Any]:
        with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
            return json.load(response)
