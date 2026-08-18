from __future__ import annotations

from collections import Counter
import logging
from threading import Lock


logger = logging.getLogger("allbot.compat")
_hit_counts: Counter[str] = Counter()
_hit_counts_lock = Lock()


def record_compat_hit(telemetry_key: str, *, entrypoint: str) -> None:
    """Emit a queryable, content-free compatibility hit and keep a local counter."""

    with _hit_counts_lock:
        _hit_counts[telemetry_key] += 1
    logger.info(
        "compatibility path used",
        extra={
            "event": "compat_hit",
            "telemetry_key": telemetry_key,
            "entrypoint": entrypoint,
        },
    )


def get_compat_hit_counts() -> dict[str, int]:
    with _hit_counts_lock:
        return dict(_hit_counts)
