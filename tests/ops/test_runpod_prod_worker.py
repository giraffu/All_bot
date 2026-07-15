from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ops.gpu_pool_controller.cli import build_parser
from ops.gpu_pool_controller.providers.runpod import (
    RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX,
    RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY,
    RUNPOD_I2I_PRO_MODEL_PREFIX,
    RUNPOD_I2I_PRO_SUPPORTED_TASK_TYPES,
    RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES,
    RUNPOD_IMG2IMG_LORA_DOCKER_START_CMD,
    RUNPOD_LTX_VIDEO_CONTAINER_DISK_GB,
    RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_LTX_VIDEO_MODEL_PREFIX,
    RUNPOD_LTX_VIDEO_SUPPORTED_TASK_TYPES,
    RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES,
    RUNPOD_PORNMASTER_FLUX2_EDIT_CONTAINER_DISK_GB,
    RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY,
    RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX,
    RUNPOD_PORNMASTER_FLUX2_EDIT_SUPPORTED_TASK_TYPES,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_CONTAINER_DISK_GB,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_COMFY_EXTRA_ARGS,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_GPU_TYPE_IDS,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_MANIFEST_KEY,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_PREFIX,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_SUPPORTED_TASK_TYPES,
    RUNPOD_PROD_AGENT_ID,
    RUNPOD_PROD_GPU_TYPE_IDS,
    RUNPOD_PROD_SUPPORTED_TASK_TYPES,
    RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
    RUNPOD_PUBLIC_LTX_VIDEO_IMAGE_PREFIX,
    RUNPOD_PUBLIC_PORNMASTER_FLUX2_EDIT_IMAGE_PREFIX,
    RUNPOD_PUBLIC_SCAIL2_IMAGE_PREFIX,
    RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE,
    RUNPOD_SCAIL2_MODEL_MANIFEST_KEY,
    RUNPOD_SCAIL2_MODEL_PREFIX,
    RUNPOD_SCAIL2_SUPPORTED_TASK_TYPES,
    RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS,
    RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
    RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX,
    RunPodProvider,
    RunPodSettings,
    prod_agent_id_from_slot,
    prod_pod_name_from_agent_id,
)
from ops.gpu_pool_controller.runpod_prod_worker import (
    RunPodProdWorkerOptions,
    RunPodProdWorkerRunner,
    apply_prod_worker_selection_to_env,
    load_env_file_for_prod_worker,
)

PUBLIC_I2I_PRO_GHCR_IMAGE = (
    "ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:20260614-i2ipro-b75c6a9-cu128-min5-ssh"
)
PUBLIC_SCAIL2_GHCR_IMAGE = (
    RUNPOD_PUBLIC_SCAIL2_IMAGE_PREFIX + "20260617-scail2-prod"
)
PUBLIC_LTX_VIDEO_GHCR_IMAGE = (
    RUNPOD_PUBLIC_LTX_VIDEO_IMAGE_PREFIX + "20260622-ltx-prod"
)
PUBLIC_PORNMASTER_FLUX2_EDIT_GHCR_IMAGE = (
    RUNPOD_PUBLIC_PORNMASTER_FLUX2_EDIT_IMAGE_PREFIX
    + "20260701-pornmaster-flux2-edit"
)


class FakeRunPodProvider:
    def __init__(
        self,
        settings: RunPodSettings | None = None,
        *,
        pods: list[dict] | None = None,
        create_log: list[dict] | None = None,
        delete_log: list[dict] | None = None,
        start_log: list[dict] | None = None,
        stop_log: list[dict] | None = None,
        restart_log: list[dict] | None = None,
    ) -> None:
        self.settings = settings or RunPodSettings(api_key="rp_test_key")
        self.pods = pods if pods is not None else []
        self.create_log = create_log if create_log is not None else []
        self.delete_log = delete_log if delete_log is not None else []
        self.start_log = start_log if start_log is not None else []
        self.stop_log = stop_log if stop_log is not None else []
        self.restart_log = restart_log if restart_log is not None else []
        self.list_calls = 0

    @property
    def create_calls(self) -> int:
        return len(self.create_log)

    @property
    def delete_calls(self) -> int:
        return len(self.delete_log)

    @property
    def start_calls(self) -> int:
        return len(self.start_log)

    @property
    def stop_calls(self) -> int:
        return len(self.stop_log)

    @property
    def restart_calls(self) -> int:
        return len(self.restart_log)

    def validate_key(self):
        return {"ok": True}

    def list_pods(self, *, managed_only=True, desired_status=None):
        self.list_calls += 1
        return {"ok": True, "count": len(self.pods), "pods": list(self.pods)}

    def reconcile_managed_pods(self, pods=None):
        pods = self.pods if pods is None else pods
        return {
            "ok": True,
            "managed_count": len(pods),
            "orphans": [],
            "by_task_type": {"img2img_lora": len(pods)} if pods else {},
        }

    def render_create_pod_request(self, *, task_type, environment, redact=True):
        settings = replace(
            self.settings,
            image_name_img2img_lora=RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
            image_name_i2i_pro=(
                self.settings.image_name_i2i_pro or PUBLIC_I2I_PRO_GHCR_IMAGE
            ),
            image_name_scail2=(
                self.settings.image_name_scail2 or PUBLIC_SCAIL2_GHCR_IMAGE
            ),
            image_name_ltx_video=(
                self.settings.image_name_ltx_video or PUBLIC_LTX_VIDEO_GHCR_IMAGE
            ),
            image_name_pornmaster_flux2_edit=(
                self.settings.image_name_pornmaster_flux2_edit
                or PUBLIC_PORNMASTER_FLUX2_EDIT_GHCR_IMAGE
            ),
            minio_endpoint="https://r2.example.test",
        )
        return RunPodProvider(settings).render_create_pod_request(
            task_type=task_type,
            environment=environment,
            redact=redact,
        )

    def create_pod(self, *, task_type, environment, execute):
        slot = self.settings.prod_agent_id.rsplit("_", 1)[-1]
        runpod_task_type = {
            "image_to_video": "image_to_video",
            "wan22_video_v2": "wan22_video_v2",
            "i2i_pro": "i2i_pro",
            "scail2": "scail2",
            "ltx_video": "ltx_video",
            "pornmaster_flux2_edit": "pornmaster_flux2_edit",
        }.get(task_type, "img2img_lora")
        pod = {
            "id": f"pod-prod-{slot}",
            "name": prod_pod_name_from_agent_id(
                self.settings.prod_agent_id,
                max_manual_slots=self.settings.prod_max_manual_slots,
            ),
            "desiredStatus": "RUNNING",
            "env": {
                "RUNPOD_ENVIRONMENT": "cloud-prod",
                "RUNPOD_TASK_TYPE": runpod_task_type,
                "AGENT_ID": self.settings.prod_agent_id,
                "AGENT_ID_PREFIX": self.settings.prod_agent_id,
            },
        }
        self.create_log.append({"agent_id": self.settings.prod_agent_id, "pod": pod})
        self.pods.append(pod)
        return {
            "ok": True,
            "pod": pod,
        }

    def delete_pod(self, *, pod_id, task_type, execute):
        self.delete_log.append(
            {"pod_id": pod_id, "agent_id": self.settings.prod_agent_id}
        )
        self.pods[:] = [
            pod
            for pod in self.pods
            if str(pod.get("id") or pod.get("podId") or "") != pod_id
        ]
        return {"ok": True}

    def start_pod(self, *, pod_id, task_type, execute):
        self.start_log.append(
            {"pod_id": pod_id, "agent_id": self.settings.prod_agent_id}
        )
        return {"ok": True}

    def stop_pod(self, *, pod_id, task_type, execute):
        self.stop_log.append(
            {"pod_id": pod_id, "agent_id": self.settings.prod_agent_id}
        )
        return {"ok": True}

    def restart_pod(self, *, pod_id, task_type, execute):
        self.restart_log.append(
            {"pod_id": pod_id, "agent_id": self.settings.prod_agent_id}
        )
        return {"ok": True}

    def pod_readiness(self, *, pod_id):
        return {"ok": True, "readiness": {"infrastructure_ready": True}}

    def for_prod_agent_id(self, agent_id: str):
        return FakeRunPodProvider(
            replace(self.settings, prod_agent_id=agent_id),
            pods=self.pods,
            create_log=self.create_log,
            delete_log=self.delete_log,
            start_log=self.start_log,
            stop_log=self.stop_log,
            restart_log=self.restart_log,
        )


