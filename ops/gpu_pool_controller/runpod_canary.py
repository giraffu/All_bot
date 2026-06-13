from __future__ import annotations

import json
import os
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .providers.runpod import (
    RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX,
    RUNPOD_TASK_PROFILES,
    RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
    RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
    RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX,
    RunPodProvider,
    redact_payload,
    redact_text,
)


EXPECTED_RUNPOD_CLOUD_TEST_CENTRAL_URL = "https://worker-central-test.aivison.it.com"
EXPECTED_MODEL_BUCKET = "allbot-model-cache"
EXPECTED_MODEL_PREFIX = "img2img_lora/2026-06-10"
EXPECTED_MODEL_MANIFEST_KEY = "img2img_lora/2026-06-10/manifest.json"
EXPECTED_WAN22_AIO_VIDEO_MODEL_PREFIX = "wan22_aio_video/2026-06-12-test"
EXPECTED_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY = (
    "wan22_aio_video/2026-06-12-test/manifest.json"
)
EXPECTED_IMAGE_TO_VIDEO_MODEL_PREFIX = RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX
EXPECTED_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY = RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY
EXPECTED_WAN22_VIDEO_V2_MODEL_PREFIX = RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX
EXPECTED_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY = RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY
EXPECTED_TEST_BUCKET = "user-data-test"
EXPECTED_IMAGE_REF_PREFIX = "ghcr.io/giraffu/allbot-comfy-runpod-img2img:"
EXPECTED_WAN22_AIO_VIDEO_IMAGE_REF_PREFIX = (
    "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:"
)
DEFAULT_CONTROL_HOST = "100.82.124.91"
DEFAULT_WORKER_IDS = tuple(f"cloud_worker_test_{index:02d}" for index in range(1, 8))
EXPECTED_TASK_TYPES = ("img2img", "img2img_lora")
EXPECTED_WAN22_AIO_VIDEO_TASK_TYPES = ("image_to_video", "wan22_video_v2")
EXPECTED_WAN22_AIO_VIDEO_GPU_TYPE_IDS = RUNPOD_WAN22_AIO_VIDEO_GPU_TYPE_IDS
TERMINAL_TASK_STATUSES = {"done", "error", "cancelled"}
HEALTHY_WORKER_STATUSES = {"idle", "running"}


class RunPodCanaryError(ValueError):
    pass


@dataclass(frozen=True)
class RunPodCanaryProfileSpec:
    task_type: str
    image_ref_prefix: str
    supported_task_types: tuple[str, ...]
    model_prefix: str
    model_manifest_key: str
    allow_template_id: bool = False
    expected_gpu_type_ids: tuple[str, ...] = ()
    task_summary: str = ""
    worker_disable_summary: str = ""


RUNPOD_CANARY_PROFILE_SPECS: dict[str, RunPodCanaryProfileSpec] = {
    "img2img_lora": RunPodCanaryProfileSpec(
        task_type="img2img_lora",
        image_ref_prefix=EXPECTED_IMAGE_REF_PREFIX,
        supported_task_types=EXPECTED_TASK_TYPES,
        model_prefix=EXPECTED_MODEL_PREFIX,
        model_manifest_key=EXPECTED_MODEL_MANIFEST_KEY,
        task_summary="submit img2img and two img2img_lora Web tasks serially",
        worker_disable_summary="temporarily disable cloud_worker_test_01..07",
    ),
    "wan22_aio_video": RunPodCanaryProfileSpec(
        task_type="wan22_aio_video",
        image_ref_prefix=EXPECTED_WAN22_AIO_VIDEO_IMAGE_REF_PREFIX,
        supported_task_types=EXPECTED_WAN22_AIO_VIDEO_TASK_TYPES,
        model_prefix=EXPECTED_WAN22_AIO_VIDEO_MODEL_PREFIX,
        model_manifest_key=EXPECTED_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY,
        allow_template_id=True,
        expected_gpu_type_ids=EXPECTED_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
        task_summary="submit image_to_video and wan22_video_v2 preview/5s Web tasks serially",
        worker_disable_summary="temporarily disable cloud-test workers supporting image_to_video or wan22_video_v2",
    ),
    "image_to_video": RunPodCanaryProfileSpec(
        task_type="image_to_video",
        image_ref_prefix=EXPECTED_WAN22_AIO_VIDEO_IMAGE_REF_PREFIX,
        supported_task_types=("image_to_video",),
        model_prefix=EXPECTED_IMAGE_TO_VIDEO_MODEL_PREFIX,
        model_manifest_key=EXPECTED_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
        allow_template_id=True,
        expected_gpu_type_ids=EXPECTED_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
        task_summary="submit image_to_video preview/5s Web task",
        worker_disable_summary="temporarily disable cloud-test workers supporting image_to_video",
    ),
    "wan22_video_v2": RunPodCanaryProfileSpec(
        task_type="wan22_video_v2",
        image_ref_prefix=EXPECTED_WAN22_AIO_VIDEO_IMAGE_REF_PREFIX,
        supported_task_types=("wan22_video_v2",),
        model_prefix=EXPECTED_WAN22_VIDEO_V2_MODEL_PREFIX,
        model_manifest_key=EXPECTED_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
        allow_template_id=True,
        expected_gpu_type_ids=EXPECTED_WAN22_AIO_VIDEO_GPU_TYPE_IDS,
        task_summary="submit wan22_video_v2 preview/5s Web task",
        worker_disable_summary="temporarily disable cloud-test workers supporting wan22_video_v2",
    ),
}


