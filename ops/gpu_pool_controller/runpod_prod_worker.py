from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .providers.runpod import (
    RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF,
    RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF,
    RUNPOD_PROD_AGENT_ID,
    RUNPOD_PROD_AGENT_ID_PREFIX,
    RUNPOD_PROD_BUCKET,
    RUNPOD_PROD_POD_NAME_PREFIX,
    RUNPOD_PROD_SUPPORTED_TASK_TYPES,
    RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
    RunPodProvider,
    prod_agent_id_from_slot,
    prod_pod_name_from_agent_id,
    prod_slot_from_agent_id,
    redact_payload,
    redact_text,
)
from .runpod_canary import result_url_path, write_canary_png


PROD_ENVIRONMENT = "cloud-prod"
PROD_TASK_TYPE = "img2img"
PROD_CONTROL_HOST = "100.107.220.127"
PROD_WORKER_CENTRAL_PORT = 8003
PROD_WEB_API_PORT = 8000
PROD_MODEL_BUCKET = "allbot-model-cache"
PROD_MODEL_PREFIX = "img2img_lora/2026-06-10"
PROD_MODEL_MANIFEST_KEY = "img2img_lora/2026-06-10/manifest.json"
HEALTHY_WORKER_STATUSES = {"idle", "running"}
TERMINAL_TASK_STATUSES = {"done", "error", "cancelled"}


class RunPodProdWorkerError(ValueError):
    pass


@dataclass(frozen=True)
class RunPodProdWorkerOptions:
    action: str = "status"
    execute: bool = False
    task_type: str = PROD_TASK_TYPE
    environment: str = PROD_ENVIRONMENT
    agent_id: str = RUNPOD_PROD_AGENT_ID
    desired_count: int | None = None
    central_url: str = ""
    web_api_url: str = ""
    web_user_id: int = 3
    web_pwd_ver: int = 1
    web_bearer_token: str = ""
    agent_token: str = ""
    input_object_key: str = ""
    output_dir: Path = Path("/tmp/allbot_runpod_prod_worker")
    download_results_dir: Path = Path("runpod_canary_results/prod")
    readiness_timeout_seconds: float = 900.0
    worker_timeout_seconds: float = 600.0
    drain_timeout_seconds: float = 300.0
    task_timeout_seconds: float = 1800.0
    poll_interval_seconds: float = 10.0
    task_poll_interval_seconds: float = 5.0
    prompt: str = "clean production canary image transform, natural lighting, high quality"
    negative_prompt: str = "low quality, artifacts, text, watermark"
    quiet: bool = False


def load_env_file_for_prod_worker(
    path: Path | None,
    *,
    override: bool = False,
    protect_existing_prefixes: tuple[str, ...] = (),
) -> dict[str, Any]:
    if path is None:
        return {"loaded": False, "path": None, "override": override, "count": 0}
    if not path.exists():
        raise RunPodProdWorkerError(f"env file not found: {path}")
    values = _dotenv_values(path)
    loaded = 0
    for key, value in values.items():
        if not key or value is None:
            continue
        if key in os.environ:
            if not override:
                continue
            if any(key.startswith(prefix) for prefix in protect_existing_prefixes):
                continue
        os.environ[key] = str(value)
        loaded += 1
    return {
        "loaded": True,
        "path": str(path),
        "override": override,
        "protected_existing_prefixes": list(protect_existing_prefixes),
        "count": loaded,
    }


def apply_prod_worker_selection_to_env(args: Any) -> dict[str, str]:
    agent_id = prod_worker_agent_id_from_args_env(args)
    os.environ["RUNPOD_PROD_AGENT_ID"] = agent_id
    return {
        "agent_id": agent_id,
        "slot": prod_slot_from_agent_id(agent_id),
        "pod_name": prod_pod_name_from_agent_id(agent_id),
    }


def prod_worker_agent_id_from_args_env(args: Any) -> str:
    explicit_agent_id = (
        getattr(args, "agent_id", None)
        or os.getenv("RUNPOD_PROD_WORKER_AGENT_ID")
        or ""
    ).strip()
    explicit_slot = (
        str(getattr(args, "slot", "") or os.getenv("RUNPOD_PROD_WORKER_SLOT") or "")
    ).strip()
    if explicit_agent_id:
        prod_slot_from_agent_id(explicit_agent_id)
        if explicit_slot:
            slot_agent_id = prod_agent_id_from_slot(explicit_slot)
            if slot_agent_id != explicit_agent_id:
                raise RunPodProdWorkerError(
                    "--slot and --agent-id refer to different prod RunPod workers"
                )
        return explicit_agent_id
    if explicit_slot:
        return prod_agent_id_from_slot(explicit_slot)
    agent_id = os.getenv("RUNPOD_PROD_AGENT_ID", RUNPOD_PROD_AGENT_ID)
    prod_slot_from_agent_id(agent_id)
    return agent_id


def options_from_args_env(args: Any) -> RunPodProdWorkerOptions:
    control_host = (
        os.getenv("RUNPOD_PROD_WORKER_CONTROL_HOST")
        or os.getenv("CLOUD_PROD_TAILSCALE_IP")
        or PROD_CONTROL_HOST
    )
    agent_id = prod_worker_agent_id_from_args_env(args)
    default_download_dir = (
        Path("runpod_canary_results")
        / "prod"
        / datetime.now(timezone.utc).strftime("%Y%m%d")
    )
    return RunPodProdWorkerOptions(
        action=str(
            getattr(args, "prod_worker_command", "")
            or getattr(args, "action", "")
            or "status"
        ),
        execute=bool(getattr(args, "execute", False)),
        agent_id=agent_id,
        desired_count=getattr(args, "desired", None),
        central_url=(
            getattr(args, "central_url", None)
            or os.getenv("RUNPOD_PROD_WORKER_CENTRAL_URL")
            or f"http://{control_host}:{PROD_WORKER_CENTRAL_PORT}"
        ).rstrip("/"),
        web_api_url=(
            getattr(args, "web_api_url", None)
            or os.getenv("RUNPOD_PROD_WORKER_WEB_API_URL")
            or f"http://{control_host}:{PROD_WEB_API_PORT}/api"
        ).rstrip("/"),
        web_user_id=int(
            getattr(args, "web_user_id", None)
            or os.getenv("RUNPOD_PROD_WORKER_WEB_USER_ID")
            or "3"
        ),
        web_pwd_ver=int(
            getattr(args, "web_pwd_ver", None)
            or os.getenv("RUNPOD_PROD_WORKER_WEB_PWD_VER")
            or "1"
        ),
        web_bearer_token=os.getenv("RUNPOD_PROD_WORKER_WEB_BEARER_TOKEN", ""),
        agent_token=(
            os.getenv("RUNPOD_PROD_WORKER_AGENT_TOKEN")
            or os.getenv("AGENT_SECRET_TOKEN")
            or ""
        ),
        input_object_key=(
            getattr(args, "input_object_key", None)
            or os.getenv("RUNPOD_PROD_WORKER_INPUT_OBJECT_KEY")
            or ""
        ),
        output_dir=Path(
            getattr(args, "output_dir", None)
            or os.getenv("RUNPOD_PROD_WORKER_OUTPUT_DIR")
            or "/tmp/allbot_runpod_prod_worker"
        ),
        download_results_dir=Path(
            getattr(args, "download_results_dir", None)
            or os.getenv("RUNPOD_PROD_WORKER_DOWNLOAD_RESULTS_DIR")
            or default_download_dir
        ),
        readiness_timeout_seconds=float(getattr(args, "readiness_timeout", 900.0)),
        worker_timeout_seconds=float(getattr(args, "worker_timeout", 600.0)),
        drain_timeout_seconds=float(getattr(args, "drain_timeout", 300.0)),
        task_timeout_seconds=float(getattr(args, "task_timeout", 1800.0)),
        poll_interval_seconds=float(getattr(args, "poll_interval", 10.0)),
        task_poll_interval_seconds=float(getattr(args, "task_poll_interval", 5.0)),
        prompt=(
            getattr(args, "prompt", None)
            or os.getenv("RUNPOD_PROD_WORKER_PROMPT")
            or RunPodProdWorkerOptions.prompt
        ),
        negative_prompt=(
            getattr(args, "negative_prompt", None)
            or os.getenv("RUNPOD_PROD_WORKER_NEGATIVE_PROMPT")
            or RunPodProdWorkerOptions.negative_prompt
        ),
        quiet=bool(getattr(args, "quiet", False)),
    )