class FailingRestartRunPodProvider(FakeRunPodProvider):
    def restart_pod(self, *, pod_id, task_type, execute):
        self.restart_log.append(
            {"pod_id": pod_id, "agent_id": self.settings.prod_agent_id}
        )
        return {"ok": False, "error": "native restart failed after disable"}


class FailingCreateAfterPodRunPodProvider(FakeRunPodProvider):
    def create_pod(self, *, task_type, environment, execute):
        super().create_pod(
            task_type=task_type,
            environment=environment,
            execute=execute,
        )
        return {
            "ok": False,
            "error": "runpod_http_500: Unknown column 'NetworkVolume.userId'",
        }

    def for_prod_agent_id(self, agent_id: str):
        return FailingCreateAfterPodRunPodProvider(
            replace(self.settings, prod_agent_id=agent_id),
            pods=self.pods,
            create_log=self.create_log,
            delete_log=self.delete_log,
            start_log=self.start_log,
            stop_log=self.stop_log,
            restart_log=self.restart_log,
        )


class FailingRenderRunPodProvider(FakeRunPodProvider):
    def render_create_pod_request(self, *, task_type, environment, redact=True):
        raise AssertionError("down should not render a create pod request")

    def for_prod_agent_id(self, agent_id: str):
        return FailingRenderRunPodProvider(
            replace(self.settings, prod_agent_id=agent_id),
            pods=self.pods,
            create_log=self.create_log,
            delete_log=self.delete_log,
            start_log=self.start_log,
            stop_log=self.stop_log,
            restart_log=self.restart_log,
        )