@dataclass(frozen=True)
class RunPodCanaryOptions:
    task_type: str = "img2img_lora"
    environment: str = "cloud-test"
    execute: bool = False
    cleanup: bool = True
    disable_workers: bool = True
    worker_ids: tuple[str, ...] = DEFAULT_WORKER_IDS
    worker_ids_explicit: bool = False
    web_api_url: str = ""
    central_url: str = ""
    web_user_id: int = 3
    web_pwd_ver: int = 1
    web_bearer_token: str = ""
    agent_token: str = ""
    input_object_key: str = ""
    output_dir: Path = Path("/tmp/allbot_runpod_canary")
    download_results_dir: Path | None = None
    readiness_timeout_seconds: float = 900.0
    worker_timeout_seconds: float = 600.0
    task_timeout_seconds: float = 1800.0
    poll_interval_seconds: float = 10.0
    task_poll_interval_seconds: float = 5.0
    control_ttl_seconds: int = 3600
    reuse_pod_ids: dict[str, str] = field(default_factory=dict)
    prompt: str = "clean canary image transform, natural lighting, high quality"
    negative_prompt: str = "low quality, artifacts, text, watermark"
    quiet: bool = False


def load_env_file(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"loaded": False, "path": None}
    if not path.exists():
        raise RunPodCanaryError(f"env file not found: {path}")
    try:
        from dotenv import load_dotenv
    except Exception:
        _load_env_file_fallback(path)
    else:
        load_dotenv(path, override=False)
    return {"loaded": True, "path": str(path)}


def options_from_args_env(args: Any) -> RunPodCanaryOptions:
    control_host = (
        os.getenv("RUNPOD_CANARY_CONTROL_HOST")
        or os.getenv("CLOUD_TEST_CONTROL_HOST")
        or os.getenv("CLOUD_TEST_TAILSCALE_IP")
        or DEFAULT_CONTROL_HOST
    )
    arg_worker_ids = getattr(args, "worker_id", None)
    env_worker_ids = _worker_ids_from_env()
    worker_ids = tuple(arg_worker_ids or env_worker_ids)
    worker_ids_explicit = bool(arg_worker_ids) or bool(
        os.getenv("RUNPOD_CANARY_WORKER_IDS", "").strip()
    )
    return RunPodCanaryOptions(
        task_type=getattr(args, "task_type", "img2img_lora"),
        environment=getattr(args, "env", "cloud-test"),
        execute=bool(getattr(args, "execute", False)),
        cleanup=bool(getattr(args, "cleanup", True)),
        disable_workers=bool(getattr(args, "disable_workers", True)),
        worker_ids=worker_ids or DEFAULT_WORKER_IDS,
        worker_ids_explicit=worker_ids_explicit,
        web_api_url=(
            getattr(args, "web_api_url", None)
            or os.getenv("RUNPOD_CANARY_WEB_API_URL")
            or f"http://{control_host}:8001/api"
        ).rstrip("/"),
        central_url=(
            getattr(args, "central_url", None)
            or os.getenv("RUNPOD_CANARY_CENTRAL_URL")
            or f"http://{control_host}:8004"
        ).rstrip("/"),
        web_user_id=int(
            getattr(args, "web_user_id", None)
            or os.getenv("RUNPOD_CANARY_WEB_USER_ID")
            or "3"
        ),
        web_pwd_ver=int(
            getattr(args, "web_pwd_ver", None)
            or os.getenv("RUNPOD_CANARY_WEB_PWD_VER")
            or "1"
        ),
        web_bearer_token=os.getenv("RUNPOD_CANARY_WEB_BEARER_TOKEN", ""),
        agent_token=os.getenv("RUNPOD_CANARY_AGENT_TOKEN")
        or os.getenv("AGENT_SECRET_TOKEN", ""),
        input_object_key=(
            getattr(args, "input_object_key", None)
            or os.getenv("RUNPOD_CANARY_INPUT_OBJECT_KEY")
            or ""
        ),
        output_dir=Path(
            getattr(args, "output_dir", None)
            or os.getenv("RUNPOD_CANARY_OUTPUT_DIR")
            or "/tmp/allbot_runpod_canary"
        ),
        download_results_dir=_optional_path(
            getattr(args, "download_results_dir", None)
            or os.getenv("RUNPOD_CANARY_DOWNLOAD_RESULTS_DIR")
        ),
        readiness_timeout_seconds=float(getattr(args, "readiness_timeout", 900.0)),
        worker_timeout_seconds=float(getattr(args, "worker_timeout", 600.0)),
        task_timeout_seconds=float(getattr(args, "task_timeout", 1800.0)),
        poll_interval_seconds=float(getattr(args, "poll_interval", 10.0)),
        task_poll_interval_seconds=float(getattr(args, "task_poll_interval", 5.0)),
        control_ttl_seconds=int(getattr(args, "control_ttl", 3600)),
        reuse_pod_ids=_reuse_pod_ids_from_args_env(args),
        prompt=(
            getattr(args, "prompt", None)
            or os.getenv("RUNPOD_CANARY_PROMPT")
            or RunPodCanaryOptions.prompt
        ),
        negative_prompt=(
            getattr(args, "negative_prompt", None)
            or os.getenv("RUNPOD_CANARY_NEGATIVE_PROMPT")
            or RunPodCanaryOptions.negative_prompt
        ),
        quiet=bool(getattr(args, "quiet", False)),
    )


def _load_env_file_fallback(path: Path) -> None:
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
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_env_quotes(value.strip())


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _worker_ids_from_env() -> tuple[str, ...]:
    raw = os.getenv("RUNPOD_CANARY_WORKER_IDS", "")
    if not raw.strip():
        return DEFAULT_WORKER_IDS
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _reuse_pod_ids_from_args_env(args: Any) -> dict[str, str]:
    raw_values = list(getattr(args, "reuse_pod_id", None) or [])
    raw_env = os.getenv("RUNPOD_CANARY_REUSE_POD_IDS", "")
    if raw_env.strip():
        raw_values.extend(item.strip() for item in raw_env.split(",") if item.strip())
    reuse_pod_ids: dict[str, str] = {}
    for raw_value in raw_values:
        if "=" not in raw_value:
            raise RunPodCanaryError(
                "--reuse-pod-id must use PROFILE=POD_ID, for example "
                "wan22_video_v2=abc123"
            )
        profile, pod_id = (part.strip() for part in raw_value.split("=", 1))
        if not profile or not pod_id:
            raise RunPodCanaryError(
                "--reuse-pod-id must include both profile and pod id"
            )
        reuse_pod_ids[profile] = pod_id
    return reuse_pod_ids


