from __future__ import annotations

import os
import socket
import time
import uuid
from typing import Any


def build_task_control_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def build_task_control_health_payload(
    *,
    enabled: bool,
    worker_id: str,
    task_states: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "enabled" if enabled else "disabled",
        "worker_id": worker_id,
        "updated_at": time.time(),
        "tasks": task_states,
    }