class SlotRaceRunPodProvider(FakeRunPodProvider):
    def __init__(self, *args, stolen_slot: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.stolen_slot = stolen_slot
        self.injected = False

    def list_pods(self, *, managed_only=True, desired_status=None):
        if self.list_calls >= 1 and not self.injected:
            self.pods.append(
                _prod_pod(
                    self.stolen_slot,
                    max_manual_slots=self.settings.prod_max_manual_slots,
                )
            )
            self.injected = True
        return super().list_pods(
            managed_only=managed_only,
            desired_status=desired_status,
        )

    def for_prod_agent_id(self, agent_id: str):
        return SlotRaceRunPodProvider(
            replace(self.settings, prod_agent_id=agent_id),
            pods=self.pods,
            create_log=self.create_log,
            delete_log=self.delete_log,
            start_log=self.start_log,
            stop_log=self.stop_log,
            restart_log=self.restart_log,
            stolen_slot=self.stolen_slot,
        )


class FakeHttpProdWorkerRunner(RunPodProdWorkerRunner):
    def __init__(self, *args, workers=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.http_calls = []
        self.control_calls = []
        self.agent_control = {}
        self.workers = workers if workers is not None else []

    def _http_json(self, method, url, **kwargs):
        self.http_calls.append({"method": method, "url": url, "kwargs": kwargs})
        if "/api/agent/task/control/" in url:
            self.control_calls.append({"method": method, "url": url, "kwargs": kwargs})
            body = kwargs.get("json_body") or {}
            agent_id = url.rstrip("/").rsplit("/", 1)[-1]
            if method == "POST":
                payload = {
                    "agent_id": agent_id,
                    "state": body.get("state", "disabled"),
                    "reason": body.get("reason", ""),
                }
                self.agent_control[agent_id] = payload
                return payload
            return self.agent_control.get(
                agent_id,
                {
                    "agent_id": agent_id,
                    "state": "enabled",
                    "reason": "",
                },
            )
        if url.endswith("/system/workers"):
            return {"workers": list(self.workers)}
        if url.endswith("/health"):
            return {"ok": True}
        return {"ok": True}


def _settings(**overrides) -> RunPodSettings:
    values = {
        "api_key": "rp_test_key",
        "dry_run": True,
        "autoscaler_enabled": False,
        "max_pods_total": 1,
        "max_pods_per_type": 1,
        "image_name_img2img_lora": RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
        "image_name_i2i_pro": PUBLIC_I2I_PRO_GHCR_IMAGE,
        "image_name_scail2": PUBLIC_SCAIL2_GHCR_IMAGE,
        "image_name_ltx_video": PUBLIC_LTX_VIDEO_GHCR_IMAGE,
        "image_name_pornmaster_flux2_edit": PUBLIC_PORNMASTER_FLUX2_EDIT_GHCR_IMAGE,
        "minio_endpoint": "https://r2.example.test",
    }
    values.update(overrides)
    return RunPodSettings(**values)


def _prod_pod(
    slot: str,
    *,
    max_manual_slots: int = 8,
    profile: str = "img2img",
) -> dict:
    agent_id = prod_agent_id_from_slot(
        slot,
        max_manual_slots=max_manual_slots,
        profile=profile,
    )
    runpod_task_type = {
        "image_to_video": "image_to_video",
        "wan22_video_v2": "wan22_video_v2",
        "i2i_pro": "i2i_pro",
        "scail2": "scail2",
        "ltx_video": "ltx_video",
        "pornmaster_flux2_edit": "pornmaster_flux2_edit",
    }.get(profile, "img2img_lora")
    return {
        "id": f"pod-prod-{slot}",
        "name": prod_pod_name_from_agent_id(
            agent_id,
            max_manual_slots=max_manual_slots,
            profile=profile,
        ),
        "desiredStatus": "RUNNING",
        "env": {
            "RUNPOD_ENVIRONMENT": "cloud-prod",
            "RUNPOD_TASK_TYPE": runpod_task_type,
            "AGENT_ID": agent_id,
            "AGENT_ID_PREFIX": agent_id,
        },
    }


def _worker(
    slot: str,
    *,
    current_task_id: str | None = None,
    max_manual_slots: int = 8,
    profile: str = "img2img",
) -> dict:
    agent_id = prod_agent_id_from_slot(
        slot,
        max_manual_slots=max_manual_slots,
        profile=profile,
    )
    types = {
        "image_to_video": "image_to_video",
        "wan22_video_v2": "wan22_video_v2",
        "i2i_pro": ",".join(RUNPOD_I2I_PRO_SUPPORTED_TASK_TYPES),
        "scail2": ",".join(RUNPOD_SCAIL2_SUPPORTED_TASK_TYPES),
        "ltx_video": ",".join(RUNPOD_LTX_VIDEO_SUPPORTED_TASK_TYPES),
        "pornmaster_flux2_edit": ",".join(
            RUNPOD_PORNMASTER_FLUX2_EDIT_SUPPORTED_TASK_TYPES
        ),
    }.get(profile, "img2img,img2img_lora")
    current_task_type = {
        "image_to_video": "image_to_video",
        "wan22_video_v2": "wan22_video_v2",
        "i2i_pro": "i2i_pro",
        "scail2": "scail2_action_transfer",
        "ltx_video": "ltx_video",
        "pornmaster_flux2_edit": "pornmaster_flux2_single_edit",
    }.get(profile, "img2img_lora")
    return {
        "agent_id": agent_id,
        "types": types,
        "status": "running" if current_task_id else "idle",
        "current_task_id": current_task_id,
        "current_task_type": current_task_type if current_task_id else None,
    }


def _control_posts(runner: FakeHttpProdWorkerRunner) -> list[tuple[str, str]]:
    posts: list[tuple[str, str]] = []
    for call in runner.control_calls:
        if call["method"] != "POST":
            continue
        agent_id = call["url"].rstrip("/").rsplit("/", 1)[-1]
        state = (call["kwargs"].get("json_body") or {}).get("state")
        posts.append((agent_id, state))
    return posts


def test_prod_worker_render_dry_run_uses_verified_image_and_prod_defaults():
    provider = FakeRunPodProvider(_settings())
    options = RunPodProdWorkerOptions(action="render", quiet=True)

    payload = RunPodProdWorkerRunner(provider, options).run()

    assert payload["ok"] is True
    assert payload["render"]["imageName"] == RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE
    assert payload["render"]["docker_start_cmd"] == list(
        RUNPOD_IMG2IMG_LORA_DOCKER_START_CMD
    )
    assert (
        payload["render"]["central_api_url"] == "https://worker-central.aivison.it.com"
    )
    assert payload["render"]["agent_id"] == RUNPOD_PROD_AGENT_ID
    assert payload["render"]["gpu_type_ids"] == list(RUNPOD_PROD_GPU_TYPE_IDS)
    assert payload["render"]["supported_task_types"] == ",".join(
        RUNPOD_PROD_SUPPORTED_TASK_TYPES
    )
    assert payload["render"]["buckets"]["result"] == "user-data-prod"
    assert payload["render"]["custom_nodes_enabled"] == "false"
    assert provider.create_calls == 0
    assert provider.delete_calls == 0


def test_prod_worker_render_wan22_video_v2_uses_prod_profile_defaults():
    image_ref = RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE
    agent_id = prod_agent_id_from_slot("01", profile="wan22_video_v2")
    provider = FakeRunPodProvider(
        _settings(
            prod_agent_id=agent_id,
            image_name_wan22_video_v2=image_ref,
            model_bucket="allbot-model-cache",
            model_prefix_wan22_video_v2=RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX,
            model_manifest_key_wan22_video_v2=RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
        )
    )
    options = RunPodProdWorkerOptions(
        action="render",
        profile="wan22_video_v2",
        task_type="wan22_video_v2",
        agent_id=agent_id,
        quiet=True,
    )

    payload = RunPodProdWorkerRunner(provider, options).run()

    assert payload["ok"] is True
    assert payload["profile"] == "wan22_video_v2"
    assert (
        payload["render"]["pod_name"] == "allbot-runpod-prod-wan22-video-v2-manual-01"
    )
    assert payload["render"]["imageName"] == image_ref
    assert payload["render"]["agent_id"] == "runpod_prod_wan22_video_v2_manual_01"
    assert payload["render"]["gpu_type_ids"] == list(RUNPOD_PROD_GPU_TYPE_IDS)
    assert payload["render"]["supported_task_types"] == "wan22_video_v2"
    assert payload["render"]["pool_runtime_profile"] == "wan22_video_v2"
    assert payload["render"]["model_prefix"] == RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX
    assert (
        payload["render"]["model_manifest_key"]
        == RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY
    )
    assert payload["render"]["wan22_timeout_seconds"] == "600"
    assert payload["render"]["wan22_exit_on_timeout"] == "true"
    assert (
        payload["render"]["comfy_extra_args"] == RUNPOD_WAN22_VIDEO_V2_COMFY_EXTRA_ARGS
    )
    assert payload["render"]["buckets"]["result"] == "user-data-prod"
    assert payload["render"]["custom_nodes_enabled"] == "false"
    assert payload["render"]["sshd_enabled"] == "false"
    assert provider.create_calls == 0
    assert provider.delete_calls == 0


def test_prod_worker_render_image_to_video_uses_prod_profile_defaults():
    image_ref = RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE
    agent_id = prod_agent_id_from_slot("01", profile="image_to_video")
    provider = FakeRunPodProvider(
        _settings(
            prod_agent_id=agent_id,
            image_name_image_to_video=image_ref,
            model_bucket="allbot-model-cache",
            model_prefix_image_to_video=RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX,
            model_manifest_key_image_to_video=RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
        )
    )
    options = RunPodProdWorkerOptions(
        action="render",
        profile="image_to_video",
        task_type="image_to_video",
        agent_id=agent_id,
        quiet=True,
    )

    payload = RunPodProdWorkerRunner(provider, options).run()

    assert payload["ok"] is True
    assert payload["profile"] == "image_to_video"
    assert (
        payload["render"]["pod_name"] == "allbot-runpod-prod-image-to-video-manual-01"
    )
    assert payload["render"]["imageName"] == image_ref
    assert payload["render"]["agent_id"] == "runpod_prod_image_to_video_manual_01"
    assert payload["render"]["gpu_type_ids"] == list(RUNPOD_PROD_GPU_TYPE_IDS)
    assert payload["render"]["supported_task_types"] == "image_to_video"
    assert payload["render"]["pool_runtime_profile"] == "image_to_video"
    assert payload["render"]["model_prefix"] == RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX
    assert (
        payload["render"]["model_manifest_key"]
        == RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY
    )
    assert payload["render"]["buckets"]["result"] == "user-data-prod"
    assert payload["render"]["custom_nodes_enabled"] == "false"
    assert payload["render"]["sshd_enabled"] == "false"
    assert provider.create_calls == 0
    assert provider.delete_calls == 0


def test_prod_worker_render_i2i_pro_uses_prod_profile_defaults():
    agent_id = prod_agent_id_from_slot("01", profile="i2i_pro")
    provider = FakeRunPodProvider(
        _settings(
            prod_agent_id=agent_id,
            image_name_i2i_pro=PUBLIC_I2I_PRO_GHCR_IMAGE,
            model_bucket="allbot-model-cache",
            model_prefix_i2i_pro=RUNPOD_I2I_PRO_MODEL_PREFIX,
            model_manifest_key_i2i_pro=RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY,
        )
    )
    options = RunPodProdWorkerOptions(
        action="render",
        profile="i2i_pro",
        task_type="i2i_pro",
        agent_id=agent_id,
        quiet=True,
    )

    payload = RunPodProdWorkerRunner(provider, options).run()

    assert payload["ok"] is True
    assert payload["profile"] == "i2i_pro"
    assert payload["render"]["pod_name"] == "allbot-runpod-prod-i2i-pro-manual-01"
    assert payload["render"]["imageName"] == PUBLIC_I2I_PRO_GHCR_IMAGE
    assert payload["render"]["agent_id"] == "runpod_prod_i2i_pro_manual_01"
    assert payload["render"]["gpu_type_ids"] == list(RUNPOD_PROD_GPU_TYPE_IDS)
    assert payload["render"]["supported_task_types"] == ",".join(
        RUNPOD_I2I_PRO_SUPPORTED_TASK_TYPES
    )
    assert payload["render"]["pool_runtime_profile"] == "i2i_pro"
    assert payload["render"]["model_prefix"] == RUNPOD_I2I_PRO_MODEL_PREFIX
    assert payload["render"]["model_manifest_key"] == RUNPOD_I2I_PRO_MODEL_MANIFEST_KEY
    assert payload["render"]["workflow_overrides"] == RUNPOD_I2I_PRO_WORKFLOW_OVERRIDES
    assert payload["render"]["buckets"]["result"] == "user-data-prod"
    assert payload["render"]["custom_nodes_enabled"] == "false"
    assert payload["render"]["sshd_enabled"] == "false"
    assert provider.create_calls == 0
    assert provider.delete_calls == 0


def test_prod_worker_render_scail2_uses_prod_profile_defaults():
    agent_id = prod_agent_id_from_slot("01", profile="scail2")
    provider = FakeRunPodProvider(
        _settings(
            prod_agent_id=agent_id,
            image_name_scail2=PUBLIC_SCAIL2_GHCR_IMAGE,
            model_bucket="allbot-model-cache",
            model_prefix_scail2=RUNPOD_SCAIL2_MODEL_PREFIX,
            model_manifest_key_scail2=RUNPOD_SCAIL2_MODEL_MANIFEST_KEY,
        )
    )
    options = RunPodProdWorkerOptions(
        action="render",
        profile="scail2",
        task_type="scail2",
        agent_id=agent_id,
        quiet=True,
    )

    payload = RunPodProdWorkerRunner(provider, options).run()

    assert payload["ok"] is True
    assert payload["profile"] == "scail2"
    assert payload["render"]["pod_name"] == "allbot-runpod-prod-scail2-manual-01"
    assert payload["render"]["imageName"] == PUBLIC_SCAIL2_GHCR_IMAGE
    assert payload["render"]["agent_id"] == "runpod_prod_scail2_manual_01"
    assert payload["render"]["gpu_type_ids"] == list(RUNPOD_PROD_GPU_TYPE_IDS)
    assert payload["render"]["supported_task_types"] == ",".join(
        RUNPOD_SCAIL2_SUPPORTED_TASK_TYPES
    )
    assert payload["render"]["pool_runtime_profile"] == "scail2"
    assert payload["render"]["model_prefix"] == RUNPOD_SCAIL2_MODEL_PREFIX
    assert payload["render"]["model_manifest_key"] == RUNPOD_SCAIL2_MODEL_MANIFEST_KEY
    assert payload["render"]["buckets"]["result"] == "user-data-prod"
    assert payload["render"]["custom_nodes_enabled"] == "false"
    assert payload["render"]["sshd_enabled"] == "false"
    assert provider.create_calls == 0
    assert provider.delete_calls == 0


def test_prod_worker_render_ltx_video_uses_v12_profile_defaults():
    agent_id = prod_agent_id_from_slot("01", profile="ltx_video")
    provider = FakeRunPodProvider(
        _settings(
            prod_agent_id=agent_id,
            image_name_ltx_video=PUBLIC_LTX_VIDEO_GHCR_IMAGE,
            model_bucket="allbot-model-cache",
            model_prefix_ltx_video=RUNPOD_LTX_VIDEO_MODEL_PREFIX,
            model_manifest_key_ltx_video=RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY,
        )
    )
    options = RunPodProdWorkerOptions(
        action="render",
        profile="ltx_video",
        task_type="ltx_video",
        agent_id=agent_id,
        quiet=True,
    )

    payload = RunPodProdWorkerRunner(provider, options).run()

    assert payload["ok"] is True
    assert payload["profile"] == "ltx_video"
    assert payload["render"]["pod_name"] == "allbot-runpod-prod-ltx-video-manual-01"
    assert payload["render"]["imageName"] == PUBLIC_LTX_VIDEO_GHCR_IMAGE
    assert payload["render"]["agent_id"] == "runpod_prod_ltx_video_manual_01"
    assert payload["render"]["supported_task_types"] == ",".join(
        RUNPOD_LTX_VIDEO_SUPPORTED_TASK_TYPES
    )
    assert payload["render"]["pool_runtime_profile"] == "ltx_video"
    assert payload["render"]["model_prefix"] == RUNPOD_LTX_VIDEO_MODEL_PREFIX
    assert payload["render"]["model_manifest_key"] == RUNPOD_LTX_VIDEO_MODEL_MANIFEST_KEY
    assert payload["render"]["workflow_overrides"] == RUNPOD_LTX_VIDEO_WORKFLOW_OVERRIDES
    assert payload["render"]["container_disk_gb"] == RUNPOD_LTX_VIDEO_CONTAINER_DISK_GB
    assert payload["render"]["buckets"]["result"] == "user-data-prod"
    assert payload["render"]["custom_nodes_enabled"] == "false"
    assert payload["render"]["sshd_enabled"] == "false"
    assert provider.create_calls == 0
    assert provider.delete_calls == 0


def test_prod_worker_render_pornmaster_flux2_edit_uses_profile_defaults():
    agent_id = prod_agent_id_from_slot("01", profile="pornmaster_flux2_edit")
    provider = FakeRunPodProvider(
        _settings(
            prod_agent_id=agent_id,
            image_name_pornmaster_flux2_edit=PUBLIC_PORNMASTER_FLUX2_EDIT_GHCR_IMAGE,
            model_bucket="allbot-model-cache",
            model_prefix_pornmaster_flux2_edit=RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX,
            model_manifest_key_pornmaster_flux2_edit=(
                RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY
            ),
        )
    )
    options = RunPodProdWorkerOptions(
        action="render",
        profile="pornmaster_flux2_edit",
        task_type="pornmaster_flux2_edit",
        agent_id=agent_id,
        quiet=True,
    )

    payload = RunPodProdWorkerRunner(provider, options).run()

    assert payload["ok"] is True
    assert payload["profile"] == "pornmaster_flux2_edit"
    assert (
        payload["render"]["pod_name"]
        == "allbot-runpod-prod-pornmaster-flux2-edit-manual-01"
    )
    assert payload["render"]["imageName"] == PUBLIC_PORNMASTER_FLUX2_EDIT_GHCR_IMAGE
    assert (
        payload["render"]["agent_id"]
        == "runpod_prod_pornmaster_flux2_edit_manual_01"
    )
    assert payload["render"]["supported_task_types"] == ",".join(
        RUNPOD_PORNMASTER_FLUX2_EDIT_SUPPORTED_TASK_TYPES
    )
    assert payload["render"]["pool_runtime_profile"] == "pornmaster_flux2_edit"
    assert (
        payload["render"]["model_prefix"]
        == RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_PREFIX
    )
    assert (
        payload["render"]["model_manifest_key"]
        == RUNPOD_PORNMASTER_FLUX2_EDIT_MODEL_MANIFEST_KEY
    )
    assert (
        payload["render"]["container_disk_gb"]
        == RUNPOD_PORNMASTER_FLUX2_EDIT_CONTAINER_DISK_GB
    )
    assert payload["render"]["buckets"]["result"] == "user-data-prod"
    assert payload["render"]["custom_nodes_enabled"] == "false"
    assert payload["render"]["sshd_enabled"] == "false"
    assert provider.create_calls == 0
    assert provider.delete_calls == 0


def test_prod_worker_render_pornmaster_flux2_edit_bf16_isolated_on_4090():
    agent_id = prod_agent_id_from_slot("01", profile="pornmaster_flux2_edit_bf16")
    provider = FakeRunPodProvider(
        _settings(
            prod_agent_id=agent_id,
            image_name_pornmaster_flux2_edit=PUBLIC_PORNMASTER_FLUX2_EDIT_GHCR_IMAGE,
            model_bucket="allbot-model-cache",
        )
    )
    options = RunPodProdWorkerOptions(
        action="render",
        profile="pornmaster_flux2_edit_bf16",
        task_type="pornmaster_flux2_edit_bf16",
        agent_id=agent_id,
        quiet=True,
    )

    payload = RunPodProdWorkerRunner(provider, options).run()

    assert payload["ok"] is True
    assert payload["profile"] == "pornmaster_flux2_edit_bf16"
    assert payload["render"]["pod_name"] == (
        "allbot-runpod-prod-pornmaster-flux2-edit-bf16-manual-01"
    )
    assert payload["render"]["gpu_type_ids"] == list(
        RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_GPU_TYPE_IDS
    )
    assert payload["render"]["supported_task_types"] == ",".join(
        RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_SUPPORTED_TASK_TYPES
    )
    assert payload["render"]["pool_runtime_profile"] == "pornmaster_flux2_edit"
    assert payload["render"]["model_prefix"] == (
        RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_PREFIX
    )
    assert payload["render"]["model_manifest_key"] == (
        RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_MANIFEST_KEY
    )
    assert payload["render"]["container_disk_gb"] == (
        RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_CONTAINER_DISK_GB
    )
    assert payload["render"]["comfy_extra_args"] == (
        RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_COMFY_EXTRA_ARGS
    )


def test_prod_worker_bf16_canary_covers_single_and_multi_isolated_task_types():
    agent_id = prod_agent_id_from_slot("01", profile="pornmaster_flux2_edit_bf16")
    runner = RunPodProdWorkerRunner(
        FakeRunPodProvider(_settings(prod_agent_id=agent_id)),
        RunPodProdWorkerOptions(
            action="canary",
            profile="pornmaster_flux2_edit_bf16",
            task_type="pornmaster_flux2_edit_bf16",
            agent_id=agent_id,
            quiet=True,
        ),
    )

    cases = runner._pornmaster_flux2_edit_bf16_task_cases("canary/input.png")

    assert len(cases) == 2
    assert [case["expected_central_task_type"] for case in cases] == [
        "pornmaster_flux2_edit_bf16",
        "pornmaster_flux2_multi_edit_bf16",
    ]
    assert cases[0]["payload"]["task_type"] == "pornmaster_flux2_edit_bf16"
    assert cases[0]["payload"]["inputs"]["images"] == ["canary/input.png"]
    assert cases[1]["payload"]["inputs"]["images"] == [
        "canary/input.png",
        "canary/input.png",
    ]


def test_prod_worker_scail2_canary_cases_use_reference_then_motion_video():
    agent_id = prod_agent_id_from_slot("01", profile="scail2")
    provider = FakeRunPodProvider(_settings(prod_agent_id=agent_id))
    options = RunPodProdWorkerOptions(
        action="canary",
        profile="scail2",
        task_type="scail2",
        agent_id=agent_id,
        prompt="prod scail2 prompt",
        negative_prompt="prod scail2 negative",
        quiet=True,
    )
    runner = RunPodProdWorkerRunner(provider, options)

    cases = runner._scail2_task_cases(
        {
            "reference_image_key": "user-data-prod/web_uploads/3/reference.jpg",
            "motion_video_key": "user-data-prod/web_uploads/3/motion.mp4",
        }
    )

    assert [case["expected_central_task_type"] for case in cases] == [
        "scail2_action_transfer",
        "scail2_video_replacement",
    ]
    for case in cases:
        payload = case["payload"]
        inputs = payload["inputs"]
        assert inputs["images"] == [
            "user-data-prod/web_uploads/3/reference.jpg",
            "user-data-prod/web_uploads/3/motion.mp4",
        ]
        assert inputs["image"] == "user-data-prod/web_uploads/3/reference.jpg"
        assert inputs["video"] == "user-data-prod/web_uploads/3/motion.mp4"
        assert inputs["duration"] == 5
        assert inputs["resolution"] == "512x896"
        assert payload["prompt"] == "prod scail2 prompt"
        assert payload["negative_prompt"] == "prod scail2 negative"


def test_prod_worker_pornmaster_flux2_canary_cases_cover_single_and_multi_edit():
    agent_id = prod_agent_id_from_slot("01", profile="pornmaster_flux2_edit")
    provider = FakeRunPodProvider(_settings(prod_agent_id=agent_id))
    options = RunPodProdWorkerOptions(
        action="canary",
        profile="pornmaster_flux2_edit",
        task_type="pornmaster_flux2_edit",
        agent_id=agent_id,
        prompt="prod pornmaster prompt",
        negative_prompt="prod pornmaster negative",
        quiet=True,
    )
    runner = RunPodProdWorkerRunner(provider, options)

    cases = runner._pornmaster_flux2_edit_task_cases(
        "user-data-prod/web_uploads/3/reference.png"
    )

    assert [case["expected_central_task_type"] for case in cases] == [
        "pornmaster_flux2_single_edit",
        "pornmaster_flux2_multi_edit",
    ]
    assert [case["result_kind"] for case in cases] == ["image", "image"]
    single_inputs = cases[0]["payload"]["inputs"]
    multi_inputs = cases[1]["payload"]["inputs"]
    assert single_inputs["images"] == ["user-data-prod/web_uploads/3/reference.png"]
    assert single_inputs["image"] == "user-data-prod/web_uploads/3/reference.png"
    assert multi_inputs["images"] == [
        "user-data-prod/web_uploads/3/reference.png",
        "user-data-prod/web_uploads/3/reference.png",
    ]
    assert multi_inputs["image2"] == "user-data-prod/web_uploads/3/reference.png"
    for case in cases:
        payload = case["payload"]
        assert payload["prompt"] == "prod pornmaster prompt"
        assert payload["negative_prompt"] == "prod pornmaster negative"
        assert payload["priority"] == 0


def test_prod_worker_scail2_canary_input_keys_are_stringified():
    agent_id = prod_agent_id_from_slot("01", profile="scail2")
    provider = FakeRunPodProvider(_settings(prod_agent_id=agent_id))
    options = RunPodProdWorkerOptions(
        action="canary",
        profile="scail2",
        task_type="scail2",
        agent_id=agent_id,
        scail2_reference_object_key=123,  # type: ignore[arg-type]
        scail2_motion_video_object_key=456,  # type: ignore[arg-type]
        quiet=True,
    )
    runner = RunPodProdWorkerRunner(provider, options)

    resolved = runner._resolve_scail2_inputs({})

    assert resolved == {
        "reference_image_key": "123",
        "motion_video_key": "456",
    }


def test_prod_worker_render_can_target_second_manual_slot():
    agent_id = prod_agent_id_from_slot("02")
    provider = FakeRunPodProvider(_settings(prod_agent_id=agent_id))
    options = RunPodProdWorkerOptions(action="render", agent_id=agent_id, quiet=True)

    payload = RunPodProdWorkerRunner(provider, options).run()

    assert payload["ok"] is True
    assert payload["render"]["pod_name"] == "allbot-runpod-prod-img2img-manual-02"
    assert payload["render"]["agent_id"] == "runpod_prod_img2img_manual_02"


def test_prod_worker_default_max_slot_namespace_allows_hundred_slots(monkeypatch):
    monkeypatch.delenv("RUNPOD_PROD_MAX_MANUAL_SLOTS", raising=False)

    assert prod_agent_id_from_slot("03") == "runpod_prod_img2img_manual_03"
    assert prod_agent_id_from_slot("100") == "runpod_prod_img2img_manual_100"
    try:
        prod_agent_id_from_slot("101")
    except ValueError as exc:
        assert "between 01 and 100" in str(exc)
    else:
        raise AssertionError("slot 101 should require explicit max slot configuration")


def test_prod_worker_env_max_slot_allows_rendering_eighth_slot(monkeypatch):
    monkeypatch.setenv("RUNPOD_PROD_MAX_MANUAL_SLOTS", "8")
    agent_id = prod_agent_id_from_slot("08")
    provider = FakeRunPodProvider(
        _settings(prod_agent_id=agent_id, prod_max_manual_slots=8)
    )
    options = RunPodProdWorkerOptions(action="render", agent_id=agent_id, quiet=True)

    payload = RunPodProdWorkerRunner(provider, options).run()

    assert payload["ok"] is True
    assert payload["render"]["pod_name"] == "allbot-runpod-prod-img2img-manual-08"
    assert payload["render"]["agent_id"] == "runpod_prod_img2img_manual_08"


def test_prod_worker_up_dry_run_preflights_without_mutation():
    provider = FakeRunPodProvider(_settings())
    options = RunPodProdWorkerOptions(action="up", execute=False, quiet=True)
    runner = FakeHttpProdWorkerRunner(
        provider, options, sleep_func=lambda _seconds: None
    )

    payload = runner.run()

    assert payload["ok"] is True
    assert "set Central control" in payload["would_execute"][0]
    assert provider.create_calls == 0
    assert runner.control_calls == []


def test_prod_worker_scale_dry_run_plans_missing_third_slot_without_mutation():
    provider = FakeRunPodProvider(
        _settings(prod_max_manual_slots=8),
        pods=[_prod_pod("01"), _prod_pod("02")],
    )
    options = RunPodProdWorkerOptions(
        action="scale",
        desired_count=3,
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[_worker("01"), _worker("02")],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is True
    assert payload["scale_plan"]["create_slots"] == ["03"]
    assert payload["scale_plan"]["delete_slots"] == []
    assert provider.create_calls == 0
    assert runner.control_calls == []
    assert "create cloud-prod RunPod pod for slot 03" in payload["would_execute"]


def test_prod_worker_add_dry_run_uses_lowest_free_slots_without_deletes():
    provider = FakeRunPodProvider(
        _settings(prod_max_manual_slots=8),
        pods=[_prod_pod("01"), _prod_pod("03")],
    )
    options = RunPodProdWorkerOptions(
        action="add",
        add_count=2,
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[_worker("01"), _worker("03")],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is True
    assert payload["add_plan"]["create_slots"] == ["02", "04"]
    assert payload["add_plan"]["existing_slots"] == ["01", "03"]
    assert payload["add_plan"]["enable_slots"] == []
    assert payload["add_plan"]["delete_slots"] == []
    assert provider.create_calls == 0
    assert runner.control_calls == []
    assert "create cloud-prod RunPod pod for new slot 02" in payload["would_execute"]
    assert any("enabled" in item for item in payload["would_execute"])
    assert any("leave all existing" in item for item in payload["would_execute"])


def test_prod_worker_add_execute_creates_only_new_free_slots():
    provider = FakeRunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            prod_max_manual_slots=8,
        ),
        pods=[_prod_pod("01"), _prod_pod("03")],
    )
    options = RunPodProdWorkerOptions(
        action="add",
        execute=True,
        add_count=2,
        agent_token="agent_token",
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[_worker("01"), _worker("02"), _worker("03"), _worker("04")],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is True
    assert payload["add_plan"]["create_slots"] == ["02", "04"]
    assert payload["add_plan"]["delete_slots"] == []
    assert [item["agent_id"] for item in provider.create_log] == [
        "runpod_prod_img2img_manual_02",
        "runpod_prod_img2img_manual_04",
    ]
    assert provider.delete_calls == 0
    assert _control_posts(runner) == [
        ("runpod_prod_img2img_manual_02", "disabled"),
        ("runpod_prod_img2img_manual_02", "enabled"),
        ("runpod_prod_img2img_manual_04", "disabled"),
        ("runpod_prod_img2img_manual_04", "enabled"),
    ]


def test_prod_worker_add_execute_rechecks_slot_before_create(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNPOD_PROD_OPERATION_LOCK_DIR", str(tmp_path))
    provider = SlotRaceRunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            prod_max_manual_slots=8,
        ),
        pods=[_prod_pod("01")],
        stolen_slot="02",
    )
    options = RunPodProdWorkerOptions(
        action="add",
        execute=True,
        add_count=1,
        agent_token="agent_token",
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[_worker("01"), _worker("02")],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is False
    assert "slot 02 is no longer free" in payload["error"]
    assert provider.create_calls == 0
    assert _control_posts(runner) == []


def test_prod_worker_add_recovers_when_create_error_left_healthy_disabled_pod():
    provider = FailingCreateAfterPodRunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            prod_max_manual_slots=8,
        ),
        pods=[_prod_pod("01")],
    )
    options = RunPodProdWorkerOptions(
        action="add",
        execute=True,
        add_count=1,
        agent_token="agent_token",
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[_worker("01"), _worker("02")],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is True
    assert provider.create_calls == 1
    assert payload["operations"][0]["create_recovery"]["recovered"] is True
    assert payload["operations"][0]["slot"] == "02"
    assert _control_posts(runner) == [
        ("runpod_prod_img2img_manual_02", "disabled"),
        ("runpod_prod_img2img_manual_02", "enabled"),
    ]


def test_prod_worker_add_fails_before_mutation_when_free_slots_insufficient():
    provider = FakeRunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            prod_max_manual_slots=2,
        ),
        pods=[_prod_pod("01", max_manual_slots=2), _prod_pod("02", max_manual_slots=2)],
    )
    options = RunPodProdWorkerOptions(
        action="add",
        execute=True,
        add_count=1,
        agent_token="agent_token",
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[_worker("01", max_manual_slots=2), _worker("02", max_manual_slots=2)],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is False
    assert "requires 1 free slot" in payload["error"]
    assert provider.create_calls == 0
    assert provider.delete_calls == 0
    assert runner.control_calls == []


def test_prod_worker_scale_execute_creates_and_enables_missing_slot():
    provider = FakeRunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            max_pods_total=3,
            max_pods_per_type=3,
            prod_max_manual_slots=8,
        ),
        pods=[_prod_pod("01"), _prod_pod("02")],
    )
    options = RunPodProdWorkerOptions(
        action="scale",
        execute=True,
        desired_count=3,
        agent_token="agent_token",
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[_worker("01"), _worker("02"), _worker("03")],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is True
    assert provider.create_calls == 1
    assert provider.create_log[0]["agent_id"] == "runpod_prod_img2img_manual_03"
    assert _control_posts(runner) == [
        ("runpod_prod_img2img_manual_03", "disabled"),
        ("runpod_prod_img2img_manual_03", "enabled"),
        ("runpod_prod_img2img_manual_01", "enabled"),
        ("runpod_prod_img2img_manual_02", "enabled"),
    ]


def test_prod_worker_scale_down_refuses_busy_highest_slot():
    provider = FakeRunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            max_pods_total=1,
            max_pods_per_type=1,
        ),
        pods=[_prod_pod("01", max_manual_slots=2), _prod_pod("02", max_manual_slots=2)],
    )
    options = RunPodProdWorkerOptions(
        action="scale",
        execute=True,
        desired_count=1,
        agent_token="agent_token",
        drain_timeout_seconds=0.001,
        poll_interval_seconds=0.001,
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[
            _worker("01", max_manual_slots=2),
            _worker("02", current_task_id="busy-task", max_manual_slots=2),
        ],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is False
    assert "current_task_id=busy-task" in payload["error"]
    assert provider.delete_calls == 0


def test_prod_worker_scale_desired_zero_drains_and_deletes_all_slots():
    provider = FakeRunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            max_pods_total=1,
            max_pods_per_type=1,
        ),
        pods=[_prod_pod("01", max_manual_slots=2), _prod_pod("02", max_manual_slots=2)],
    )
    options = RunPodProdWorkerOptions(
        action="scale",
        execute=True,
        desired_count=0,
        agent_token="agent_token",
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[_worker("01", max_manual_slots=2), _worker("02", max_manual_slots=2)],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is True
    assert [item["pod_id"] for item in provider.delete_log] == [
        "pod-prod-02",
        "pod-prod-01",
    ]
    assert _control_posts(runner) == [
        ("runpod_prod_img2img_manual_02", "disabled"),
        ("runpod_prod_img2img_manual_01", "disabled"),
    ]


def test_prod_worker_down_deletes_existing_slots_without_create_render_config():
    cases = [
        ("img2img", "img2img_lora", {}),
        ("image_to_video", "image_to_video", {}),
        ("wan22_video_v2", "wan22_video_v2", {}),
        ("i2i_pro", "i2i_pro", {"image_name_i2i_pro": ""}),
        ("scail2", "scail2", {"image_name_scail2": ""}),
        (
            "pornmaster_flux2_edit",
            "pornmaster_flux2_edit",
            {"image_name_pornmaster_flux2_edit": ""},
        ),
    ]
    for profile, task_type, setting_overrides in cases:
        agent_id = prod_agent_id_from_slot("01", profile=profile)
        provider = FailingRenderRunPodProvider(
            _settings(
                dry_run=False,
                autoscaler_enabled=True,
                prod_agent_id=agent_id,
                **setting_overrides,
            ),
            pods=[_prod_pod("01", profile=profile)],
        )
        options = RunPodProdWorkerOptions(
            action="down",
            execute=True,
            profile=profile,
            task_type=task_type,
            agent_id=agent_id,
            agent_token="agent_token",
            quiet=True,
        )
        runner = FakeHttpProdWorkerRunner(
            provider,
            options,
            workers=[_worker("01", profile=profile)],
            sleep_func=lambda _seconds: None,
        )

        payload = runner.run()

        assert payload["ok"] is True, (profile, payload.get("error"))
        assert provider.create_calls == 0
        assert provider.delete_calls == 1
        assert provider.delete_log[0]["pod_id"] == "pod-prod-01"
        assert _control_posts(runner) == [(agent_id, "disabled")]


def test_prod_worker_scale_rejects_desired_above_max_slots():
    provider = FakeRunPodProvider(_settings(prod_max_manual_slots=2))
    options = RunPodProdWorkerOptions(action="scale", desired_count=3, quiet=True)

    payload = RunPodProdWorkerRunner(provider, options).run()

    assert payload["ok"] is False
    assert "--desired must be <= RUNPOD_PROD_MAX_MANUAL_SLOTS (2)" in payload["error"]


def test_prod_worker_up_execute_requires_gates_before_control_or_create():
    provider = FakeRunPodProvider(_settings(dry_run=True, autoscaler_enabled=False))
    options = RunPodProdWorkerOptions(
        action="up",
        execute=True,
        agent_token="agent_token",
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider, options, sleep_func=lambda _seconds: None
    )

    payload = runner.run()

    assert payload["ok"] is False
    assert "RUNPOD_DRY_RUN=false" in payload["error"]
    assert "RUNPOD_AUTOSCALER_ENABLED=true" in payload["error"]
    assert provider.create_calls == 0
    assert runner.control_calls == []


def test_prod_worker_up_second_slot_execute_ignores_removed_per_type_gate():
    agent_id = prod_agent_id_from_slot("02")
    provider = FakeRunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            max_pods_total=5,
            max_pods_per_type=1,
            prod_agent_id=agent_id,
        )
    )
    options = RunPodProdWorkerOptions(
        action="up",
        execute=True,
        agent_id=agent_id,
        agent_token="agent_token",
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[_worker("02")],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is True
    assert provider.create_calls == 1
    assert provider.create_log[0]["agent_id"] == "runpod_prod_img2img_manual_02"
    assert _control_posts(runner) == [
        ("runpod_prod_img2img_manual_02", "disabled"),
    ]


def test_prod_worker_restart_execute_uses_native_restart_and_enables():
    agent_id = prod_agent_id_from_slot("03", profile="wan22_video_v2")
    provider = FakeRunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            prod_agent_id=agent_id,
            prod_max_manual_slots=8,
            image_name_wan22_video_v2=RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE,
        ),
        pods=[_prod_pod("03", profile="wan22_video_v2")],
    )
    options = RunPodProdWorkerOptions(
        action="restart",
        execute=True,
        profile="wan22_video_v2",
        task_type="wan22_video_v2",
        agent_id=agent_id,
        agent_token="agent_token",
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[_worker("03", profile="wan22_video_v2")],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is True
    assert provider.create_calls == 0
    assert provider.delete_calls == 0
    assert provider.stop_calls == 0
    assert provider.start_calls == 0
    assert provider.restart_log == [
        {"pod_id": "pod-prod-03", "agent_id": "runpod_prod_wan22_video_v2_manual_03"}
    ]
    assert payload["pod_restart"]["pod_id"] == "pod-prod-03"
    assert payload["pod_restart"]["restart"] == {"ok": True}
    assert _control_posts(runner) == [
        ("runpod_prod_wan22_video_v2_manual_03", "disabled"),
        ("runpod_prod_wan22_video_v2_manual_03", "enabled"),
    ]


def test_prod_worker_restart_recovers_enable_when_worker_is_idle_after_failure():
    agent_id = prod_agent_id_from_slot("04")
    provider = FailingRestartRunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            prod_agent_id=agent_id,
            prod_max_manual_slots=8,
        ),
        pods=[_prod_pod("04")],
    )
    options = RunPodProdWorkerOptions(
        action="restart",
        execute=True,
        agent_id=agent_id,
        agent_token="agent_token",
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[_worker("04")],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is True
    assert payload["pod_restart"]["recovered_after_error"] is True
    assert payload["pod_restart"]["restart"] == {"ok": False}
    assert payload["restart_recovery"]["recovered"] is True
    assert "runpod restart-pod failed" in payload["error_before_recovery"]
    assert provider.stop_calls == 0
    assert provider.start_calls == 0
    assert provider.restart_log == [
        {"pod_id": "pod-prod-04", "agent_id": "runpod_prod_img2img_manual_04"}
    ]
    assert _control_posts(runner) == [
        ("runpod_prod_img2img_manual_04", "disabled"),
        ("runpod_prod_img2img_manual_04", "enabled"),
    ]


def test_prod_worker_restart_keeps_disabled_when_recovery_worker_is_busy():
    agent_id = prod_agent_id_from_slot("04")
    provider = FailingRestartRunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            prod_agent_id=agent_id,
            prod_max_manual_slots=8,
        ),
        pods=[_prod_pod("04")],
    )
    options = RunPodProdWorkerOptions(
        action="restart",
        execute=True,
        agent_id=agent_id,
        agent_token="agent_token",
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[_worker("04", current_task_id="busy-task")],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is False
    assert "runpod restart-pod failed" in payload["error"]
    assert payload["restart_recovery"]["recovered"] is False
    assert "worker_not_idle:running" in payload["restart_recovery"]["blockers"]
    assert "worker_has_current_task_id" in payload["restart_recovery"]["blockers"]
    assert _control_posts(runner) == [
        ("runpod_prod_img2img_manual_04", "disabled"),
    ]


def test_prod_worker_restart_keeps_disabled_when_recovery_pod_not_running():
    agent_id = prod_agent_id_from_slot("04")
    pod = _prod_pod("04")
    pod["desiredStatus"] = "EXITED"
    provider = FailingRestartRunPodProvider(
        _settings(
            dry_run=False,
            autoscaler_enabled=True,
            prod_agent_id=agent_id,
            prod_max_manual_slots=8,
        ),
        pods=[pod],
    )
    options = RunPodProdWorkerOptions(
        action="restart",
        execute=True,
        agent_id=agent_id,
        agent_token="agent_token",
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(
        provider,
        options,
        workers=[_worker("04")],
        sleep_func=lambda _seconds: None,
    )

    payload = runner.run()

    assert payload["ok"] is False
    assert payload["restart_recovery"]["recovered"] is False
    assert "pod_not_running:EXITED" in payload["restart_recovery"]["blockers"]
    assert _control_posts(runner) == [
        ("runpod_prod_img2img_manual_04", "disabled"),
    ]


def test_prod_worker_env_loader_protects_explicit_runpod_gates(
    tmp_path: Path, monkeypatch
):
    env_file = tmp_path / ".env.cloud.prod"
    env_file.write_text(
        "RUNPOD_DRY_RUN=true\nAGENT_SECRET_TOKEN=prod_agent_token\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RUNPOD_DRY_RUN", "false")
    monkeypatch.setenv("AGENT_SECRET_TOKEN", "old_agent_token")

    info = load_env_file_for_prod_worker(
        env_file,
        override=True,
        protect_existing_prefixes=("RUNPOD_",),
    )

    assert info["loaded"] is True
    assert info["count"] == 1
    assert info["protected_existing_prefixes"] == ["RUNPOD_"]
    assert __import__("os").environ["RUNPOD_DRY_RUN"] == "false"
    assert __import__("os").environ["AGENT_SECRET_TOKEN"] == "prod_agent_token"


def test_prod_worker_selection_slot_updates_provider_agent_env(monkeypatch):
    monkeypatch.delenv("RUNPOD_PROD_AGENT_ID", raising=False)
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "status",
            "--slot",
            "02",
        ]
    )

    selection = apply_prod_worker_selection_to_env(args)

    assert selection["slot"] == "02"
    assert selection["agent_id"] == "runpod_prod_img2img_manual_02"
    assert selection["pod_name"] == "allbot-runpod-prod-img2img-manual-02"
    assert __import__("os").environ["RUNPOD_PROD_AGENT_ID"] == selection["agent_id"]


