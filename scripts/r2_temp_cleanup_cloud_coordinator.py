#!/usr/bin/env python3
"""Persistently coordinate exact-plan R2 duplicate cleanup on the cloud host."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

from scripts.r2_temp_cleanup import (
    DEFAULT_MAX_DELETE_BYTES,
    PRODUCTION_BUCKET,
    _r2_client,
    resume_delete_started,
    run as cleanup_run,
    select_duplicate_candidates,
)
from scripts.refresh_r2_temp_cleanup_inventory import refresh_inventory


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def remove_inventory_keys(path: Path, keys: list[str]) -> tuple[int, int, str]:
    if len(keys) != len(set(keys)):
        raise RuntimeError("cleanup rowset contains duplicate keys")
    connection = sqlite3.connect(path)
    try:
        connection.execute("begin immediate")
        before = int(connection.execute("select count(*) from objects").fetchone()[0])
        connection.executemany("delete from objects where key=?", ((key,) for key in keys))
        after = int(connection.execute("select count(*) from objects").fetchone()[0])
        if before - after != len(keys):
            raise RuntimeError("cleanup rowset does not match working inventory")
        connection.commit()
        if str(connection.execute("pragma integrity_check").fetchone()[0]) != "ok":
            raise RuntimeError("working inventory integrity check failed")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    os.chmod(path, 0o600)
    return len(keys), after, file_sha256(path)


class CloudCleanupCoordinator:
    def __init__(
        self,
        *,
        state_root: Path,
        authorization_path: Path,
        refresh_inventory_func: Callable[[Path], dict[str, Any]] | None = None,
        cleanup_run_func: Callable[[SimpleNamespace], Awaitable[dict]] = cleanup_run,
        verification_concurrency: int = 8,
    ) -> None:
        self.state_root = state_root
        self.authorization_path = authorization_path
        self.state_path = state_root / "chain-state.json"
        self.working_inventory = state_root / "working-inventory.sqlite3"
        self.cleanup_run = cleanup_run_func
        self.verification_concurrency = min(16, max(1, verification_concurrency))
        self.refresh_inventory_func = refresh_inventory_func or self._refresh_inventory

    @staticmethod
    def _refresh_inventory(state_root: Path) -> dict[str, Any]:
        client = _r2_client()
        try:
            return refresh_inventory(state_root=state_root, client=client)
        finally:
            client.close()

    def validate_authorization(self) -> None:
        path = self.authorization_path
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise RuntimeError("private umbrella authorization receipt is missing")
        document = json.loads(path.read_text(encoding="utf-8"))
        if (
            document.get("bucket") != PRODUCTION_BUCKET
            or document.get("delegates_exact_child_phase_tokens") is not True
            or document.get("scope_expansion_allowed") is not False
        ):
            raise RuntimeError("umbrella authorization does not cover this cleanup")

    def _fresh_pass(self, *, number: int) -> dict[str, Any]:
        refreshed = self.refresh_inventory_func(self.state_root)
        source = Path(str(refreshed["path"]))
        if file_sha256(source) != str(refreshed["sha256"]):
            raise RuntimeError("refreshed inventory SHA-256 does not match receipt")
        shutil.copy2(source, self.working_inventory)
        os.chmod(self.working_inventory, 0o600)
        working_sha = file_sha256(self.working_inventory)
        return {
            "number": number,
            "source_inventory": str(source),
            "source_inventory_sha256": str(refreshed["sha256"]),
            "working_inventory_sha256": working_sha,
            "deleted_count": 0,
            "deleted_bytes": 0,
            "deferred_count": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    def _initial_state(self) -> dict[str, Any]:
        current_pass = self._fresh_pass(number=1)
        state = {
            "schema": "allbot-r2-temp-cleanup-cloud-chain/v1",
            "bucket": PRODUCTION_BUCKET,
            "authorization_receipt": str(self.authorization_path),
            "working_inventory": str(self.working_inventory),
            "current_inventory_sha256": current_pass["working_inventory_sha256"],
            "next_sequence": 0,
            "pending": None,
            "completed": [],
            "passes": [],
            "current_pass": current_pass,
            "finished": False,
        }
        atomic_private_json(self.state_path, state)
        return state

    @staticmethod
    def _stage(state: dict[str, Any]) -> int:
        completed = len(state.get("completed") or [])
        return 100 if completed == 0 else 1000 if completed == 1 else 10_000

    def _args(self, *, output: Path, limit: int) -> SimpleNamespace:
        return SimpleNamespace(
            inventory=str(self.working_inventory),
            output=str(output),
            bucket=PRODUCTION_BUCKET,
            limit=limit,
            min_age_hours=24,
            verification_concurrency=self.verification_concurrency,
            max_delete_bytes=DEFAULT_MAX_DELETE_BYTES,
            execute=False,
            approved_plan="",
            plan_sha256="",
            confirm="",
        )

    def _reconcile_completed(self, state: dict[str, Any], receipt: dict) -> None:
        pending = state["pending"]
        objects = list(receipt.get("objects") or [])
        if receipt.get("status") != "completed":
            raise RuntimeError("cleanup receipt is not completed")
        if int(receipt.get("post_delete_verified_count", -1)) != len(objects):
            raise RuntimeError("cleanup receipt post-delete verification is incomplete")
        if file_sha256(self.working_inventory) != pending["inventory_sha256_before"]:
            raise RuntimeError("working inventory changed while a batch was pending")
        removed, remaining, after_sha = remove_inventory_keys(
            self.working_inventory, [str(item["key"]) for item in objects]
        )
        receipt_path = Path(str(pending["receipt"]))
        state["completed"].append(
            {
                "sequence": int(pending["sequence"]),
                "stage": int(pending["stage"]),
                "plan": str(pending["plan"]),
                "plan_sha256": str(pending["plan_sha256"]),
                "receipt": str(receipt_path),
                "receipt_sha256": file_sha256(receipt_path),
                "deleted_count": removed,
                "deleted_bytes": int(receipt.get("delete_bytes") or 0),
                "inventory_object_count_after": remaining,
                "inventory_sha256_after": after_sha,
            }
        )
        current_pass = state["current_pass"]
        current_pass["deleted_count"] += removed
        current_pass["deleted_bytes"] += int(receipt.get("delete_bytes") or 0)
        state["current_inventory_sha256"] = after_sha
        state["next_sequence"] = int(pending["sequence"]) + 1
        state["pending"] = None
        atomic_private_json(self.state_path, state)

    def _reconcile_probe_failed(self, state: dict[str, Any], receipt: dict) -> None:
        """Defer exact pre-delete probe failures without deleting any R2 object."""
        pending = state["pending"]
        if (
            receipt.get("status") != "probe_failed"
            or receipt.get("mode") != "execute"
            or receipt.get("approved_plan_sha256") != pending["plan_sha256"]
            or int(receipt.get("delete_count", -1)) != 0
            or list(receipt.get("objects") or [])
            or "post_delete_verified_count" in receipt
        ):
            raise RuntimeError("probe-failed receipt is not a zero-delete receipt")
        failures = list(receipt.get("probe_failures") or [])
        failure_keys = [str(item.get("key") or "") for item in failures]
        if not failure_keys or any(not key for key in failure_keys):
            raise RuntimeError("probe-failed receipt has no exact failure rowset")
        if len(failure_keys) != len(set(failure_keys)):
            raise RuntimeError("probe-failed receipt contains duplicate keys")
        plan = json.loads(Path(str(pending["plan"])).read_text(encoding="utf-8"))
        plan_keys = {str(item.get("key") or "") for item in plan.get("objects") or []}
        if not set(failure_keys).issubset(plan_keys):
            raise RuntimeError("probe-failed rowset is outside the frozen plan")
        if file_sha256(self.working_inventory) != pending["inventory_sha256_before"]:
            raise RuntimeError("working inventory changed while a batch was pending")
        removed, remaining, after_sha = remove_inventory_keys(
            self.working_inventory, failure_keys
        )
        receipt_path = Path(str(pending["receipt"]))
        state.setdefault("deferred", []).append(
            {
                "sequence": int(pending["sequence"]),
                "stage": int(pending["stage"]),
                "plan": str(pending["plan"]),
                "plan_sha256": str(pending["plan_sha256"]),
                "receipt": str(receipt_path),
                "receipt_sha256": file_sha256(receipt_path),
                "deferred_count": removed,
                "reason": "execute_probe_failed",
                "inventory_object_count_after": remaining,
                "inventory_sha256_after": after_sha,
            }
        )
        state["current_pass"]["deferred_count"] += removed
        state["current_inventory_sha256"] = after_sha
        state["next_sequence"] = int(pending["sequence"]) + 1
        state["pending"] = None
        atomic_private_json(self.state_path, state)

    async def _reconcile_pending(self, state: dict[str, Any]) -> None:
        pending = state.get("pending")
        if not isinstance(pending, dict):
            return
        plan_path = Path(str(pending["plan"]))
        receipt_path = Path(str(pending["receipt"]))
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if not receipt_path.exists():
            args = self._args(output=receipt_path, limit=int(pending["stage"]))
            args.execute = True
            args.approved_plan = str(plan_path)
            args.plan_sha256 = str(pending["plan_sha256"])
            args.confirm = (
                f"DELETE_VERIFIED_TEMP_R2_{PRODUCTION_BUCKET}:{args.plan_sha256}"
            )
            receipt = await self.cleanup_run(args)
        else:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("status") == "delete_started":
                client = _r2_client()
                try:
                    receipt = await resume_delete_started(
                        client=client,
                        plan=plan,
                        receipt=receipt,
                        concurrency=self.verification_concurrency,
                    )
                finally:
                    client.close()
                atomic_private_json(receipt_path, receipt)
        if receipt.get("status") == "probe_failed":
            self._reconcile_probe_failed(state, receipt)
        else:
            self._reconcile_completed(state, receipt)

    def _defer_blocked_frontier(self, state: dict[str, Any], plan: dict) -> None:
        connection = sqlite3.connect(self.working_inventory)
        try:
            candidates = select_duplicate_candidates(
                connection,
                cutoff=str(plan["cutoff"]),
                limit=int(plan["candidate_count"]),
            )
        finally:
            connection.close()
        if len(candidates) != int(plan["candidate_count"]):
            raise RuntimeError("blocked frontier no longer matches frozen plan")
        removed, _remaining, after_sha = remove_inventory_keys(
            self.working_inventory, [item.key for item in candidates]
        )
        state["current_pass"]["deferred_count"] += removed
        state["current_inventory_sha256"] = after_sha
        atomic_private_json(self.state_path, state)

    def _complete_pass_or_finish(self, state: dict[str, Any]) -> None:
        current_pass = state["current_pass"]
        current_pass["completed_at"] = datetime.now(timezone.utc).isoformat()
        state["passes"].append(dict(current_pass))
        if int(current_pass["deleted_count"]) == 0:
            state["finished"] = True
            state["finished_at"] = datetime.now(timezone.utc).isoformat()
            state["finish_reason"] = "fresh_full_pass_deleted_zero"
            state["current_pass"] = None
        else:
            next_pass = self._fresh_pass(number=int(current_pass["number"]) + 1)
            state["current_pass"] = next_pass
            state["current_inventory_sha256"] = next_pass[
                "working_inventory_sha256"
            ]
        atomic_private_json(self.state_path, state)

    async def run_one_step(self, state: dict[str, Any]) -> None:
        await self._reconcile_pending(state)
        if state.get("finished"):
            return
        sequence = int(state["next_sequence"])
        stage = self._stage(state)
        plan_path = self.state_root / f"plan-{sequence:06d}-{stage}.json"
        receipt_path = self.state_root / f"execute-{sequence:06d}-{stage}.json"
        args = self._args(output=plan_path, limit=stage)
        plan = await self.cleanup_run(args)
        if plan.get("mode") != "dry-run" or not plan.get("plan_sha256"):
            raise RuntimeError("cleanup plan is invalid")
        if plan.get("probe_failures") and int(plan.get("delete_count") or 0) > 0:
            raise RuntimeError("mixed successful and failed probes cannot be executed")
        delete_count = int(plan.get("delete_count") or 0)
        candidate_count = int(plan.get("candidate_count") or 0)
        if delete_count == 0:
            if candidate_count:
                self._defer_blocked_frontier(state, plan)
            else:
                self._complete_pass_or_finish(state)
            return
        before_sha = file_sha256(self.working_inventory)
        if before_sha != state["current_inventory_sha256"]:
            raise RuntimeError("working inventory identity changed before execution")
        state["pending"] = {
            "sequence": sequence,
            "stage": stage,
            "plan": str(plan_path),
            "plan_sha256": str(plan["plan_sha256"]),
            "receipt": str(receipt_path),
            "inventory_sha256_before": before_sha,
        }
        atomic_private_json(self.state_path, state)
        await self._reconcile_pending(state)

    async def run_until_complete(self, *, max_steps: int = 0) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.state_root, 0o700)
        self.validate_authorization()
        state = (
            json.loads(self.state_path.read_text(encoding="utf-8"))
            if self.state_path.is_file()
            else self._initial_state()
        )
        steps = 0
        while not state.get("finished"):
            if max_steps and steps >= max_steps:
                return
            await self.run_one_step(state)
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            steps += 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--state-root",
        default=os.getenv(
            "R2_TEMP_CLEANUP_STATE_ROOT", "/var/lib/allbot-r2-temp-cleanup"
        ),
    )
    parser.add_argument(
        "--authorization",
        default=os.getenv(
            "R2_TEMP_CLEANUP_AUTHORIZATION",
            "/var/lib/allbot-r2-temp-cleanup/authorization-receipt.json",
        ),
    )
    parser.add_argument("--max-steps", type=int, default=0)
    args = parser.parse_args()
    state_root = Path(args.state_root)
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = state_root / "coordinator.lock"
    lock = lock_path.open("a+")
    os.chmod(lock_path, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    coordinator = CloudCleanupCoordinator(
        state_root=state_root,
        authorization_path=Path(args.authorization),
        verification_concurrency=int(
            os.getenv("R2_TEMP_CLEANUP_VERIFICATION_CONCURRENCY", "8")
        ),
    )
    backoff = 60
    while True:
        try:
            asyncio.run(coordinator.run_until_complete(max_steps=args.max_steps))
            return
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "at": datetime.now(timezone.utc).isoformat(),
                        "event": "retry_scheduled",
                        "error_type": type(exc).__name__,
                        "delay_seconds": backoff,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            time.sleep(backoff)
            backoff = min(900, backoff * 2)


if __name__ == "__main__":
    main()