def _optional_path(value: Any) -> Path | None:
    if value is None:
        return None
    raw = str(value).strip()
    return Path(raw) if raw else None


class RunPodCanaryRunner:
    def __init__(
        self,
        provider: RunPodProvider,
        options: RunPodCanaryOptions,
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
            "execute": self.options.execute,
            "environment": self.options.environment,
            "task_type": self.options.task_type,
            "started_at": _utc_now_iso(),
            "phases": [],
            "cleanup": {
                "requested": self.options.cleanup,
                "worker_restore": [],
            },
        }
        pod_id: str | None = None
        worker_controls: list[dict[str, Any]] = []
        try:
            self._validate_static_options()
            self._run_runpod_preflight(summary)
            if not self.options.execute:
                spec = _canary_profile_spec(self.options.task_type)
                summary["ok"] = True
                summary["would_execute"] = [
                    "create one RunPod cloud-test pod",
                    "wait for infrastructure readiness and Central worker heartbeat",
                    spec.worker_disable_summary,
                    "upload or reuse one test PNG object in user-data-test",
                    spec.task_summary,
                    "optionally download generated results to a local directory",
                    "restore test workers and delete the RunPod pod",
                ]
            else:
                self._run_web_preflight(summary)
                create_payload = self._create_pod(summary)
                pod_id = _extract_pod_id(create_payload)
                summary["pod"] = _pod_summary(
                    create_payload, self._render_image_ref(summary)
                )
                self._wait_pod_readiness(pod_id, summary)
                runpod_worker = self._wait_runpod_worker(pod_id, summary)

                if self.options.disable_workers:
                    worker_controls = self._disable_test_workers(summary)

                image_object_key = self._resolve_canary_image(summary)
                summary["test_input"] = {"object_key": image_object_key}
                summary["tasks"] = []
                for task_case in self._task_cases(image_object_key):
                    task_result = self._run_task_case(task_case, runpod_worker, summary)
                    summary["tasks"].append(task_result)

                summary["ok"] = True
        except KeyboardInterrupt:
            summary["ok"] = False
            summary["error"] = "interrupted"
        except Exception as exc:
            summary["ok"] = False
            summary["error"] = redact_text(str(exc))
        finally:
            if self.options.execute:
                self._cleanup(
                    summary=summary,
                    pod_id=pod_id,
                    worker_controls=worker_controls,
                )
        return self._finish(summary)

    def _validate_static_options(self) -> None:
        if self.options.environment != "cloud-test":
            raise RunPodCanaryError("runpod canary only supports --env cloud-test")
        if self.options.task_type not in RUNPOD_TASK_PROFILES:
            supported = ", ".join(sorted(RUNPOD_TASK_PROFILES))
            raise RunPodCanaryError(f"runpod canary only supports: {supported}")
        if self.options.execute:
            settings = self.provider.settings
            missing_gates: list[str] = []
            if settings.dry_run:
                missing_gates.append("RUNPOD_DRY_RUN=false")
            if not settings.autoscaler_enabled:
                missing_gates.append("RUNPOD_AUTOSCALER_ENABLED=true")
            if settings.max_pods_total != 1:
                missing_gates.append("RUNPOD_MAX_PODS_TOTAL=1")
            if settings.max_pods_per_type != 1:
                missing_gates.append("RUNPOD_MAX_PODS_PER_TYPE=1")
            if missing_gates:
                raise RunPodCanaryError(
                    "execute requires RunPod canary gates: " + ", ".join(missing_gates)
                )
            if self.options.disable_workers and not self.options.agent_token:
                raise RunPodCanaryError(
                    "AGENT_SECRET_TOKEN is required to disable/restore test workers"
                )

    def _run_runpod_preflight(self, summary: dict[str, Any]) -> None:
        self._phase(summary, "runpod_validate_key", "running")
        validate = self.provider.validate_key()
        self._require_ok(validate, "runpod validate-key failed")
        self._phase(summary, "runpod_validate_key", "ok")

        self._phase(summary, "runpod_list_pods", "running")
        listed = self.provider.list_pods(managed_only=True)
        self._require_ok(listed, "runpod list-pods failed")
        if self.options.execute and int(listed.get("count") or 0) != 0:
            raise RunPodCanaryError(
                "refusing canary: managed RunPod pod count is not 0"
            )
        self._phase(
            summary,
            "runpod_list_pods",
            "ok",
            {"count": listed.get("count", 0)},
        )

        self._phase(summary, "runpod_reconcile", "running")
        reconcile = self.provider.reconcile_managed_pods()
        self._require_ok(reconcile, "runpod reconcile-managed-pods failed")
        if self.options.execute and int(reconcile.get("managed_count") or 0) != 0:
            raise RunPodCanaryError(
                "refusing canary: managed RunPod reconcile count is not 0"
            )
        self._phase(
            summary,
            "runpod_reconcile",
            "ok",
            {
                "managed_count": reconcile.get("managed_count", 0),
                "orphans": reconcile.get("orphans", []),
            },
        )

        self._phase(summary, "runpod_render_create", "running")
        render = self.provider.render_create_pod_request(
            task_type=self.options.task_type,
            environment=self.options.environment,
            redact=False,
        )
        self._validate_render(render)
        summary["render"] = self._render_summary(render)
        self._phase(summary, "runpod_render_create", "ok", summary["render"])

    def _run_web_preflight(self, summary: dict[str, Any]) -> None:
        self._phase(summary, "web_and_central_preflight", "running")
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
            "web_and_central_preflight",
            "ok",
            {
                "web_api_url": self.options.web_api_url,
                "central_url": self.options.central_url,
                "web_user_id": self.options.web_user_id,
            },
        )

    def _create_pod(self, summary: dict[str, Any]) -> dict[str, Any]:
        self._phase(summary, "runpod_create_pod", "running")
        payload = self.provider.create_pod(
            task_type=self.options.task_type,
            environment=self.options.environment,
            execute=True,
        )
        self._require_ok(payload, "runpod create-pod failed")
        pod_id = _extract_pod_id(payload)
        self._phase(summary, "runpod_create_pod", "ok", {"pod_id": pod_id})
        return payload

    def _wait_pod_readiness(self, pod_id: str, summary: dict[str, Any]) -> None:
        self._phase(summary, "pod_readiness", "running", {"pod_id": pod_id})
        deadline = time.monotonic() + self.options.readiness_timeout_seconds
        last_payload: dict[str, Any] | None = None
        while time.monotonic() <= deadline:
            payload = self.provider.pod_readiness(pod_id=pod_id)
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
        raise RunPodCanaryError(
            "pod readiness timeout: "
            + json.dumps(redact_payload(last_payload), ensure_ascii=False)
        )

    def _wait_runpod_worker(
        self, pod_id: str, summary: dict[str, Any]
    ) -> dict[str, Any]:
        profile = RUNPOD_TASK_PROFILES[self.options.task_type]
        expected_agent_id = f"{profile.agent_id_prefix}_{pod_id}"
        self._phase(
            summary, "central_runpod_worker", "running", {"agent_id": expected_agent_id}
        )
        deadline = time.monotonic() + self.options.worker_timeout_seconds
        last_workers: list[dict[str, Any]] = []
        while time.monotonic() <= deadline:
            workers = self._fetch_workers()
            last_workers = workers
            worker = _find_runpod_worker(
                workers,
                expected_agent_id=expected_agent_id,
                agent_id_prefix=profile.agent_id_prefix,
            )
            if worker and _worker_supports_expected_types(
                worker,
                expected_types=_expected_task_types(self.options.task_type),
            ):
                status = str(worker.get("status") or "")
                if status in HEALTHY_WORKER_STATUSES:
                    summary["runpod_worker"] = _worker_summary(worker)
                    self._phase(
                        summary, "central_runpod_worker", "ok", summary["runpod_worker"]
                    )
                    return worker
            self._sleep(self.options.poll_interval_seconds)
        raise RunPodCanaryError(
            "runpod worker heartbeat timeout: "
            + json.dumps(
                {
                    "expected_agent_id": expected_agent_id,
                    "runpod_workers": [
                        _worker_summary(worker)
                        for worker in last_workers
                        if str(worker.get("agent_id") or "").startswith(
                            f"{profile.agent_id_prefix}_"
                        )
                    ],
                },
                ensure_ascii=False,
            )
        )

    def _disable_test_workers(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        self._phase(summary, "disable_test_workers", "running")
        controls: list[dict[str, Any]] = []
        agent_ids = self._worker_ids_to_disable()
        for agent_id in agent_ids:
            current = self._get_agent_control(agent_id)
            controls.append(
                {
                    "agent_id": agent_id,
                    "state": current.get("state", "enabled"),
                    "reason": current.get("reason", ""),
                }
            )
            self._set_agent_control(
                agent_id,
                "disabled",
                reason="runpod_canary",
                ttl_seconds=self.options.control_ttl_seconds,
            )
        self._phase(
            summary,
            "disable_test_workers",
            "ok",
            {"disabled": [item["agent_id"] for item in controls]},
        )
        return controls

    def _worker_ids_to_disable(self) -> tuple[str, ...]:
        profile = RUNPOD_TASK_PROFILES[self.options.task_type]
        if profile.task_type == "img2img_lora" or self.options.worker_ids_explicit:
            return self.options.worker_ids
        expected_types = _expected_task_types(self.options.task_type)
        return tuple(
            str(worker.get("agent_id") or "")
            for worker in self._fetch_workers()
            if _is_cloud_test_non_runpod_worker(worker)
            and _worker_supports_any_expected_type(
                worker, expected_types=expected_types
            )
        )

    def _upload_canary_image(self, summary: dict[str, Any]) -> str:
        self._phase(summary, "upload_test_image", "running")
        self.options.output_dir.mkdir(parents=True, exist_ok=True)
        image_path = self.options.output_dir / f"runpod_canary_{int(time.time())}.png"
        write_canary_png(image_path)
        presign = self._http_json(
            "GET",
            _join_url(self.options.web_api_url, "storage", "presigned-url"),
            params={
                "filename": image_path.name,
                "content_type": "image/png",
            },
            headers=self._web_auth_headers(),
        )
        object_key = str(presign.get("object_key") or "")
        upload_url = str(presign.get("upload_url") or "")
        if not object_key or not upload_url:
            raise RunPodCanaryError(
                "presigned upload response missing object_key/upload_url"
            )
        self._http_bytes(
            "PUT",
            upload_url,
            body=image_path.read_bytes(),
            headers={"Content-Type": "image/png"},
            expected_statuses=(200, 201, 204),
        )
        self._phase(summary, "upload_test_image", "ok", {"object_key": object_key})
        return object_key

    def _resolve_canary_image(self, summary: dict[str, Any]) -> str:
        object_key = self.options.input_object_key.strip()
        if object_key:
            self._phase(summary, "reuse_test_image", "ok", {"object_key": object_key})
            return object_key
        return self._upload_canary_image(summary)

    def _run_task_case(
        self,
        task_case: dict[str, Any],
        runpod_worker: dict[str, Any],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        label = str(task_case["label"])
        self._phase(summary, f"task_{label}", "running")
        submit_payload = self._http_json(
            "POST",
            _join_url(self.options.web_api_url, "tasks", "generate"),
            json_body=task_case["payload"],
            headers=self._web_auth_headers(),
        )
        task_id = str(submit_payload.get("task_id") or "")
        if not task_id:
            raise RunPodCanaryError(f"{label}: missing task_id in Web response")
        final_status, pop_evidence = self._wait_task_done(
            task_id=task_id,
            expected_worker_id=str(runpod_worker.get("agent_id") or ""),
        )
        task_result = {
            "label": label,
            "registry_task_id": task_id,
            "task_type": task_case["payload"]["task_type"],
            "lora_name": task_case.get("lora_name") or "",
            "central_status": final_status.get("status"),
            "central_task_type": final_status.get("task_type"),
            "pop_evidence": pop_evidence,
        }
        if final_status.get("status") != "done":
            raise RunPodCanaryError(
                f"{label}: Central terminal status is {final_status.get('status')}"
            )
        result_payload = self._wait_web_result(task_id)
        result_url = str(result_payload.get("result_url") or "")
        task_result["web_result_status"] = result_payload.get("status")
        task_result["result_path"] = result_url_path(result_url)
        if result_payload.get("status") != "success" or not result_url:
            raise RunPodCanaryError(f"{label}: Web result did not become success")
        downloaded = self._download_result_if_requested(
            label=label,
            task_id=task_id,
            result_url=result_url,
        )
        if downloaded:
            task_result.update(downloaded)
        last_frame_result = self._validate_wan22_last_frame_if_required(
            label=label,
            task_id=task_id,
            result_payload=result_payload,
        )
        if last_frame_result:
            task_result.update(last_frame_result)
        self._phase(summary, f"task_{label}", "ok", task_result)
        return task_result

    def _fetch_result_bytes(self, result_url: str) -> tuple[bytes, str]:
        method = "public_url"
        try:
            response = self._http_request(
                "GET",
                result_url,
                headers={"User-Agent": "AllBot-RunPod-Canary/1.0"},
                expected_statuses=(200,),
            )
            raw = response["raw"]
        except Exception:
            method = "r2_s3"
            raw = self._download_result_bytes_from_s3(result_url)
        if not raw:
            raise RunPodCanaryError(
                f"downloaded result is empty: {_safe_url(result_url)}"
            )
        return raw, method

    def _download_result_if_requested(
        self,
        *,
        label: str,
        task_id: str,
        result_url: str,
    ) -> dict[str, str]:
        if self.options.download_results_dir is None:
            return {}
        download_dir = self.options.download_results_dir
        download_dir.mkdir(parents=True, exist_ok=True)
        parsed = urllib.parse.urlsplit(result_url)
        suffix = Path(parsed.path).suffix or ".bin"
        target = download_dir / f"{label}_{task_id}{suffix}"
        raw, method = self._fetch_result_bytes(result_url)
        target.write_bytes(raw)
        return {"downloaded_file": str(target), "download_method": method}

    def _validate_wan22_last_frame_if_required(
        self,
        *,
        label: str,
        task_id: str,
        result_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self.options.task_type != "wan22_aio_video":
            return {}
        extra_outputs = result_payload.get("extra_outputs")
        last_frame = (
            extra_outputs.get("last_frame") if isinstance(extra_outputs, dict) else None
        )
        if not isinstance(last_frame, dict):
            raise RunPodCanaryError(f"{label}: missing extra_outputs.last_frame")
        last_frame_url = str(last_frame.get("url") or last_frame.get("path") or "")
        if not last_frame_url:
            raise RunPodCanaryError(f"{label}: last_frame is missing url/path")
        raw, method = self._fetch_result_bytes(last_frame_url)
        result: dict[str, Any] = {
            "last_frame_path": result_url_path(last_frame_url),
            "last_frame_bytes": len(raw),
            "last_frame_download_method": method,
        }
        if self.options.download_results_dir is not None:
            download_dir = self.options.download_results_dir
            download_dir.mkdir(parents=True, exist_ok=True)
            parsed = urllib.parse.urlsplit(last_frame_url)
            suffix = Path(parsed.path).suffix or ".png"
            target = download_dir / f"{label}_{task_id}_last_frame{suffix}"
            target.write_bytes(raw)
            result["last_frame_downloaded_file"] = str(target)
        return result

    def _download_result_bytes_from_s3(self, result_url: str) -> bytes:
        object_key = result_url_path(result_url).lstrip("/")
        if not object_key:
            raise RunPodCanaryError("result URL did not contain an object key path")
        endpoint = os.getenv("MINIO_ENDPOINT", "").strip()
        access_key = os.getenv("MINIO_ACCESS_KEY", "").strip()
        secret_key = os.getenv("MINIO_SECRET_KEY", "").strip()
        bucket = os.getenv("MINIO_RESULT_BUCKET", EXPECTED_TEST_BUCKET).strip()
        secure = os.getenv("MINIO_SECURE", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not endpoint or not access_key or not secret_key or not bucket:
            raise RunPodCanaryError(
                "R2 S3 fallback is missing MINIO endpoint/credentials/bucket"
            )
        endpoint_url = endpoint
        if "://" not in endpoint_url:
            endpoint_url = f"{'https' if secure else 'http'}://{endpoint_url}"
        try:
            import boto3
        except Exception as exc:
            raise RunPodCanaryError(
                f"boto3 is required for R2 S3 result download: {exc}"
            ) from exc
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
            raise RunPodCanaryError(
                f"R2 S3 result download failed for {object_key}: {exc}"
            ) from exc
        return body

    def _wait_task_done(
        self,
        *,
        task_id: str,
        expected_worker_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        deadline = time.monotonic() + self.options.task_timeout_seconds
        last_status: dict[str, Any] = {}
        pop_evidence: dict[str, Any] = {
            "observed": False,
            "expected_agent_id": expected_worker_id,
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
            current_worker = _find_worker_current_task(
                workers, expected_worker_id, task_id
            )
            if current_worker:
                pop_evidence = {
                    "observed": True,
                    "agent_id": current_worker.get("agent_id"),
                    "current_task_id": current_worker.get("current_task_id"),
                    "current_task_type": current_worker.get("current_task_type"),
                    "status": current_worker.get("status"),
                }
            status = str(last_status.get("status") or "")
            if status in TERMINAL_TASK_STATUSES:
                if not pop_evidence["observed"]:
                    pop_evidence["agent_id"] = expected_worker_id
                    pop_evidence["note"] = "not_observed_during_poll"
                return last_status, pop_evidence
            self._sleep(self.options.task_poll_interval_seconds)
        raise RunPodCanaryError(
            f"task timeout: {task_id} last_status="
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
        raise RunPodCanaryError(
            f"web result timeout: {task_id} last_result="
            + json.dumps(redact_payload(last_result), ensure_ascii=False)
        )

    def _cleanup(
        self,
        *,
        summary: dict[str, Any],
        pod_id: str | None,
        worker_controls: list[dict[str, Any]],
    ) -> None:
        cleanup = summary.setdefault("cleanup", {})
        cleanup_errors: list[str] = []
        if worker_controls:
            for control in worker_controls:
                agent_id = str(control.get("agent_id") or "")
                state = str(control.get("state") or "enabled")
                reason = str(control.get("reason") or "runpod_canary_restore")
                try:
                    self._set_agent_control(agent_id, state, reason=reason)
                    cleanup.setdefault("worker_restore", []).append(
                        {"agent_id": agent_id, "state": state, "ok": True}
                    )
                except Exception as exc:
                    cleanup_errors.append(
                        f"restore {agent_id}: {redact_text(str(exc))}"
                    )
                    cleanup.setdefault("worker_restore", []).append(
                        {"agent_id": agent_id, "state": state, "ok": False}
                    )
        if pod_id and self.options.cleanup:
            try:
                delete_payload = self.provider.delete_pod(
                    pod_id=pod_id,
                    task_type=self.options.task_type,
                    execute=True,
                )
                if not delete_payload.get("ok"):
                    raise RunPodCanaryError(
                        str(delete_payload.get("error") or "delete failed")
                    )
                cleanup["pod_delete"] = {"pod_id": pod_id, "ok": True}
            except Exception as exc:
                cleanup_errors.append(f"delete pod {pod_id}: {redact_text(str(exc))}")
                cleanup["pod_delete"] = {"pod_id": pod_id, "ok": False}
        elif pod_id:
            cleanup["pod_delete"] = {"pod_id": pod_id, "ok": False, "skipped": True}
        try:
            listed = self.provider.list_pods(managed_only=True)
            reconcile = self.provider.reconcile_managed_pods()
            cleanup["post_list_pods"] = {
                "ok": listed.get("ok"),
                "count": listed.get("count"),
            }
            cleanup["post_reconcile"] = {
                "ok": reconcile.get("ok"),
                "managed_count": reconcile.get("managed_count"),
            }
        except Exception as exc:
            cleanup_errors.append(f"post cleanup reconcile: {redact_text(str(exc))}")
        if cleanup_errors:
            cleanup["errors"] = cleanup_errors
            summary["ok"] = False
            summary["error"] = summary.get("error") or "cleanup failed"

    def _task_cases(self, image_object_key: str) -> list[dict[str, Any]]:
        profile = RUNPOD_TASK_PROFILES[self.options.task_type]
        if profile.task_type == "wan22_aio_video":
            return self._wan22_aio_video_task_cases(image_object_key)
        return self._img2img_task_cases(image_object_key)

    def _img2img_task_cases(self, image_object_key: str) -> list[dict[str, Any]]:
        base_inputs = {
            "images": [image_object_key],
            "image": image_object_key,
            "num_inference_steps": 6,
            "guidance_scale": 1.0,
            "seed": 20260612,
        }
        return [
            {
                "label": "img2img_plain",
                "payload": {
                    "task_type": "img2img",
                    "inputs": dict(base_inputs),
                    "prompt": self.options.prompt,
                    "negative_prompt": self.options.negative_prompt,
                    "priority": 0,
                },
            },
            {
                "label": "img2img_lora_yarn",
                "lora_name": "qwen/YARN_1.0.safetensors",
                "payload": {
                    "task_type": "img2img_lora",
                    "inputs": {
                        **base_inputs,
                        "lora_name": "qwen/YARN_1.0.safetensors",
                        "lora_strength": 0.65,
                    },
                    "prompt": self.options.prompt,
                    "negative_prompt": self.options.negative_prompt,
                    "priority": 0,
                },
            },
            {
                "label": "img2img_lora_realistic_texture",
                "lora_name": "qwen/realistic_texture.safetensors",
                "payload": {
                    "task_type": "img2img_lora",
                    "inputs": {
                        **base_inputs,
                        "lora_name": "qwen/realistic_texture.safetensors",
                        "lora_strength": 0.65,
                    },
                    "prompt": self.options.prompt,
                    "negative_prompt": self.options.negative_prompt,
                    "priority": 0,
                },
            },
        ]

    def _wan22_aio_video_task_cases(
        self, image_object_key: str
    ) -> list[dict[str, Any]]:
        base_inputs = {
            "images": [image_object_key],
            "image": image_object_key,
            "resolution_preset": "preview",
            "duration_seconds": 5,
            "extract_last_frame": True,
            "seed": 20260612,
        }
        return [
            {
                "label": "image_to_video_preview_5s",
                "payload": {
                    "task_type": "image_to_video",
                    "inputs": {
                        **base_inputs,
                        "wan22_model_profile": "legacy_image_to_video",
                    },
                    "prompt": self.options.prompt,
                    "negative_prompt": self.options.negative_prompt,
                    "priority": 0,
                },
            },
            {
                "label": "wan22_video_v2_preview_5s",
                "payload": {
                    "task_type": "wan22_video_v2",
                    "inputs": {
                        **base_inputs,
                        "wan22_model_profile": "wan22_video_v2",
                    },
                    "prompt": self.options.prompt,
                    "negative_prompt": self.options.negative_prompt,
                    "priority": 0,
                },
            },
        ]

    def _validate_render(self, render: dict[str, Any]) -> None:
        spec = _canary_profile_spec(self.options.task_type)
        body = render.get("json") or {}
        env = body.get("env") or {}
        failures: list[str] = []
        image_name = str(body.get("imageName") or "")
        template_id = str(body.get("templateId") or "")
        if template_id and not spec.allow_template_id:
            failures.append("templateId must be empty for baked GHCR canary")
        if image_name and not image_name.startswith(spec.image_ref_prefix):
            failures.append(
                f"imageName must use public GHCR prefix {spec.image_ref_prefix}"
            )
        if not template_id and not image_name.startswith(spec.image_ref_prefix):
            failures.append(
                f"imageName must use public GHCR prefix {spec.image_ref_prefix}"
            )
        if (
            spec.expected_gpu_type_ids
            and tuple(body.get("gpuTypeIds") or ()) != spec.expected_gpu_type_ids
        ):
            failures.append(
                "gpuTypeIds must be " + ",".join(spec.expected_gpu_type_ids)
            )
        expected_env = {
            "CENTRAL_API_URL": EXPECTED_RUNPOD_CLOUD_TEST_CENTRAL_URL,
            "SUPPORTED_TASK_TYPES": ",".join(spec.supported_task_types),
            "MINIO_INPUT_BUCKET": EXPECTED_TEST_BUCKET,
            "MINIO_RESULT_BUCKET": EXPECTED_TEST_BUCKET,
            "MINIO_TEMPLATE_BUCKET": EXPECTED_TEST_BUCKET,
            "RUNPOD_MODEL_SYNC_ENABLED": "true",
            "RUNPOD_MODEL_BUCKET": EXPECTED_MODEL_BUCKET,
            "RUNPOD_MODEL_PREFIX": spec.model_prefix,
            "RUNPOD_MODEL_MANIFEST_KEY": spec.model_manifest_key,
            "RUNPOD_COMFY_CUSTOM_NODES_ENABLED": "false",
            "RUNPOD_COMFY_KJNODES_ENABLED": "false",
        }
        for key, expected in expected_env.items():
            if str(env.get(key) or "") != expected:
                failures.append(f"{key} must be {expected}")
        for key in (
            "AGENT_SECRET_TOKEN",
            "MINIO_ACCESS_KEY",
            "MINIO_SECRET_KEY",
            "RUNPOD_MODEL_ACCESS_KEY",
            "RUNPOD_MODEL_SECRET_KEY",
        ):
            value = str(env.get(key) or "")
            if not value.startswith("{{ RUNPOD_SECRET_"):
                failures.append(f"{key} must use a RunPod secret reference")
        if failures:
            raise RunPodCanaryError(
                "render-create sanity check failed: " + "; ".join(failures)
            )

    def _render_summary(self, render: dict[str, Any]) -> dict[str, Any]:
        body = render.get("json") or {}
        env = body.get("env") or {}
        return {
            "imageName": body.get("imageName"),
            "templateId": body.get("templateId"),
            "uses_template": bool(body.get("templateId")),
            "gpu_type_ids": body.get("gpuTypeIds") or [],
            "central_api_url": env.get("CENTRAL_API_URL"),
            "supported_task_types": env.get("SUPPORTED_TASK_TYPES"),
            "model_bucket": env.get("RUNPOD_MODEL_BUCKET"),
            "model_prefix": env.get("RUNPOD_MODEL_PREFIX"),
            "model_manifest_key": env.get("RUNPOD_MODEL_MANIFEST_KEY"),
            "custom_nodes_enabled": env.get("RUNPOD_COMFY_CUSTOM_NODES_ENABLED"),
            "kjnodes_enabled": env.get("RUNPOD_COMFY_KJNODES_ENABLED"),
            "buckets": {
                "input": env.get("MINIO_INPUT_BUCKET"),
                "result": env.get("MINIO_RESULT_BUCKET"),
                "template": env.get("MINIO_TEMPLATE_BUCKET"),
            },
        }

    def _render_image_ref(self, summary: dict[str, Any]) -> str:
        render = summary.get("render") or {}
        return str(render.get("imageName") or "")

    def _get_agent_control(self, agent_id: str) -> dict[str, Any]:
        return self._http_json(
            "GET",
            _join_url(
                self.options.central_url, "api", "agent", "task", "control", agent_id
            ),
            headers=self._agent_headers(),
        )

    def _set_agent_control(
        self,
        agent_id: str,
        state: str,
        *,
        reason: str,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"state": state, "reason": reason}
        if ttl_seconds and state != "enabled":
            body["ttl_seconds"] = ttl_seconds
        return self._http_json(
            "POST",
            _join_url(
                self.options.central_url, "api", "agent", "task", "control", agent_id
            ),
            json_body=body,
            headers=self._agent_headers(),
        )

    def _fetch_workers(self) -> list[dict[str, Any]]:
        payload = self._http_json(
            "GET", _join_url(self.options.central_url, "system", "workers")
        )
        workers = payload.get("workers") or []
        if not isinstance(workers, list):
            raise RunPodCanaryError("Central /system/workers returned non-list workers")
        return [worker for worker in workers if isinstance(worker, dict)]

    def _web_token(self) -> str:
        if self.options.web_bearer_token:
            return self.options.web_bearer_token
        try:
            from src.web_api.core.security import create_access_token
        except Exception as exc:
            raise RunPodCanaryError(f"failed to load Web JWT signer: {exc}") from exc
        return create_access_token(
            subject=str(self.options.web_user_id),
            pwd_ver=self.options.web_pwd_ver,
            channel="runpod_canary",
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
            raise RunPodCanaryError(
                f"invalid JSON response from {method} {_safe_url(url)}"
            ) from exc
        if isinstance(payload, dict):
            payload.setdefault("_status", response["status"])
            return payload
        return {"_status": response["status"], "data": payload}

    def _http_bytes(
        self,
        method: str,
        url: str,
        *,
        body: bytes,
        headers: dict[str, str] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        return self._http_request(
            method,
            url,
            body=body,
            headers=headers or {},
            expected_statuses=expected_statuses,
        )

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
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers=headers or {},
        )
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
                raise RunPodCanaryError(
                    f"{method} {_safe_url(url)} returned HTTP {status}: {redact_text(text[:500])}"
                ) from exc
        except urllib.error.URLError as exc:
            raise RunPodCanaryError(
                f"{method} {_safe_url(url)} network error: {redact_text(str(exc.reason))}"
            ) from exc
        if status not in expected_statuses and status not in allow_statuses:
            raise RunPodCanaryError(
                f"{method} {_safe_url(url)} returned HTTP {status}: {redact_text(text[:500])}"
            )
        return {"status": status, "text": text, "raw": raw}

    def _phase(
        self,
        summary: dict[str, Any],
        name: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        entry = {
            "name": name,
            "status": status,
            "at": _utc_now_iso(),
        }
        if details:
            entry["details"] = redact_payload(details)
        summary.setdefault("phases", []).append(entry)
        if not self.options.quiet:
            self._emit_func(f"[runpod-canary] {name}: {status}")

    @staticmethod
    def _require_ok(payload: dict[str, Any], message: str) -> None:
        if not payload.get("ok"):
            raise RunPodCanaryError(
                f"{message}: {redact_text(str(payload.get('error') or payload))}"
            )

    @staticmethod
    def _finish(summary: dict[str, Any]) -> dict[str, Any]:
        summary["ended_at"] = _utc_now_iso()
        return redact_payload(summary)


def write_canary_png(path: Path, *, width: int = 512, height: int = 512) -> None:
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(
                (
                    72 + (x % 48),
                    126 + (y % 48),
                    168 + ((x + y) % 48),
                )
            )
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(
        _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    )
    png.extend(_png_chunk(b"IDAT", zlib.compress(bytes(rows), level=6)))
    png.extend(_png_chunk(b"IEND", b""))
    path.write_bytes(bytes(png))


def result_url_path(url: str) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme or parsed.netloc:
        return parsed.path
    return urllib.parse.urlunsplit(parsed._replace(query="", fragment=""))


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def _join_url(base: str, *parts: str) -> str:
    return "/".join([base.rstrip("/"), *(part.strip("/") for part in parts if part)])


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _safe_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parsed._replace(query="", fragment=""))


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
    raise RunPodCanaryError("RunPod create response did not include pod id")


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


def _canary_profile_spec(task_type: str) -> RunPodCanaryProfileSpec:
    profile = RUNPOD_TASK_PROFILES[task_type]
    try:
        return RUNPOD_CANARY_PROFILE_SPECS[profile.task_type]
    except KeyError as exc:
        raise RunPodCanaryError(
            f"missing runpod canary profile spec: {profile.task_type}"
        ) from exc


def _expected_task_types(task_type: str) -> tuple[str, ...]:
    return _canary_profile_spec(task_type).supported_task_types


def _worker_types(worker: dict[str, Any]) -> set[str]:
    raw_types = worker.get("types") or worker.get("supported_task_types") or ""
    if isinstance(raw_types, (list, tuple, set)):
        return {str(item).strip() for item in raw_types if str(item).strip()}
    return {item.strip() for item in str(raw_types).split(",") if item.strip()}


def _is_cloud_test_non_runpod_worker(worker: dict[str, Any]) -> bool:
    agent_id = str(worker.get("agent_id") or "")
    provider = str(worker.get("provider") or "").strip().lower()
    return agent_id.startswith("cloud_worker_test_") and provider != "runpod"


def _find_runpod_worker(
    workers: list[dict[str, Any]],
    *,
    expected_agent_id: str,
    agent_id_prefix: str,
) -> dict[str, Any] | None:
    fallback: dict[str, Any] | None = None
    for worker in workers:
        agent_id = str(worker.get("agent_id") or "")
        if agent_id == expected_agent_id:
            return worker
        if agent_id.startswith(f"{agent_id_prefix}_"):
            fallback = worker
    return fallback


def _find_worker_current_task(
    workers: list[dict[str, Any]],
    expected_agent_id: str,
    task_id: str,
) -> dict[str, Any] | None:
    for worker in workers:
        if str(worker.get("agent_id") or "") != expected_agent_id:
            continue
        if str(worker.get("current_task_id") or "") == task_id:
            return worker
    return None


def _worker_supports_expected_types(
    worker: dict[str, Any],
    *,
    expected_types: tuple[str, ...],
) -> bool:
    return set(expected_types).issubset(_worker_types(worker))


def _worker_supports_any_expected_type(
    worker: dict[str, Any],
    *,
    expected_types: tuple[str, ...],
) -> bool:
    return bool(set(expected_types).intersection(_worker_types(worker)))


def _worker_summary(worker: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": worker.get("agent_id"),
        "types": worker.get("types"),
        "status": worker.get("status"),
        "provider": worker.get("provider"),
        "runtime_profile": worker.get("runtime_profile"),
        "image_ref": worker.get("image_ref"),
        "current_task_id": worker.get("current_task_id"),
        "current_task_type": worker.get("current_task_type"),
    }