def test_prod_worker_selection_wan22_profile_uses_dedicated_agent_env(monkeypatch):
    monkeypatch.setenv("RUNPOD_PROD_AGENT_ID", RUNPOD_PROD_AGENT_ID)
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "status",
            "--profile",
            "wan22_video_v2",
            "--slot",
            "02",
        ]
    )

    selection = apply_prod_worker_selection_to_env(args)

    assert selection["profile"] == "wan22_video_v2"
    assert selection["slot"] == "02"
    assert selection["agent_id"] == "runpod_prod_wan22_video_v2_manual_02"
    assert selection["pod_name"] == "allbot-runpod-prod-wan22-video-v2-manual-02"
    assert __import__("os").environ["RUNPOD_PROD_AGENT_ID"] == selection["agent_id"]


def test_prod_worker_selection_image_to_video_profile_uses_dedicated_agent_env(
    monkeypatch,
):
    monkeypatch.setenv("RUNPOD_PROD_AGENT_ID", RUNPOD_PROD_AGENT_ID)
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "status",
            "--profile",
            "image_to_video",
            "--slot",
            "02",
        ]
    )

    selection = apply_prod_worker_selection_to_env(args)

    assert selection["profile"] == "image_to_video"
    assert selection["slot"] == "02"
    assert selection["agent_id"] == "runpod_prod_image_to_video_manual_02"
    assert selection["pod_name"] == "allbot-runpod-prod-image-to-video-manual-02"
    assert __import__("os").environ["RUNPOD_PROD_AGENT_ID"] == selection["agent_id"]


