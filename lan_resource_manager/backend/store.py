from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import OperationStatus, TERMINAL_OPERATION_STATUSES


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OperationStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.operations_path = data_dir / "operations.json"
        self.snapshot_path = data_dir / "live-snapshot.json"
        self.operations: dict[str, dict[str, Any]] = {}
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.operations_path.exists():
            self.operations = json.loads(
                self.operations_path.read_text(encoding="utf-8")
            )
        changed = False
        for operation in self.operations.values():
            if operation.get("status") not in {
                str(status) for status in TERMINAL_OPERATION_STATUSES
            }:
                operation.update(
                    status=OperationStatus.INTERRUPTED,
                    stage="interrupted",
                    finished_at=utc_now(),
                    updated_at=utc_now(),
                )
                changed = True
        if changed:
            self._save()

    def _atomic_json(self, path: Path, payload: Any) -> None:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temp_path = Path(handle.name)
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)

    def _save(self) -> None:
        self._atomic_json(self.operations_path, self.operations)

    def create(self, operation_id: str, *, kind: str, request: dict[str, Any]) -> dict:
        operation = {
            "operation_id": operation_id,
            "kind": kind,
            "status": OperationStatus.QUEUED,
            "stage": "queued",
            "request": request,
            "started_at": utc_now(),
            "updated_at": utc_now(),
            "finished_at": None,
            "error_code": None,
        }
        self.operations[operation_id] = operation
        self._save()
        return dict(operation)

    def update(self, operation_id: str, **changes: Any) -> dict:
        operation = self.operations[operation_id]
        operation.update(changes, updated_at=utc_now())
        if operation.get("status") in {
            str(status) for status in TERMINAL_OPERATION_STATUSES
        } and not operation.get("finished_at"):
            operation["finished_at"] = utc_now()
        self._save()
        return dict(operation)

    def get(self, operation_id: str) -> dict | None:
        operation = self.operations.get(operation_id)
        return dict(operation) if operation else None

    def active(self) -> dict | None:
        terminals = {str(status) for status in TERMINAL_OPERATION_STATUSES}
        for operation in reversed(list(self.operations.values())):
            if operation.get("status") not in terminals:
                return dict(operation)
        return None

    def save_snapshot(self, payload: dict[str, Any]) -> None:
        self._atomic_json(self.snapshot_path, payload)

    def load_snapshot(self) -> dict[str, Any] | None:
        if not self.snapshot_path.exists():
            return None
        return json.loads(self.snapshot_path.read_text(encoding="utf-8"))
