from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

import yaml


STATE_VERSION = 1
OPERATION_STATUSES = {"in_progress", "succeeded", "failed", "rolled_back"}
SAFE_OPERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")


class StateDriftError(RuntimeError):
    """Raised when live, local-ledger, and catalog facts do not converge."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_lan_aio_state_dir(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    values = os.environ if environ is None else environ
    xdg_state_home = str(values.get("XDG_STATE_HOME") or "").strip()
    if xdg_state_home:
        root = Path(xdg_state_home).expanduser()
    else:
        root = (home or Path.home()) / ".local" / "state"
    return root / "allbot" / "lan-aio"


def catalog_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assess_state_drift(
    *,
    live_current: Mapping[str, str | None],
    ledger: Mapping[str, Any] | None,
    catalog_slot_ids: set[str],
    catalog_sha256: str,
    live_errors: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    drift: list[dict[str, Any]] = []
    errors = live_errors or {}
    if ledger is None:
        drift.append({"physical_slot": None, "kind": "ledger_missing"})
        ledger_slots: Mapping[str, Any] = {}
        ledger_catalog_sha256 = None
    else:
        ledger_slots = ledger.get("physical_slots") or {}
        ledger_catalog_sha256 = ledger.get("catalog_sha256")
    if ledger_catalog_sha256 and ledger_catalog_sha256 != catalog_sha256:
        drift.append(
            {
                "physical_slot": None,
                "kind": "catalog_revision_mismatch",
                "ledger_catalog_sha256": ledger_catalog_sha256,
                "catalog_sha256": catalog_sha256,
            }
        )

    physical_slots = sorted(set(live_current) | set(ledger_slots))
    for physical_slot in physical_slots:
        current = ledger_slots.get(physical_slot) or {}
        ledger_slot = (current.get("current") or {}).get("slot_id")
        live_slot = live_current.get(physical_slot)
        if physical_slot in errors:
            drift.append(
                {
                    "physical_slot": physical_slot,
                    "kind": "live_unavailable",
                    "error": errors[physical_slot],
                }
            )
            continue
        if ledger_slot and ledger_slot not in catalog_slot_ids:
            drift.append(
                {
                    "physical_slot": physical_slot,
                    "kind": "ledger_slot_not_in_catalog",
                    "ledger_slot": ledger_slot,
                }
            )
            continue
        if not ledger_slot:
            drift.append(
                {
                    "physical_slot": physical_slot,
                    "kind": "ledger_current_missing",
                    "live_slot": live_slot,
                }
            )
            continue
        if not live_slot:
            drift.append(
                {
                    "physical_slot": physical_slot,
                    "kind": "live_current_missing",
                    "ledger_slot": ledger_slot,
                }
            )
            continue
        if live_slot != ledger_slot:
            drift.append(
                {
                    "physical_slot": physical_slot,
                    "kind": "live_ledger_mismatch",
                    "live_slot": live_slot,
                    "ledger_slot": ledger_slot,
                }
            )

    return {
        "status": "blocked" if drift else "passed",
        "drift": drift,
        "live_current": dict(live_current),
        "ledger_current": {
            physical_slot: (value.get("current") or {}).get("slot_id")
            for physical_slot, value in ledger_slots.items()
        },
        "catalog_sha256": catalog_sha256,
    }


class LanAioStateStore:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.state_dir = state_dir or default_lan_aio_state_dir()
        self.current_path = self.state_dir / "current.yml"
        self.history_dir = self.state_dir / "history"
        self.lock_path = self.state_dir / "mutation.lock"

    def _ensure_directories(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.history_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.state_dir, 0o700)
        os.chmod(self.history_dir, 0o700)

    @staticmethod
    def _validate_operation_id(operation_id: str) -> None:
        if not SAFE_OPERATION_ID.fullmatch(operation_id):
            raise ValueError(f"invalid LAN AIO operation id: {operation_id!r}")

    def _history_path(self, operation_id: str) -> Path:
        self._validate_operation_id(operation_id)
        return self.history_dir / f"{operation_id}.json"

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file_obj:
                temp_path = Path(file_obj.name)
                os.chmod(temp_path, 0o600)
                file_obj.write(content)
                file_obj.flush()
                os.fsync(file_obj.fileno())
            os.replace(temp_path, path)
            temp_path = None
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def load_current(self) -> dict[str, Any] | None:
        if not self.current_path.exists():
            return None
        payload = yaml.safe_load(self.current_path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict) or payload.get("version") != STATE_VERSION:
            raise RuntimeError(
                f"unsupported LAN AIO current state: {self.current_path}"
            )
        return payload

    def write_current(
        self,
        payload: Mapping[str, Any],
        *,
        operation_id: str,
    ) -> dict[str, Any]:
        self._validate_operation_id(operation_id)
        current = dict(payload)
        current["version"] = STATE_VERSION
        current["updated_at"] = _utc_now()
        current["last_operation_id"] = operation_id
        current.setdefault("physical_slots", {})
        self._ensure_directories()
        self._atomic_write(
            self.current_path,
            yaml.safe_dump(current, allow_unicode=True, sort_keys=False),
        )
        return current

    def begin_operation(
        self,
        operation_id: str,
        *,
        action: str,
        physical_slots: list[str],
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._ensure_directories()
        history_path = self._history_path(operation_id)
        if history_path.exists():
            raise RuntimeError(f"LAN AIO operation already exists: {operation_id}")
        payload = {
            "version": STATE_VERSION,
            "operation_id": operation_id,
            "action": action,
            "physical_slots": sorted(set(physical_slots)),
            "status": "in_progress",
            "started_at": _utc_now(),
            "request": dict(request),
        }
        self._atomic_write(
            history_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        )
        return payload

    def finish_operation(
        self,
        operation_id: str,
        *,
        status: str,
        result: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        if status not in OPERATION_STATUSES - {"in_progress"}:
            raise ValueError(f"invalid LAN AIO operation status: {status}")
        history_path = self._history_path(operation_id)
        if not history_path.exists():
            raise RuntimeError(f"LAN AIO operation does not exist: {operation_id}")
        payload = json.loads(history_path.read_text(encoding="utf-8"))
        if payload.get("status") != "in_progress":
            raise RuntimeError(
                f"LAN AIO operation is already finalized: {operation_id}"
            )
        payload["status"] = status
        payload["finished_at"] = _utc_now()
        if result is not None:
            payload["result"] = dict(result)
        if error:
            payload["error"] = error
        self._atomic_write(
            history_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        )
        return payload

    def unfinished_operations(self) -> list[str]:
        if not self.history_dir.exists():
            return []
        unfinished = []
        for path in sorted(self.history_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                unfinished.append(path.stem)
                continue
            if payload.get("status") == "in_progress":
                unfinished.append(path.stem)
        return unfinished

    @contextmanager
    def mutation_lock(self) -> Iterator[None]:
        self._ensure_directories()
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            os.chmod(self.lock_path, 0o600)
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("another LAN AIO mutation is in progress") from exc
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def assert_mutation_allowed(report: Mapping[str, Any]) -> None:
        if report.get("status") == "passed":
            return
        kinds = ", ".join(
            str(item.get("kind") or "unknown") for item in report.get("drift") or []
        )
        raise StateDriftError(f"LAN AIO mutation blocked by state drift: {kinds}")

    def migrate_legacy_state(
        self,
        legacy: Mapping[str, Any],
        *,
        catalog_sha256: str,
        operation_id: str,
    ) -> dict[str, Any]:
        physical_slots: dict[str, Any] = {}
        for node_id, node in (legacy.get("nodes") or {}).items():
            for physical_gpu in node.get("physical_gpus") or []:
                gpu_index = int(physical_gpu["gpu_index"])
                physical_slot = f"{node_id}:gpu{gpu_index}"
                current = dict(physical_gpu.get("current") or {})
                physical_slots[physical_slot] = {
                    "current": current,
                    "cached_profiles": list(physical_gpu.get("cached_profiles") or []),
                    "blocked_observations": list(
                        physical_gpu.get("blocked_profiles") or []
                    ),
                    "last_verified_at": current.get("last_verified_at"),
                }
        self.begin_operation(
            operation_id,
            action="state-init",
            physical_slots=list(physical_slots),
            request={"source": "legacy_git_state"},
        )
        current = self.write_current(
            {
                "catalog_sha256": catalog_sha256,
                "physical_slots": physical_slots,
            },
            operation_id=operation_id,
        )
        self.finish_operation(
            operation_id,
            status="succeeded",
            result={"migrated_physical_slots": sorted(physical_slots)},
        )
        return current