def test_prod_worker_selection_can_infer_profile_from_prod_agent_env(monkeypatch):
    monkeypatch.setenv(
        "RUNPOD_PROD_AGENT_ID",
        prod_agent_id_from_slot("01", profile="wan22_video_v2"),
    )
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "status",
        ]
    )

    selection = apply_prod_worker_selection_to_env(args)

    assert selection["profile"] == "wan22_video_v2"
    assert selection["agent_id"] == "runpod_prod_wan22_video_v2_manual_01"
    assert selection["pod_name"] == "allbot-runpod-prod-wan22-video-v2-manual-01"


def test_prod_worker_selection_can_infer_image_to_video_profile_from_prod_agent_env(
    monkeypatch,
):
    monkeypatch.setenv(
        "RUNPOD_PROD_AGENT_ID",
        prod_agent_id_from_slot("01", profile="image_to_video"),
    )
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "status",
        ]
    )

    selection = apply_prod_worker_selection_to_env(args)

    assert selection["profile"] == "image_to_video"
    assert selection["agent_id"] == "runpod_prod_image_to_video_manual_01"
    assert selection["pod_name"] == "allbot-runpod-prod-image-to-video-manual-01"


def test_prod_worker_selection_scail2_profile_uses_dedicated_agent_env(monkeypatch):
    monkeypatch.setenv("RUNPOD_PROD_AGENT_ID", RUNPOD_PROD_AGENT_ID)
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "status",
            "--profile",
            "scail2",
            "--slot",
            "02",
        ]
    )

    selection = apply_prod_worker_selection_to_env(args)

    assert selection["profile"] == "scail2"
    assert selection["slot"] == "02"
    assert selection["agent_id"] == "runpod_prod_scail2_manual_02"
    assert selection["pod_name"] == "allbot-runpod-prod-scail2-manual-02"
    assert __import__("os").environ["RUNPOD_PROD_AGENT_ID"] == selection["agent_id"]