class RunPodProdWorkerRunner:
    def __init__(
        self,
        provider: RunPodProvider,
        options: RunPodProdWorkerOptions,
        *,
        sleep_func: Callable[[float], None] = time.sleep,
        emit_func: Callable[[str], None] | None = None,
    ) -> None:
        self.provider = provider
        self.options = options
        self._sleep = sleep_func
        self._emit_func = emit_func or (lambda message: print(message, file=sys.stderr))

    def run(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "ok": False,
            "action": self.options.action,
            "execute": self.options.execute,
            "environment": self.options.environment,
            "agent_id": self.options.agent_id,
            "started_at": _utc_now_iso(),
            "phases": [],
        }
        try:
            self._validate_static_options()
            action = self.options.action.replace("-", "_")
            if action == "render":
                self._run_render(summary)
            elif action == "up":
                self._run_up(summary)
            elif action == "status":
                self._run_status(summary)
            elif action == "enable":
                self._run_control(summary, state="enabled")
            elif action == "disable":
                self._run_control(summary, state="disabled")
            elif action == "down":
                self._run_down(summary)
            elif action == "canary":
                self._run_canary(summary)
            elif action == "scale":
                self._run_scale(summary)
            else:
                raise RunPodProdWorkerError(f"unsupported prod-worker action: {self.options.action}")
            summary.setdefault("ok", True)
        except Exception as exc:
            summary["ok"] = False
            summary["error"] = redact_text(str(exc))
        return self._finish(summary)

    def _validate_static_options(self) -> None:
        if self.options.environment != PROD_ENVIRONMENT:
            raise RunPodProdWorkerError("prod-worker only supports environment=cloud-prod")
        if self.options.task_type != PROD_TASK_TYPE:
            raise RunPodProdWorkerError("prod-worker only supports task_type=img2img")
        prod_slot_from_agent_id(
            self.options.agent_id,
            max_manual_slots=self.provider.settings.prod_max_manual_slots,
        )
        if self.options.agent_id != self.provider.settings.prod_agent_id:
            raise RunPodProdWorkerError(
                "prod-worker agent_id must match provider RUNPOD_PROD_AGENT_ID "
                f"({self.provider.settings.prod_agent_id})"
            )

    def _run_render(self, summary: dict[str, Any]) -> None:
        self._phase(summary, "render", "running")
        render = self._render(redact=False)
        summary["render"] = self._render_summary(render)
        summary["request"] = redact_payload(render)
        self._phase(summary, "render", "ok", summary["render"])
        summary["ok"] = True

    def _run_up(self, summary: dict[str, Any]) -> None:
        self._run_preflight(summary)
        if not self.options.execute:
            summary["ok"] = True
            summary["would_execute"] = [
                f"set Central control for {self.options.agent_id} to disabled",
                "create one cloud-prod RunPod pod from the GHCR baked image",
                "wait for RunPod infrastructure readiness",
                "wait for prod Central heartbeat while control remains disabled",
            ]
            return
        self._require_runpod_mutation_gates()
        self._require_agent_token()
        self._set_agent_control("disabled", reason="runpod_prod_worker_up")
        create_payload = self.provider.create_pod(
            task_type=self.options.task_type,
            environment=self.options.environment,
            execute=True,
        )
        self._require_ok(create_payload, "runpod create-pod failed")
        pod_id = _extract_pod_id(create_payload)
        summary["pod"] = _pod_summary(create_payload, summary.get("render", {}).get("imageName", ""))
        self._phase(summary, "runpod_create_pod", "ok", {"pod_id": pod_id})
        self._wait_pod_readiness(pod_id, summary)
        worker = self._wait_prod_worker(summary, require_disabled=True)
        summary["worker"] = _worker_summary(worker)
        summary["ok"] = True

    def _run_status(self, summary: dict[str, Any]) -> None:
        self._phase(summary, "status", "running")
        status = self._status_snapshot()
        summary.update(status)
        self._phase(
            summary,
            "status",
            "ok" if status.get("ok") else "error",
            {
                "prod_pod_count": status.get("prod_pod_count"),
                "worker_seen": bool(status.get("worker")),
                "control_state": (status.get("control") or {}).get("state"),
            },
        )
        summary["ok"] = bool(status.get("ok"))

    def _run_control(self, summary: dict[str, Any], *, state: str) -> None:
        self._phase(summary, f"control_{state}", "running")
        if not self.options.execute:
            summary["ok"] = True
            summary["would_execute"] = [
                f"set Central control for {self.options.agent_id} to {state}",
            ]
            return
        self._require_agent_token()
        payload = self._set_agent_control(state, reason=f"runpod_prod_worker_{state}")
        summary["control"] = payload
        self._phase(summary, f"control_{state}", "ok", payload)
        summary["ok"] = True

    def _run_down(self, summary: dict[str, Any]) -> None:
        self._run_preflight(summary, allow_existing_prod_pod=True)
        if not self.options.execute:
            summary["ok"] = True
            summary["would_execute"] = [
                f"set Central control for {self.options.agent_id} to disabled",
                "wait until the prod RunPod worker has no current_task_id",
                "delete the prod RunPod pod if exactly one managed prod pod exists",
                "list and reconcile managed RunPod pods after deletion",
            ]
            return
        self._require_runpod_mutation_gates()
        self._require_agent_token()
        self._set_agent_control("disabled", reason="runpod_prod_worker_down")
        worker = self._wait_worker_drained(summary)
        if worker:
            summary["worker"] = _worker_summary(worker)
        pod = self._single_prod_pod(summary)
        if pod is None:
            summary["pod_delete"] = {"skipped": True, "reason": "prod pod not found"}
            summary["ok"] = True
            return
        pod_id = str(pod.get("id") or pod.get("podId") or "")
        if not pod_id:
            raise RunPodProdWorkerError("managed prod pod did not include an id")
        delete_payload = self.provider.delete_pod(
            pod_id=pod_id,
            task_type=self.options.task_type,
            execute=True,
        )
        self._require_ok(delete_payload, "runpod delete-pod failed")
        summary["pod_delete"] = {"pod_id": pod_id, "ok": True}
        self._phase(summary, "runpod_delete_pod", "ok", {"pod_id": pod_id})
        listed = self.provider.list_pods(managed_only=True)
        reconcile = self.provider.reconcile_managed_pods()
        summary["post_cleanup"] = {
            "list_pods": {"ok": listed.get("ok"), "count": listed.get("count")},
            "reconcile": {
                "ok": reconcile.get("ok"),
                "managed_count": reconcile.get("managed_count"),
                "orphans": reconcile.get("orphans", []),
            },
        }
        summary["ok"] = bool(listed.get("ok") and reconcile.get("ok"))

    def _run_canary(self, summary: dict[str, Any]) -> None:
        if not self.options.execute:
            summary["ok"] = True
            summary["would_execute"] = [
                f"verify {self.options.agent_id} heartbeat in prod Central",
                f"temporarily set {self.options.agent_id} control to enabled",
                "upload or reuse one non-sensitive 512x512 PNG in user-data-prod",
                "submit one prod Web img2img task as internal user_id=3",
                "download the result to runpod_canary_results/prod/<date>/",
                f"restore {self.options.agent_id} control to disabled",
            ]
            return
        self._require_agent_token()
        self._run_web_preflight(summary)
        worker_before = self._wait_prod_worker(summary, require_disabled=False)
        summary["worker_before_canary"] = _worker_summary(worker_before)
        summary["tasks"] = []
        self._set_agent_control("enabled", reason="runpod_prod_worker_canary")
        try:
            image_object_key = self._resolve_canary_image(summary)
            task_result = self._run_img2img_task(image_object_key, summary)
            summary["tasks"].append(task_result)
            summary["runpod_task_verified"] = (
                (task_result.get("pop_evidence") or {}).get("agent_id") == self.options.agent_id
            )
            summary["ok"] = True
        finally:
            try:
                summary["restore_control"] = self._set_agent_control(
                    "disabled",
                    reason="runpod_prod_worker_canary_restore",
                )
            except Exception as exc:
                summary["ok"] = False
                summary["restore_control_error"] = redact_text(str(exc))

    def _run_scale(self, summary: dict[str, Any]) -> None:
        desired = self._desired_count()
        max_slots = self.provider.settings.prod_max_manual_slots
        if desired > max_slots:
            raise RunPodProdWorkerError(
                f"--desired must be <= RUNPOD_PROD_MAX_MANUAL_SLOTS ({max_slots})"
            )
        summary["desired_count"] = desired
        summary["max_manual_slots"] = max_slots

        self._phase(summary, "runpod_validate_key", "running")
        validate = self.provider.validate_key()
        self._require_ok(validate, "runpod validate-key failed")
        self._phase(summary, "runpod_validate_key", "ok")

        self._phase(summary, "runpod_list_pods", "running")
        listed = self.provider.list_pods(managed_only=True)
        self._require_ok(listed, "runpod list-pods failed")
        managed_pods = list(listed.get("pods") or [])
        slot_pods = _prod_manual_slot_pods(
            managed_pods,
            max_manual_slots=max_slots,
        )
        self._phase(
            summary,
            "runpod_list_pods",
            "ok",
            {
                "managed_count": listed.get("count", 0),
                "prod_slot_count": len(slot_pods),
            },
        )

        self._phase(summary, "runpod_reconcile", "running")
        reconcile = self.provider.reconcile_managed_pods()
        self._require_ok(reconcile, "runpod reconcile-managed-pods failed")
        summary["reconcile"] = {
            "managed_count": reconcile.get("managed_count"),
            "orphans": reconcile.get("orphans", []),
            "by_task_type": reconcile.get("by_task_type", {}),
        }
        self._phase(summary, "runpod_reconcile", "ok", summary["reconcile"])

        self._phase(summary, "central_health", "running")
        health = self._http_json("GET", _join_url(self.options.central_url, "health"))
        summary["central_health"] = redact_payload(health)
        self._phase(summary, "central_health", "ok", {"central_url": self.options.central_url})

        workers = self._fetch_workers()
        controls = self._scale_control_snapshot(
            desired=desired,
            slot_pods=slot_pods,
        )
        plan = self._build_scale_plan(
            desired=desired,
            slot_pods=slot_pods,
            workers=workers,
            controls=controls,
        )
        summary["scale_plan"] = plan
        if not self.options.execute:
            summary["ok"] = True
            summary["would_execute"] = self._scale_would_execute(plan)
            return

        self._require_agent_token()
        self._require_runpod_mutation_gates(
            required_pod_limit=desired if plan["create_slots"] else 0,
        )
        operations: list[dict[str, Any]] = []
        for slot in plan["create_slots"]:
            operations.append(self._scale_create_slot(slot, summary))
        for slot in plan["enable_slots"]:
            operations.append(self._scale_enable_slot(slot, summary))
        for slot in plan["delete_slots"]:
            pod = slot_pods.get(slot)
            if pod is None:
                continue
            operations.append(self._scale_delete_slot(slot, pod, summary))
        summary["operations"] = operations

        listed_after = self.provider.list_pods(managed_only=True)
        reconcile_after = self.provider.reconcile_managed_pods()
        summary["post_reconcile"] = {
            "list_pods": {
                "ok": listed_after.get("ok"),
                "count": listed_after.get("count"),
            },
            "reconcile": {
                "ok": reconcile_after.get("ok"),
                "managed_count": reconcile_after.get("managed_count"),
                "orphans": reconcile_after.get("orphans", []),
            },
        }
        summary["ok"] = bool(listed_after.get("ok") and reconcile_after.get("ok"))

    def _desired_count(self) -> int:
        if self.options.desired_count is None:
            raise RunPodProdWorkerError("prod-worker scale requires --desired")
        try:
            desired = int(self.options.desired_count)
        except (TypeError, ValueError) as exc:
            raise RunPodProdWorkerError("--desired must be an integer") from exc
        if desired < 0:
            raise RunPodProdWorkerError("--desired must be >= 0")
        return desired

    def _build_scale_plan(
        self,
        *,
        desired: int,
        slot_pods: dict[str, dict[str, Any]],
        workers: list[dict[str, Any]],
        controls: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        desired_slots = set(_prod_slot_sequence(desired))
        existing_slots = set(slot_pods)
        create_slots = sorted(
            desired_slots - existing_slots,
            key=_slot_sort_key,
        )
        enable_slots = sorted(
            desired_slots & existing_slots,
            key=_slot_sort_key,
        )
        delete_slots = sorted(
            existing_slots - desired_slots,
            key=_slot_sort_key,
            reverse=True,
        )
        slots: dict[str, Any] = {}
        for slot in sorted(existing_slots | desired_slots, key=_slot_sort_key):
            agent_id = prod_agent_id_from_slot(
                slot,
                max_manual_slots=self.provider.settings.prod_max_manual_slots,
            )
            worker = _find_worker(workers, agent_id)
            slots[slot] = {
                "agent_id": agent_id,
                "pod": _pod_minimal(slot_pods[slot]) if slot in slot_pods else None,
                "worker": _worker_summary(worker) if worker else None,
                "control": controls.get(slot),
            }
        return {
            "desired_slots": sorted(desired_slots, key=_slot_sort_key),
            "existing_slots": sorted(existing_slots, key=_slot_sort_key),
            "create_slots": create_slots,
            "enable_slots": enable_slots,
            "delete_slots": delete_slots,
            "slots": slots,
        }

    def _scale_control_snapshot(
        self,
        *,
        desired: int,
        slot_pods: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        slots = sorted(
            set(_prod_slot_sequence(desired)) | set(slot_pods),
            key=_slot_sort_key,
        )
        snapshot: dict[str, dict[str, Any]] = {}
        for slot in slots:
            agent_id = prod_agent_id_from_slot(
                slot,
                max_manual_slots=self.provider.settings.prod_max_manual_slots,
            )
            if not self.options.agent_token:
                snapshot[slot] = {
                    "agent_id": agent_id,
                    "state": "unknown",
                    "note": "AGENT_SECRET_TOKEN not loaded; control was not queried",
                }
                continue
            try:
                snapshot[slot] = redact_payload(
                    self._get_agent_control_for_agent(agent_id)
                )
            except Exception as exc:
                snapshot[slot] = {
                    "agent_id": agent_id,
                    "state": "unknown",
                    "error": redact_text(str(exc)),
                }
        return snapshot

    def _scale_would_execute(self, plan: dict[str, Any]) -> list[str]:
        actions: list[str] = []
        for slot in plan["create_slots"]:
            agent_id = prod_agent_id_from_slot(
                slot,
                max_manual_slots=self.provider.settings.prod_max_manual_slots,
            )
            actions.extend(
                [
                    f"set Central control for {agent_id} to disabled",
                    f"create cloud-prod RunPod pod for slot {slot}",
                    f"wait for slot {slot} Pod readiness and disabled heartbeat",
                    f"set Central control for {agent_id} to enabled",
                ]
            )
        for slot in plan["enable_slots"]:
            agent_id = prod_agent_id_from_slot(
                slot,
                max_manual_slots=self.provider.settings.prod_max_manual_slots,
            )
            actions.append(f"verify slot {slot} heartbeat and set {agent_id} to enabled")
        for slot in plan["delete_slots"]:
            agent_id = prod_agent_id_from_slot(
                slot,
                max_manual_slots=self.provider.settings.prod_max_manual_slots,
            )
            actions.extend(
                [
                    f"set Central control for {agent_id} to disabled",
                    f"wait until slot {slot} worker has no current_task_id",
                    f"delete cloud-prod RunPod pod for slot {slot}",
                ]
            )
        if not actions:
            actions.append("no changes; desired RunPod prod worker count already matches")
        return actions

    def _scale_create_slot(
        self,
        slot: str,
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        agent_id = prod_agent_id_from_slot(
            slot,
            max_manual_slots=self.provider.settings.prod_max_manual_slots,
        )
        provider = self._provider_for_agent(agent_id)
        operation: dict[str, Any] = {
            "action": "create",
            "slot": slot,
            "agent_id": agent_id,
        }
        render = self._render(redact=False, agent_id=agent_id, provider=provider)
        operation["render"] = self._render_summary(render)
        operation["disable_control"] = self._set_agent_control_for_agent(
            agent_id,
            "disabled",
            reason="runpod_prod_worker_scale_up",
        )
        create_payload = provider.create_pod(
            task_type=self.options.task_type,
            environment=self.options.environment,
            execute=True,
        )
        self._require_ok(create_payload, f"runpod create-pod failed for slot {slot}")
        pod_id = _extract_pod_id(create_payload)
        operation["pod"] = _pod_summary(create_payload, operation["render"].get("imageName", ""))
        self._phase(summary, f"runpod_create_pod_{slot}", "ok", {"pod_id": pod_id})
        self._wait_pod_readiness(pod_id, summary, provider=provider)
        worker = self._wait_prod_worker_for_agent(
            agent_id,
            summary,
            require_disabled=True,
        )
        operation["worker"] = _worker_summary(worker)
        operation["enable_control"] = self._set_agent_control_for_agent(
            agent_id,
            "enabled",
            reason="runpod_prod_worker_scale_enable",
        )
        return operation

    def _scale_enable_slot(
        self,
        slot: str,
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        agent_id = prod_agent_id_from_slot(
            slot,
            max_manual_slots=self.provider.settings.prod_max_manual_slots,
        )
        worker = self._wait_prod_worker_for_agent(
            agent_id,
            summary,
            require_disabled=False,
        )
        control = self._set_agent_control_for_agent(
            agent_id,
            "enabled",
            reason="runpod_prod_worker_scale_enable",
        )
        return {
            "action": "enable",
            "slot": slot,
            "agent_id": agent_id,
            "worker": _worker_summary(worker),
            "control": control,
        }

    def _scale_delete_slot(
        self,
        slot: str,
        pod: dict[str, Any],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        agent_id = prod_agent_id_from_slot(
            slot,
            max_manual_slots=self.provider.settings.prod_max_manual_slots,
        )
        provider = self._provider_for_agent(agent_id)
        operation: dict[str, Any] = {
            "action": "delete",
            "slot": slot,
            "agent_id": agent_id,
        }
        operation["disable_control"] = self._set_agent_control_for_agent(
            agent_id,
            "disabled",
            reason="runpod_prod_worker_scale_down",
        )
        worker = self._wait_worker_drained_for_agent(agent_id, summary)
        operation["worker"] = _worker_summary(worker) if worker else {}
        pod_id = str(pod.get("id") or pod.get("podId") or "")
        if not pod_id:
            raise RunPodProdWorkerError(f"managed prod pod for slot {slot} did not include an id")
        delete_payload = provider.delete_pod(
            pod_id=pod_id,
            task_type=self.options.task_type,
            execute=True,
        )
        self._require_ok(delete_payload, f"runpod delete-pod failed for slot {slot}")
        operation["pod_delete"] = {"pod_id": pod_id, "ok": True}
        self._phase(summary, f"runpod_delete_pod_{slot}", "ok", {"pod_id": pod_id})
        return operation

    def _provider_for_agent(self, agent_id: str) -> Any:
        if hasattr(self.provider, "for_prod_agent_id"):
            return self.provider.for_prod_agent_id(agent_id)
        return RunPodProvider(
            replace(self.provider.settings, prod_agent_id=agent_id),
        )

    def _run_preflight(
        self,
        summary: dict[str, Any],
        *,
        allow_existing_prod_pod: bool = False,
    ) -> None:
        self._phase(summary, "runpod_validate_key", "running")
        validate = self.provider.validate_key()
        self._require_ok(validate, "runpod validate-key failed")
        self._phase(summary, "runpod_validate_key", "ok")

        self._phase(summary, "runpod_list_pods", "running")
        listed = self.provider.list_pods(managed_only=True)
        self._require_ok(listed, "runpod list-pods failed")
        prod_pods = self._prod_pods(list(listed.get("pods") or []))
        if self.options.execute and prod_pods and not allow_existing_prod_pod:
            raise RunPodProdWorkerError("refusing up: managed prod RunPod pod already exists")
        summary["prod_pods"] = [_pod_minimal(pod) for pod in prod_pods]
        self._phase(
            summary,
            "runpod_list_pods",
            "ok",
            {
                "managed_count": listed.get("count", 0),
                "prod_pod_count": len(prod_pods),
            },
        )

        self._phase(summary, "runpod_reconcile", "running")
        reconcile = self.provider.reconcile_managed_pods()
        self._require_ok(reconcile, "runpod reconcile-managed-pods failed")
        summary["reconcile"] = {
            "managed_count": reconcile.get("managed_count"),
            "orphans": reconcile.get("orphans", []),
            "by_task_type": reconcile.get("by_task_type", {}),
        }
        self._phase(summary, "runpod_reconcile", "ok", summary["reconcile"])

        self._phase(summary, "render", "running")
        render = self._render(redact=False)
        summary["render"] = self._render_summary(render)
        self._phase(summary, "render", "ok", summary["render"])

        self._phase(summary, "central_health", "running")
        health = self._http_json("GET", _join_url(self.options.central_url, "health"))
        summary["central_health"] = redact_payload(health)
        self._phase(summary, "central_health", "ok", {"central_url": self.options.central_url})

    def _run_web_preflight(self, summary: dict[str, Any]) -> None:
        self._phase(summary, "prod_web_and_central_preflight", "running")
        self._web_token()
        self._http_json("GET", _join_url(self.options.web_api_url, "health"))
        self._http_json("GET", _join_url(self.options.central_url, "health"))
        self._http_json(
            "GET",
            _join_url(self.options.web_api_url, "tasks", "queue-status"),
            headers=self._web_auth_headers(),
        )
        self._phase(
            summary,
            "prod_web_and_central_preflight",
            "ok",
            {
                "web_api_url": self.options.web_api_url,
                "central_url": self.options.central_url,
                "web_user_id": self.options.web_user_id,
            },
        )

    def _render(
        self,
        *,
        redact: bool,
        agent_id: str | None = None,
        provider: Any | None = None,
    ) -> dict[str, Any]:
        target_provider = provider or self.provider
        target_agent_id = agent_id or self.options.agent_id
        render = target_provider.render_create_pod_request(
            task_type=self.options.task_type,
            environment=self.options.environment,
            redact=redact,
        )
        self._validate_render(
            render,
            agent_id=target_agent_id,
            settings=target_provider.settings,
        )
        return render

    def _validate_render(
        self,
        render: dict[str, Any],
        *,
        agent_id: str | None = None,
        settings: Any | None = None,
    ) -> None:
        body = render.get("json") or {}
        env = body.get("env") or {}
        target_agent_id = agent_id or self.options.agent_id
        target_settings = settings or self.provider.settings
        failures: list[str] = []
        if body.get("templateId"):
            failures.append("templateId must be empty for prod GHCR baked image")
        if str(body.get("imageName") or "") != RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE:
            failures.append("imageName must be the verified GHCR baked image")
        expected_env = {
            "ENVIRONMENT": "prod",
            "RUNPOD_ENVIRONMENT": PROD_ENVIRONMENT,
            "AGENT_ID": target_agent_id,
            "AGENT_ID_PREFIX": target_agent_id,
            "CENTRAL_API_URL": target_settings.worker_central_url_cloud_prod,
            "SUPPORTED_TASK_TYPES": ",".join(target_settings.prod_supported_task_types),
            "POOL_PROVIDER": "runpod",
            "POOL_NODE_ID": target_settings.prod_node_id,
            "POOL_RUNTIME_PROFILE": "img2img_lora",
            "MINIO_BUCKET": target_settings.prod_bucket,
            "MINIO_INPUT_BUCKET": target_settings.prod_bucket,
            "MINIO_RESULT_BUCKET": target_settings.prod_bucket,
            "MINIO_TEMPLATE_BUCKET": target_settings.prod_bucket,
            "RUNPOD_MODEL_SYNC_ENABLED": "true",
            "RUNPOD_MODEL_BUCKET": PROD_MODEL_BUCKET,
            "RUNPOD_MODEL_PREFIX": PROD_MODEL_PREFIX,
            "RUNPOD_MODEL_MANIFEST_KEY": PROD_MODEL_MANIFEST_KEY,
            "RUNPOD_COMFY_CUSTOM_NODES_ENABLED": "false",
            "RUNPOD_COMFY_KJNODES_ENABLED": "false",
            "RUNPOD_START_SSHD": "false",
            "RUNPOD_INSTALL_SSHD_IF_MISSING": "false",
        }
        for key, expected in expected_env.items():
            if str(env.get(key) or "") != expected:
                failures.append(f"{key} must be {expected}")
        if list(body.get("gpuTypeIds") or []) != list(target_settings.prod_gpu_type_ids):
            failures.append(
                "gpuTypeIds must be "
                + ",".join(target_settings.prod_gpu_type_ids)
                + " for prod-worker"
            )
        expected_refs = {
            "AGENT_SECRET_TOKEN": target_settings.prod_agent_secret_token_ref,
            "MINIO_ACCESS_KEY": target_settings.prod_minio_access_key_ref,
            "MINIO_SECRET_KEY": target_settings.prod_minio_secret_key_ref,
            "RUNPOD_MODEL_ACCESS_KEY": RUNPOD_MODEL_CACHE_R2_ACCESS_KEY_REF,
            "RUNPOD_MODEL_SECRET_KEY": RUNPOD_MODEL_CACHE_R2_SECRET_KEY_REF,
        }
        for key, expected in expected_refs.items():
            value = str(env.get(key) or "")
            if value != expected:
                failures.append(f"{key} must use prod RunPod secret reference")
            if not value.startswith("{{ RUNPOD_SECRET_"):
                failures.append(f"{key} must not contain an inline secret")
        if failures:
            raise RunPodProdWorkerError(
                "prod render sanity check failed: " + "; ".join(failures)
            )

    def _render_summary(self, render: dict[str, Any]) -> dict[str, Any]:
        body = render.get("json") or {}
        env = body.get("env") or {}
        return {
            "pod_name": body.get("name"),
            "imageName": body.get("imageName"),
            "templateId": bool(body.get("templateId")),
            "gpu_type_ids": body.get("gpuTypeIds"),
            "central_api_url": env.get("CENTRAL_API_URL"),
            "agent_id": env.get("AGENT_ID"),
            "supported_task_types": env.get("SUPPORTED_TASK_TYPES"),
            "pool_node_id": env.get("POOL_NODE_ID"),
            "pool_runtime_profile": env.get("POOL_RUNTIME_PROFILE"),
            "model_bucket": env.get("RUNPOD_MODEL_BUCKET"),
            "model_prefix": env.get("RUNPOD_MODEL_PREFIX"),
            "model_manifest_key": env.get("RUNPOD_MODEL_MANIFEST_KEY"),
            "custom_nodes_enabled": env.get("RUNPOD_COMFY_CUSTOM_NODES_ENABLED"),
            "kjnodes_enabled": env.get("RUNPOD_COMFY_KJNODES_ENABLED"),
            "sshd_enabled": env.get("RUNPOD_START_SSHD"),
            "buckets": {
                "input": env.get("MINIO_INPUT_BUCKET"),
                "result": env.get("MINIO_RESULT_BUCKET"),
                "template": env.get("MINIO_TEMPLATE_BUCKET"),
            },
            "refs": [
                _secret_ref_name(env.get("AGENT_SECRET_TOKEN")),
                _secret_ref_name(env.get("MINIO_ACCESS_KEY")),
                _secret_ref_name(env.get("MINIO_SECRET_KEY")),
            ],
        }

    def _status_snapshot(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": True}
        listed = self.provider.list_pods(managed_only=True)
        payload["list_pods"] = {
            "ok": listed.get("ok"),
            "count": listed.get("count"),
        }
        if not listed.get("ok"):
            payload["ok"] = False
            payload["list_pods"]["error"] = listed.get("error")
        pods = self._prod_pods(list(listed.get("pods") or []))
        payload["prod_pod_count"] = len(pods)
        payload["prod_pods"] = [_pod_minimal(pod) for pod in pods]
        reconcile = self.provider.reconcile_managed_pods()
        payload["reconcile"] = {
            "ok": reconcile.get("ok"),
            "managed_count": reconcile.get("managed_count"),
            "orphans": reconcile.get("orphans", []),
        }
        if not reconcile.get("ok"):
            payload["ok"] = False
        try:
            workers = self._fetch_workers()
            worker = _find_worker(workers, self.options.agent_id)
            payload["worker"] = _worker_summary(worker) if worker else None
        except Exception as exc:
            payload["worker_error"] = redact_text(str(exc))
            payload["ok"] = False
        if self.options.agent_token:
            try:
                payload["control"] = self._get_agent_control()
            except Exception as exc:
                payload["control_error"] = redact_text(str(exc))
                payload["ok"] = False
        else:
            payload["control"] = {
                "agent_id": self.options.agent_id,
                "state": "unknown",
                "note": "AGENT_SECRET_TOKEN not loaded; control was not queried",
            }
        return payload

    def _prod_pods(self, pods: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            pod
            for pod in pods
            if _is_prod_pod(
                pod,
                self.options.agent_id,
                max_manual_slots=self.provider.settings.prod_max_manual_slots,
            )
        ]

    def _single_prod_pod(self, summary: dict[str, Any]) -> dict[str, Any] | None:
        listed = self.provider.list_pods(managed_only=True)
        self._require_ok(listed, "runpod list-pods failed")
        prod_pods = self._prod_pods(list(listed.get("pods") or []))
        summary["prod_pods"] = [_pod_minimal(pod) for pod in prod_pods]
        if not prod_pods:
            return None
        if len(prod_pods) > 1:
            raise RunPodProdWorkerError("refusing down: multiple managed prod RunPod pods found")
        return prod_pods[0]

    def _wait_pod_readiness(
        self,
        pod_id: str,
        summary: dict[str, Any],
        *,
        provider: Any | None = None,
    ) -> None:
        target_provider = provider or self.provider
        self._phase(summary, "pod_readiness", "running", {"pod_id": pod_id})
        deadline = time.monotonic() + self.options.readiness_timeout_seconds
        last_payload: dict[str, Any] | None = None
        while time.monotonic() <= deadline:
            payload = target_provider.pod_readiness(pod_id=pod_id)
            self._require_ok(payload, "runpod pod-readiness failed")
            last_payload = payload
            readiness = payload.get("readiness") or {}
            if readiness.get("infrastructure_ready") is True:
                summary["pod_readiness"] = {
                    "pod_id": pod_id,
                    "confidence": readiness.get("confidence"),
                    "network": readiness.get("network"),
                }
                self._phase(summary, "pod_readiness", "ok", summary["pod_readiness"])
                return
            self._sleep(self.options.poll_interval_seconds)
        raise RunPodProdWorkerError(
            "pod readiness timeout: "
            + json.dumps(redact_payload(last_payload), ensure_ascii=False)
        )

    def _wait_prod_worker(
        self,
        summary: dict[str, Any],
        *,
        require_disabled: bool,
    ) -> dict[str, Any]:
        return self._wait_prod_worker_for_agent(
            self.options.agent_id,
            summary,
            require_disabled=require_disabled,
        )

    def _wait_prod_worker_for_agent(
        self,
        agent_id: str,
        summary: dict[str, Any],
        *,
        require_disabled: bool,
    ) -> dict[str, Any]:
        self._phase(summary, "prod_worker_heartbeat", "running")
        deadline = time.monotonic() + self.options.worker_timeout_seconds
        last_worker: dict[str, Any] | None = None
        last_control: dict[str, Any] | None = None
        while time.monotonic() <= deadline:
            worker = _find_worker(self._fetch_workers(), agent_id)
            control = self._get_agent_control_for_agent(agent_id)
            last_worker = worker
            last_control = control
            if worker and _worker_supports_img2img(worker):
                status = str(worker.get("status") or "")
                control_state = str(control.get("state") or "enabled")
                control_ok = (not require_disabled) or control_state == "disabled"
                if status in HEALTHY_WORKER_STATUSES and control_ok:
                    details = {
                        "worker": _worker_summary(worker),
                        "control": control,
                    }
                    self._phase(summary, "prod_worker_heartbeat", "ok", details)
                    return worker
            self._sleep(self.options.poll_interval_seconds)
        raise RunPodProdWorkerError(
            "prod worker heartbeat timeout: "
            + json.dumps(
                {
                    "agent_id": agent_id,
                    "last_worker": _worker_summary(last_worker) if last_worker else None,
                    "last_control": redact_payload(last_control),
                },
                ensure_ascii=False,
            )
        )

    def _wait_worker_drained(self, summary: dict[str, Any]) -> dict[str, Any] | None:
        return self._wait_worker_drained_for_agent(self.options.agent_id, summary)

    def _wait_worker_drained_for_agent(
        self,
        agent_id: str,
        summary: dict[str, Any],
    ) -> dict[str, Any] | None:
        self._phase(summary, "worker_drain", "running")
        deadline = time.monotonic() + self.options.drain_timeout_seconds
        last_worker: dict[str, Any] | None = None
        while time.monotonic() <= deadline:
            worker = _find_worker(self._fetch_workers(), agent_id)
            last_worker = worker
            current_task_id = str((worker or {}).get("current_task_id") or "")
            if not current_task_id:
                self._phase(
                    summary,
                    "worker_drain",
                    "ok",
                    {"worker": _worker_summary(worker) if worker else None},
                )
                return worker
            self._sleep(self.options.poll_interval_seconds)
        raise RunPodProdWorkerError(
            "refusing down: prod RunPod worker still has current_task_id="
            + str((last_worker or {}).get("current_task_id") or "")
        )

    def _resolve_canary_image(self, summary: dict[str, Any]) -> str:
        object_key = self.options.input_object_key.strip()
        if object_key:
            self._phase(summary, "reuse_prod_test_image", "ok", {"object_key": object_key})
            return object_key
        return self._upload_canary_image(summary)

    def _upload_canary_image(self, summary: dict[str, Any]) -> str:
        self._phase(summary, "upload_prod_test_image", "running")
        self.options.output_dir.mkdir(parents=True, exist_ok=True)
        image_path = self.options.output_dir / f"runpod_prod_canary_{int(time.time())}.png"
        write_canary_png(image_path)
        presign = self._http_json(
            "GET",
            _join_url(self.options.web_api_url, "storage", "presigned-url"),
            params={"filename": image_path.name, "content_type": "image/png"},
            headers=self._web_auth_headers(),
        )
        object_key = str(presign.get("object_key") or "")
        upload_url = str(presign.get("upload_url") or "")
        if not object_key or not upload_url:
            raise RunPodProdWorkerError("presigned upload response missing object_key/upload_url")
        self._http_request(
            "PUT",
            upload_url,
            body=image_path.read_bytes(),
            headers={"Content-Type": "image/png"},
            expected_statuses=(200, 201, 204),
        )
        self._phase(summary, "upload_prod_test_image", "ok", {"object_key": object_key})
        return object_key

    def _run_img2img_task(
        self,
        image_object_key: str,
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        self._phase(summary, "task_prod_img2img_canary", "running")
        payload = {
            "task_type": PROD_TASK_TYPE,
            "inputs": {
                "images": [image_object_key],
                "image": image_object_key,
                "num_inference_steps": 6,
                "guidance_scale": 1.0,
                "seed": 20260612,
            },
            "prompt": self.options.prompt,
            "negative_prompt": self.options.negative_prompt,
            "priority": 0,
        }
        submit_payload = self._http_json(
            "POST",
            _join_url(self.options.web_api_url, "tasks", "generate"),
            json_body=payload,
            headers=self._web_auth_headers(),
        )
        task_id = str(submit_payload.get("task_id") or "")
        if not task_id:
            raise RunPodProdWorkerError("missing task_id in Web response")
        final_status, pop_evidence = self._wait_task_done(task_id)
        task_result: dict[str, Any] = {
            "label": "prod_img2img_canary",
            "registry_task_id": task_id,
            "task_type": PROD_TASK_TYPE,
            "central_status": final_status.get("status"),
            "central_task_type": final_status.get("task_type"),
            "pop_evidence": pop_evidence,
        }
        if final_status.get("status") != "done":
            raise RunPodProdWorkerError(
                f"prod canary Central terminal status is {final_status.get('status')}"
            )
        result_payload = self._wait_web_result(task_id)
        result_url = str(result_payload.get("result_url") or "")
        task_result["web_result_status"] = result_payload.get("status")
        task_result["result_path"] = result_url_path(result_url)
        if result_payload.get("status") != "success" or not result_url:
            raise RunPodProdWorkerError("prod canary Web result did not become success")
        task_result.update(self._download_result(task_id=task_id, result_url=result_url))
        self._phase(summary, "task_prod_img2img_canary", "ok", task_result)
        return task_result

    def _wait_task_done(self, task_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        deadline = time.monotonic() + self.options.task_timeout_seconds
        last_status: dict[str, Any] = {}
        pop_evidence: dict[str, Any] = {
            "observed": False,
            "expected_agent_id": self.options.agent_id,
            "agent_id": "",
        }
        while time.monotonic() <= deadline:
            status_payload = self._http_json(
                "GET",
                _join_url(self.options.central_url, "status", task_id),
                allow_statuses=(404,),
            )
            if status_payload.get("_status") != 404:
                last_status = status_payload
            workers = self._fetch_workers()
            current_worker = _find_current_task_worker(workers, task_id)
            if current_worker:
                pop_evidence = {
                    "observed": True,
                    "expected_agent_id": self.options.agent_id,
                    "agent_id": current_worker.get("agent_id"),
                    "current_task_id": current_worker.get("current_task_id"),
                    "current_task_type": current_worker.get("current_task_type"),
                    "status": current_worker.get("status"),
                }
            status = str(last_status.get("status") or "")
            if status in TERMINAL_TASK_STATUSES:
                if not pop_evidence["observed"]:
                    pop_evidence["note"] = "not_observed_during_poll"
                return last_status, pop_evidence
            self._sleep(self.options.task_poll_interval_seconds)
        raise RunPodProdWorkerError(
            f"prod canary task timeout: {task_id} last_status="
            + json.dumps(redact_payload(last_status), ensure_ascii=False)
        )

    def _wait_web_result(self, task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + min(self.options.task_timeout_seconds, 300.0)
        last_result: dict[str, Any] = {}
        while time.monotonic() <= deadline:
            payload = self._http_json(
                "GET",
                _join_url(self.options.web_api_url, "tasks", task_id, "result"),
                headers=self._web_auth_headers(),
            )
            last_result = payload
            if payload.get("status") == "success" and payload.get("result_url"):
                return payload
            self._sleep(self.options.task_poll_interval_seconds)
        raise RunPodProdWorkerError(
            f"prod canary web result timeout: {task_id} last_result="
            + json.dumps(redact_payload(last_result), ensure_ascii=False)
        )

    def _download_result(self, *, task_id: str, result_url: str) -> dict[str, str]:
        download_dir = self.options.download_results_dir
        download_dir.mkdir(parents=True, exist_ok=True)
        parsed = urllib.parse.urlsplit(result_url)
        suffix = Path(parsed.path).suffix or ".bin"
        target = download_dir / f"prod_img2img_canary_{task_id}{suffix}"
        method = "public_url"
        try:
            response = self._http_request(
                "GET",
                result_url,
                headers={"User-Agent": "AllBot-RunPod-Prod-Worker/1.0"},
                expected_statuses=(200,),
            )
            raw = response["raw"]
        except Exception:
            method = "r2_s3"
            raw = self._download_result_bytes_from_s3(result_url)
        target.write_bytes(raw)
        return {"downloaded_file": str(target), "download_method": method}

    def _download_result_bytes_from_s3(self, result_url: str) -> bytes:
        object_key = result_url_path(result_url).lstrip("/")
        if not object_key:
            raise RunPodProdWorkerError("result URL did not contain an object key path")
        endpoint = os.getenv("MINIO_ENDPOINT", "").strip()
        access_key = os.getenv("MINIO_ACCESS_KEY", "").strip()
        secret_key = os.getenv("MINIO_SECRET_KEY", "").strip()
        bucket = os.getenv("MINIO_RESULT_BUCKET", RUNPOD_PROD_BUCKET).strip()
        secure = os.getenv("MINIO_SECURE", "true").strip().lower() in {"1", "true", "yes", "on"}
        if not endpoint or not access_key or not secret_key or not bucket:
            raise RunPodProdWorkerError("R2 S3 fallback is missing MINIO endpoint/credentials/bucket")
        endpoint_url = endpoint
        if "://" not in endpoint_url:
            endpoint_url = f"{'https' if secure else 'http'}://{endpoint_url}"
        try:
            import boto3
        except Exception as exc:
            raise RunPodProdWorkerError(f"boto3 is required for R2 S3 result download: {exc}") from exc
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=os.getenv("AWS_DEFAULT_REGION", "auto"),
        )
        try:
            response = client.get_object(Bucket=bucket, Key=object_key)
            body = response["Body"].read()
        except Exception as exc:
            raise RunPodProdWorkerError(f"R2 S3 result download failed for {object_key}: {exc}") from exc
        return body

    def _get_agent_control(self) -> dict[str, Any]:
        return self._get_agent_control_for_agent(self.options.agent_id)

    def _get_agent_control_for_agent(self, agent_id: str) -> dict[str, Any]:
        self._require_agent_token()
        return self._http_json(
            "GET",
            _join_url(self.options.central_url, "api", "agent", "task", "control", agent_id),
            headers=self._agent_headers(),
        )

    def _set_agent_control(self, state: str, *, reason: str) -> dict[str, Any]:
        return self._set_agent_control_for_agent(
            self.options.agent_id,
            state,
            reason=reason,
        )

    def _set_agent_control_for_agent(
        self,
        agent_id: str,
        state: str,
        *,
        reason: str,
    ) -> dict[str, Any]:
        self._require_agent_token()
        body = {"state": state, "reason": reason}
        payload = self._http_json(
            "POST",
            _join_url(self.options.central_url, "api", "agent", "task", "control", agent_id),
            json_body=body,
            headers=self._agent_headers(),
        )
        self._phase("control_" + state, "ok", payload)
        return payload

    def _fetch_workers(self) -> list[dict[str, Any]]:
        payload = self._http_json("GET", _join_url(self.options.central_url, "system", "workers"))
        workers = payload.get("workers") or []
        if not isinstance(workers, list):
            raise RunPodProdWorkerError("Central /system/workers returned non-list workers")
        return [worker for worker in workers if isinstance(worker, dict)]

    def _web_token(self) -> str:
        if self.options.web_bearer_token:
            return self.options.web_bearer_token
        try:
            from src.web_api.core.security import create_access_token
        except Exception as exc:
            raise RunPodProdWorkerError(f"failed to load Web JWT signer: {exc}") from exc
        return create_access_token(
            subject=str(self.options.web_user_id),
            pwd_ver=self.options.web_pwd_ver,
            channel="runpod_prod_worker",
        )

    def _web_auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._web_token()}"}

    def _agent_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.options.agent_token}"}

    def _http_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
        allow_statuses: tuple[int, ...] = (),
    ) -> dict[str, Any]:
        body = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        request_headers = dict(headers or {})
        if json_body is not None:
            request_headers["Content-Type"] = "application/json"
        response = self._http_request(
            method,
            url,
            params=params,
            body=body,
            headers=request_headers,
            expected_statuses=expected_statuses,
            allow_statuses=allow_statuses,
        )
        if not response["text"]:
            return {"_status": response["status"]}
        try:
            payload = json.loads(response["text"])
        except json.JSONDecodeError as exc:
            raise RunPodProdWorkerError(f"invalid JSON response from {method} {_safe_url(url)}") from exc
        if isinstance(payload, dict):
            payload.setdefault("_status", response["status"])
            return payload
        return {"_status": response["status"], "data": payload}

    def _http_request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
        allow_statuses: tuple[int, ...] = (),
    ) -> dict[str, Any]:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
        request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = int(response.status)
                raw = response.read()
                text = raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw = exc.read()
            text = raw.decode("utf-8", errors="replace")
            if status not in expected_statuses and status not in allow_statuses:
                raise RunPodProdWorkerError(
                    f"{method} {_safe_url(url)} returned HTTP {status}: {redact_text(text[:500])}"
                ) from exc
        except urllib.error.URLError as exc:
            raise RunPodProdWorkerError(
                f"{method} {_safe_url(url)} network error: {redact_text(str(exc.reason))}"
            ) from exc
        if status not in expected_statuses and status not in allow_statuses:
            raise RunPodProdWorkerError(
                f"{method} {_safe_url(url)} returned HTTP {status}: {redact_text(text[:500])}"
            )
        return {"status": status, "text": text, "raw": raw}

    def _require_runpod_mutation_gates(
        self,
        *,
        required_pod_limit: int | None = None,
    ) -> None:
        settings = self.provider.settings
        max_manual_slots = settings.prod_max_manual_slots
        if required_pod_limit is None:
            required_pod_limit = int(
                prod_slot_from_agent_id(
                    self.options.agent_id,
                    max_manual_slots=max_manual_slots,
                )
            )
        missing_gates: list[str] = []
        if settings.dry_run:
            missing_gates.append("RUNPOD_DRY_RUN=false")
        if not settings.autoscaler_enabled:
            missing_gates.append("RUNPOD_AUTOSCALER_ENABLED=true")
        if settings.max_pods_total < required_pod_limit:
            missing_gates.append(f"RUNPOD_MAX_PODS_TOTAL>={required_pod_limit}")
        if settings.max_pods_total > max_manual_slots:
            missing_gates.append(
                f"RUNPOD_MAX_PODS_TOTAL<={max_manual_slots}"
            )
        if settings.max_pods_per_type < required_pod_limit:
            missing_gates.append(f"RUNPOD_MAX_PODS_PER_TYPE>={required_pod_limit}")
        if settings.max_pods_per_type > max_manual_slots:
            missing_gates.append(
                f"RUNPOD_MAX_PODS_PER_TYPE<={max_manual_slots}"
            )
        if settings.max_pods_per_type > settings.max_pods_total:
            missing_gates.append(
                "RUNPOD_MAX_PODS_PER_TYPE<=RUNPOD_MAX_PODS_TOTAL"
            )
        if missing_gates:
            raise RunPodProdWorkerError(
                "execute requires RunPod prod-worker gates: " + ", ".join(missing_gates)
            )

    def _require_agent_token(self) -> None:
        if not self.options.agent_token:
            raise RunPodProdWorkerError("AGENT_SECRET_TOKEN is required for prod-worker control")

    @staticmethod
    def _require_ok(payload: dict[str, Any], message: str) -> None:
        if not payload.get("ok"):
            raise RunPodProdWorkerError(
                f"{message}: {redact_text(str(payload.get('error') or payload))}"
            )

    def _phase(
        self,
        summary: dict[str, Any] | str,
        name: str,
        status: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if isinstance(summary, str):
            self._emit(f"[runpod-prod-worker] {summary}: {name}")
            return
        entry = {"name": name, "status": status, "at": _utc_now_iso()}
        if details:
            entry["details"] = redact_payload(details)
        summary.setdefault("phases", []).append(entry)
        self._emit(f"[runpod-prod-worker] {name}: {status}")

    def _emit(self, message: str) -> None:
        if not self.options.quiet:
            self._emit_func(message)

    @staticmethod
    def _finish(summary: dict[str, Any]) -> dict[str, Any]:
        summary["ended_at"] = _utc_now_iso()
        return redact_payload(summary)


def _dotenv_values(path: Path) -> dict[str, str | None]:
    try:
        from dotenv import dotenv_values
    except Exception:
        return _dotenv_values_fallback(path)
    return {str(key): value for key, value in dotenv_values(path).items()}


def _dotenv_values_fallback(path: Path) -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _strip_env_quotes(value.strip())
    return values


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _join_url(base: str, *parts: str) -> str:
    return "/".join([base.rstrip("/"), *(part.strip("/") for part in parts if part)])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parsed._replace(query="", fragment=""))


def _secret_ref_name(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.startswith("{{") and raw.endswith("}}"):
        raw = raw.strip("{} ").strip()
    if raw.startswith("RUNPOD_SECRET_"):
        return raw[len("RUNPOD_SECRET_") :]
    return ""


def _extract_pod_id(payload: dict[str, Any]) -> str:
    pod = payload.get("pod") or payload.get("response") or payload
    if isinstance(pod, dict):
        for key in ("id", "podId", "pod_id"):
            value = pod.get(key)
            if value:
                return str(value)
        data = pod.get("data")
        if isinstance(data, dict):
            for key in ("id", "podId", "pod_id"):
                value = data.get(key)
                if value:
                    return str(value)
    raise RunPodProdWorkerError("RunPod create response did not include pod id")


def _pod_summary(payload: dict[str, Any], image_ref: str) -> dict[str, Any]:
    pod = payload.get("pod") or payload.get("response") or payload
    if not isinstance(pod, dict):
        pod = {}
    machine = pod.get("machine") if isinstance(pod.get("machine"), dict) else {}
    return {
        "pod_id": _extract_pod_id(payload),
        "name": pod.get("name"),
        "gpu": (
            pod.get("gpuTypeId")
            or pod.get("gpuType")
            or machine.get("gpuDisplayName")
            or machine.get("gpuType")
        ),
        "image": pod.get("imageName") or pod.get("image") or image_ref,
        "created_at": pod.get("createdAt") or pod.get("created_at"),
        "cost_per_hr": pod.get("costPerHr") or pod.get("adjustedCostPerHr"),
    }


def _pod_minimal(pod: dict[str, Any]) -> dict[str, Any]:
    env = pod.get("env") if isinstance(pod.get("env"), dict) else {}
    return {
        "id": pod.get("id") or pod.get("podId"),
        "name": pod.get("name"),
        "desiredStatus": pod.get("desiredStatus") or pod.get("status"),
        "agent_id": env.get("AGENT_ID"),
        "environment": env.get("RUNPOD_ENVIRONMENT"),
        "task_type": env.get("RUNPOD_TASK_TYPE"),
    }


def _is_prod_pod(
    pod: dict[str, Any],
    agent_id: str,
    *,
    max_manual_slots: int | None = None,
) -> bool:
    env = pod.get("env") if isinstance(pod.get("env"), dict) else {}
    name = str(pod.get("name") or "")
    return (
        name == prod_pod_name_from_agent_id(
            agent_id,
            max_manual_slots=max_manual_slots,
        )
        or str(env.get("AGENT_ID") or "") == agent_id
        or str(env.get("AGENT_ID_PREFIX") or "") == agent_id
    )


def _prod_manual_slot_pods(
    pods: list[dict[str, Any]],
    *,
    max_manual_slots: int,
) -> dict[str, dict[str, Any]]:
    slot_pods: dict[str, dict[str, Any]] = {}
    for pod in pods:
        slot = _prod_manual_slot_from_pod(pod)
        if not slot:
            continue
        if int(slot) > max_manual_slots:
            raise RunPodProdWorkerError(
                f"managed prod RunPod slot {slot} exceeds "
                f"RUNPOD_PROD_MAX_MANUAL_SLOTS={max_manual_slots}"
            )
        if slot in slot_pods:
            raise RunPodProdWorkerError(
                f"multiple managed prod RunPod pods found for slot {slot}"
            )
        slot_pods[slot] = pod
    return slot_pods


def _prod_manual_slot_from_pod(pod: dict[str, Any]) -> str:
    env = pod.get("env") if isinstance(pod.get("env"), dict) else {}
    for key in ("AGENT_ID", "AGENT_ID_PREFIX"):
        slot = _prod_manual_slot_from_agent_id(str(env.get(key) or ""))
        if slot:
            return slot
    return _prod_manual_slot_from_pod_name(str(pod.get("name") or ""))


def _prod_manual_slot_from_agent_id(agent_id: str) -> str:
    if not agent_id.startswith(RUNPOD_PROD_AGENT_ID_PREFIX):
        return ""
    raw = agent_id.removeprefix(RUNPOD_PROD_AGENT_ID_PREFIX).strip()
    if not raw.isdigit():
        return ""
    value = int(raw, 10)
    if value < 1:
        return ""
    return f"{value:02d}"


def _prod_manual_slot_from_pod_name(name: str) -> str:
    if not name.startswith(RUNPOD_PROD_POD_NAME_PREFIX):
        return ""
    raw = name.removeprefix(RUNPOD_PROD_POD_NAME_PREFIX).strip()
    if not raw.isdigit():
        return ""
    value = int(raw, 10)
    if value < 1:
        return ""
    return f"{value:02d}"


def _prod_slot_sequence(count: int) -> list[str]:
    return [f"{index:02d}" for index in range(1, count + 1)]


def _slot_sort_key(slot: str) -> int:
    return int(slot)


def _find_worker(workers: list[dict[str, Any]], agent_id: str) -> dict[str, Any] | None:
    for worker in workers:
        if str(worker.get("agent_id") or "") == agent_id:
            return worker
    return None


def _find_current_task_worker(workers: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    for worker in workers:
        if str(worker.get("current_task_id") or "") == task_id:
            return worker
    return None


def _worker_supports_img2img(worker: dict[str, Any]) -> bool:
    worker_types = {
        item.strip()
        for item in str(worker.get("types") or "").split(",")
        if item.strip()
    }
    return set(RUNPOD_PROD_SUPPORTED_TASK_TYPES).issubset(worker_types)


def _worker_summary(worker: dict[str, Any] | None) -> dict[str, Any]:
    if not worker:
        return {}
    return {
        "agent_id": worker.get("agent_id"),
        "types": worker.get("types"),
        "status": worker.get("status"),
        "provider": worker.get("provider"),
        "node_id": worker.get("node_id"),
        "runtime_profile": worker.get("runtime_profile"),
        "image_ref": worker.get("image_ref"),
        "current_task_id": worker.get("current_task_id"),
        "current_task_type": worker.get("current_task_type"),
    }