def test_prod_worker_selection_can_infer_scail2_profile_from_prod_agent_env(
    monkeypatch,
):
    monkeypatch.setenv(
        "RUNPOD_PROD_AGENT_ID",
        prod_agent_id_from_slot("01", profile="scail2"),
    )
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "status",
        ]
    )

    selection = apply_prod_worker_selection_to_env(args)

    assert selection["profile"] == "scail2"
    assert selection["agent_id"] == "runpod_prod_scail2_manual_01"
    assert selection["pod_name"] == "allbot-runpod-prod-scail2-manual-01"


def test_prod_worker_selection_ltx_video_profile_uses_dedicated_agent_env(
    monkeypatch,
):
    monkeypatch.setenv("RUNPOD_PROD_AGENT_ID", RUNPOD_PROD_AGENT_ID)
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "status",
            "--profile",
            "ltx_video",
            "--slot",
            "02",
        ]
    )

    selection = apply_prod_worker_selection_to_env(args)

    assert selection["profile"] == "ltx_video"
    assert selection["slot"] == "02"
    assert selection["agent_id"] == "runpod_prod_ltx_video_manual_02"
    assert selection["pod_name"] == "allbot-runpod-prod-ltx-video-manual-02"
    assert __import__("os").environ["RUNPOD_PROD_AGENT_ID"] == selection["agent_id"]


def test_prod_worker_selection_pornmaster_flux2_profile_uses_dedicated_agent_env(
    monkeypatch,
):
    monkeypatch.setenv("RUNPOD_PROD_AGENT_ID", RUNPOD_PROD_AGENT_ID)
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "status",
            "--profile",
            "pornmaster_flux2_edit",
            "--slot",
            "02",
        ]
    )

    selection = apply_prod_worker_selection_to_env(args)

    assert selection["profile"] == "pornmaster_flux2_edit"
    assert selection["slot"] == "02"
    assert selection["agent_id"] == "runpod_prod_pornmaster_flux2_edit_manual_02"
    assert (
        selection["pod_name"]
        == "allbot-runpod-prod-pornmaster-flux2-edit-manual-02"
    )
    assert __import__("os").environ["RUNPOD_PROD_AGENT_ID"] == selection["agent_id"]


def test_cli_parses_runpod_prod_worker_up_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "up",
            "--slot",
            "02",
            "--runpod-env-file",
            ".env.cloud.test",
            "--prod-env-file",
            ".env.cloud.prod",
            "--execute",
            "--quiet",
        ]
    )

    assert args.runpod_command == "prod-worker"
    assert args.prod_worker_command == "up"
    assert args.slot == "02"
    assert args.runpod_env_file == Path(".env.cloud.test")
    assert args.prod_env_file == Path(".env.cloud.prod")
    assert args.execute is True
    assert args.quiet is True


def test_cli_parses_runpod_prod_worker_add_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "add",
            "--profile",
            "img2img",
            "--count",
            "2",
            "--execute",
            "--quiet",
        ]
    )

    assert args.runpod_command == "prod-worker"
    assert args.prod_worker_command == "add"
    assert args.profile == "img2img"
    assert args.count == 2
    assert args.execute is True
    assert args.quiet is True


def test_cli_parses_runpod_prod_worker_wan22_profile_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "render",
            "--profile",
            "wan22_video_v2",
            "--slot",
            "01",
            "--quiet",
        ]
    )

    assert args.runpod_command == "prod-worker"
    assert args.prod_worker_command == "render"
    assert args.profile == "wan22_video_v2"
    assert args.slot == "01"
    assert args.quiet is True


def test_cli_parses_runpod_prod_worker_image_to_video_profile_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "render",
            "--profile",
            "image_to_video",
            "--slot",
            "01",
            "--quiet",
        ]
    )

    assert args.runpod_command == "prod-worker"
    assert args.prod_worker_command == "render"
    assert args.profile == "image_to_video"
    assert args.slot == "01"
    assert args.quiet is True


def test_cli_parses_runpod_prod_worker_i2i_pro_profile_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "render",
            "--profile",
            "i2i_pro",
            "--slot",
            "01",
            "--quiet",
        ]
    )

    assert args.runpod_command == "prod-worker"
    assert args.prod_worker_command == "render"
    assert args.profile == "i2i_pro"
    assert args.slot == "01"
    assert args.quiet is True


def test_cli_parses_runpod_prod_worker_scail2_profile_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "canary",
            "--profile",
            "scail2",
            "--slot",
            "01",
            "--scail2-reference-object-key",
            "user-data-prod/web_uploads/3/reference.jpg",
            "--scail2-motion-video-object-key",
            "user-data-prod/web_uploads/3/motion.mp4",
            "--quiet",
        ]
    )

    assert args.runpod_command == "prod-worker"
    assert args.prod_worker_command == "canary"
    assert args.profile == "scail2"
    assert args.slot == "01"
    assert args.scail2_reference_object_key == "user-data-prod/web_uploads/3/reference.jpg"
    assert args.scail2_motion_video_object_key == "user-data-prod/web_uploads/3/motion.mp4"
    assert args.quiet is True


def test_cli_parses_runpod_prod_worker_ltx_video_profile_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "render",
            "--profile",
            "ltx_video",
            "--slot",
            "01",
            "--quiet",
        ]
    )

    assert args.runpod_command == "prod-worker"
    assert args.prod_worker_command == "render"
    assert args.profile == "ltx_video"
    assert args.slot == "01"
    assert args.quiet is True


def test_cli_parses_runpod_prod_worker_pornmaster_flux2_profile_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "render",
            "--profile",
            "pornmaster_flux2_edit",
            "--slot",
            "01",
            "--quiet",
        ]
    )

    assert args.runpod_command == "prod-worker"
    assert args.prod_worker_command == "render"
    assert args.profile == "pornmaster_flux2_edit"
    assert args.slot == "01"
    assert args.quiet is True


def test_cli_parses_runpod_prod_worker_pornmaster_flux2_bf16_profile_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "render",
            "--profile",
            "pornmaster_flux2_edit_bf16",
            "--slot",
            "01",
            "--quiet",
        ]
    )

    assert args.runpod_command == "prod-worker"
    assert args.prod_worker_command == "render"
    assert args.profile == "pornmaster_flux2_edit_bf16"
    assert args.slot == "01"
    assert args.quiet is True


def test_cli_parses_runpod_prod_worker_scale_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "scale",
            "--desired",
            "3",
            "--execute",
            "--quiet",
        ]
    )

    assert args.runpod_command == "prod-worker"
    assert args.prod_worker_command == "scale"
    assert args.desired == 3
    assert args.execute is True
    assert args.quiet is True
