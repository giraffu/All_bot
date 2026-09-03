from __future__ import annotations

import json
import re
from typing import Any

from .pipeline_policy import pipeline_environment_for_profile
from .runpod_profile_catalog import (
    RUNPOD_I2I_PRO_CONTAINER_DISK_GB,
    RUNPOD_IMAGE_TO_VIDEO_CONTAINER_DISK_GB,
    RUNPOD_LTX_VIDEO_CONTAINER_DISK_GB,
    RUNPOD_LTX_VIDEO_DOCKER_START_CMD,
    RUNPOD_LTX_T2V_CONTAINER_DISK_GB,
    RUNPOD_LTX_T2V_DOCKER_START_CMD,
    RUNPOD_LTX_T2V_GPU_TYPE_IDS,
    RUNPOD_LTX_T2V_MODEL_MANIFEST_KEY,
    RUNPOD_LTX_T2V_MODEL_PREFIX,
    RUNPOD_LTX_T2V_VOLUME_GB,
    RUNPOD_LTX25_VIDEO_UPSCALE_CONTAINER_DISK_GB,
    RUNPOD_LTX25_VIDEO_UPSCALE_DOCKER_START_CMD,
    RUNPOD_LTX25_VIDEO_UPSCALE_GPU_TYPE_IDS,
    RUNPOD_LTX25_VIDEO_UPSCALE_MODEL_MANIFEST_KEY,
    RUNPOD_LTX25_VIDEO_UPSCALE_MODEL_PREFIX,
    RUNPOD_LTX25_VIDEO_UPSCALE_TASK_COMPLETION_TIMEOUT_SECONDS,
    RUNPOD_LTX25_VIDEO_UPSCALE_VOLUME_GB,
    RUNPOD_MINIMAX_H3_CONTAINER_DISK_GB,
    RUNPOD_MINIMAX_H3_COMFY_EXTRA_ARGS,
    RUNPOD_MINIMAX_H3_DOCKER_START_CMD,
    RUNPOD_MINIMAX_H3_ALLOWED_GPU_TYPE_IDS,
    RUNPOD_MINIMAX_H3_MODEL_MANIFEST_KEY,
    RUNPOD_MINIMAX_H3_MODEL_PREFIX,
    RUNPOD_MINIMAX_H3_VOLUME_GB,
    RUNPOD_PUBLIC_MINIMAX_H3_IMAGE_PREFIX,
    RUNPOD_PORNMASTER_FLUX2_EDIT_CONTAINER_DISK_GB,
    RUNPOD_PORNMASTER_FLUX2_EDIT_DOCKER_START_CMD,
    RUNPOD_PORNMASTER_FLUX2_EDIT_SUPPORTED_TASK_TYPES,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_CONTAINER_DISK_GB,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_COMFY_EXTRA_ARGS,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_DOCKER_START_CMD,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_GPU_TYPE_IDS,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_MANIFEST_KEY,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_PREFIX,
    RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_SUPPORTED_TASK_TYPES,
    RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
    RUNPOD_PUBLIC_WAN22_AIO_VIDEO_REPOSITORY,
    RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE,
    RUNPOD_RELEASE_WAN22_AIO_VIDEO_REPOSITORY,
    RUNPOD_SCAIL2_CONTAINER_DISK_GB,
    RUNPOD_SCAIL2_DOCKER_START_CMD,
    RUNPOD_TASK_PROFILES,
    RunPodTaskProfile,
    prod_pod_name_from_agent_id,
    prod_slot_from_agent_id,
    prod_worker_profile_for_task_type,
)


_RUNPOD_WAN22_AIO_VIDEO_DIGEST_RES = tuple(
    re.compile(rf"^{re.escape(repository)}@sha256:[0-9a-f]{{64}}$")
    for repository in (
        RUNPOD_PUBLIC_WAN22_AIO_VIDEO_REPOSITORY,
        RUNPOD_RELEASE_WAN22_AIO_VIDEO_REPOSITORY,
    )
)


def is_allowed_cloud_prod_wan22_image(image_name: str) -> bool:
    return (
        image_name == RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE
        or any(
            pattern.fullmatch(image_name)
            for pattern in _RUNPOD_WAN22_AIO_VIDEO_DIGEST_RES
        )
    )


def format_seconds_env(value: float) -> str:
    return f"{value:g}"


def normalized_ports(raw_ports: Any) -> list[str]:
    if raw_ports is None:
        return []
    if isinstance(raw_ports, str):
        return [item.strip() for item in raw_ports.split(",") if item.strip()]
    if isinstance(raw_ports, list):
        return [str(item).strip() for item in raw_ports if str(item).strip()]
    return []


def is_managed_pod(pod: dict[str, Any]) -> bool:
    env = pod.get("env") or {}
    name = str(pod.get("name") or "")
    return (
        str(env.get("RUNPOD_MANAGED", "")).strip().lower() == "true"
        or str(env.get("ALLBOT_RUNPOD_MANAGED", "")).strip().lower() == "true"
        or name.startswith("allbot-")
    )


def pod_readiness_from_payload(
    pod: dict[str, Any],
    *,
    require_port_mappings: bool = False,
) -> dict[str, Any]:
    desired_status = str(pod.get("desiredStatus") or pod.get("status") or "")
    ports = normalized_ports(pod.get("ports"))
    port_mappings = pod.get("portMappings") or {}
    public_ip = str(pod.get("publicIp") or "")
    machine = pod.get("machine") or {}
    reasons: list[str] = []
    exposed_ports = bool(ports)
    tcp_ports = [port for port in ports if port.endswith("/tcp")]
    public_ip_expected = (
        str(pod.get("cloudType") or "").upper() == "SECURE"
        or machine.get("secureCloud") is True
        or machine.get("supportPublicIp") is True
    )
    public_ip_present = bool(public_ip.strip())
    port_mappings_present = bool(port_mappings)

    if desired_status != "RUNNING":
        reasons.append("desired_status_not_running")
    if require_port_mappings and public_ip_expected and not public_ip_present:
        reasons.append("public_ip_missing")
    if require_port_mappings and not port_mappings_present:
        reasons.append("port_mappings_empty_for_exposed_ports")
    if require_port_mappings and tcp_ports and not public_ip_present:
        reasons.append("public_ip_missing_for_tcp_ports")

    confidence = "status_only_no_exposed_ports"
    if require_port_mappings:
        confidence = (
            "network_mapping_confirmed"
            if not reasons
            else "initializing_or_unmapped"
        )
    elif exposed_ports:
        confidence = "status_only_with_image_exposed_ports"

    network = {
        "public_ip_expected": public_ip_expected,
        "public_ip_present": public_ip_present,
        "exposed_ports": ports,
        "tcp_ports": tcp_ports,
        "port_mappings_present": port_mappings_present,
        "port_mappings": port_mappings,
    }

    return {
        "infrastructure_ready": not reasons,
        "confidence": confidence,
        "reasons": reasons,
        "network": network,
        "signals": {
            "desired_status": desired_status or "unknown",
            **network,
        },
        "notes": [
            "RunPod REST Pod schema does not expose uptimeSeconds; do not infer readiness from a missing uptime field.",
            "For AllBot business readiness, verify the expected runpod_test_* heartbeat in cloud-test Central /system/workers.",
        ],
    }


def pod_cost(pod: dict[str, Any]) -> float:
    for key in ("adjustedCostPerHr", "costPerHr"):
        raw = pod.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


class RunPodPodRequestBuilder:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def create_pod_body(self, *, task_type: str, environment: str) -> dict[str, Any]:
        if environment not in {"cloud-test", "cloud-prod"}:
            raise ValueError(
                "RunPodProvider v0 only supports environment=cloud-test/cloud-prod"
            )
        profile = self.profile_for_task_type(task_type)
        if profile.task_type == "ltx_t2v":
            self.validate_ltx_t2v_contract()
        if profile.task_type == "ltx25_video_upscale":
            self.validate_ltx25_video_upscale_contract()
        if profile.task_type == "minimax_h3":
            self.validate_minimax_h3_contract()
        if environment == "cloud-prod":
            prod_profile = prod_worker_profile_for_task_type(profile.task_type)
            prod_slot_from_agent_id(
                self.settings.prod_agent_id,
                max_manual_slots=self.settings.prod_max_manual_slots,
                profile=prod_profile,
            )
        if environment == "cloud-prod" and profile.task_type not in {
            "img2img_lora",
            "image_to_video",
            "wan22_video_v2",
            "i2i_pro",
            "scail2",
            "ltx_video",
            "ltx_t2v",
            "ltx25_video_upscale",
            "minimax_h3",
            "pornmaster_flux2_edit_bf16",
        }:
            raise ValueError(
                "RunPodProvider v0 cloud-prod only supports "
                "img2img/img2img_lora, image_to_video, wan22_video_v2, "
                "i2i_pro, scail2, ltx_video, ltx_t2v, minimax_h3, and "
                "pornmaster_flux2_edit_bf16 profiles"
            )
        gpu_type_ids = self.gpu_type_ids_for(profile)
        if environment == "cloud-prod":
            gpu_type_ids = self.prod_gpu_type_ids_for(profile)
        template_id = (
            "" if environment == "cloud-prod" else self.template_id_for(profile)
        )
        image_name = self.image_name_for(profile)
        if (
            environment == "cloud-prod"
            and profile.task_type == "img2img_lora"
            and not image_name
        ):
            image_name = RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE
        if (
            environment == "cloud-prod"
            and profile.task_type
            in {
                "image_to_video",
                "wan22_video_v2",
                "i2i_pro",
                "scail2",
                "ltx_video",
                "ltx_t2v",
                "ltx25_video_upscale",
                "minimax_h3",
                "pornmaster_flux2_edit_bf16",
            }
            and not image_name
        ):
            raise ValueError(f"{profile.image_env_key} is required for cloud-prod")
        if (
            environment == "cloud-prod"
            and profile.task_type in {"image_to_video", "wan22_video_v2"}
            and template_id
        ):
            raise ValueError(
                f"{profile.template_env_key} must be false for cloud-prod split video"
            )
        if (
            environment == "cloud-prod"
            and profile.task_type in {"image_to_video", "wan22_video_v2"}
            and not is_allowed_cloud_prod_wan22_image(image_name)
        ):
            raise ValueError(
                f"{profile.image_env_key} must be the legacy image "
                f"{RUNPOD_PUBLIC_WAN22_AIO_VIDEO_RIFE_IMAGE} or a canonical digest "
                "from an allowed Wan22 release repository for cloud-prod"
            )
        if not template_id and not image_name:
            image_name = self.pending_image_name_for(profile)
        body: dict[str, Any] = {
            "name": self.pod_name(profile=profile, environment=environment),
            "cloudType": self.settings.cloud_type,
            "computeType": "GPU",
            "gpuCount": 1,
            "gpuTypeIds": list(gpu_type_ids),
            "gpuTypePriority": "availability",
            "containerDiskInGb": self.container_disk_gb_for(
                profile=profile,
                environment=environment,
            ),
            "volumeMountPath": self.settings.volume_mount_path,
            "interruptible": self.settings.interruptible,
            "env": self.pod_env(profile=profile, environment=environment),
        }
        if profile.task_type == "minimax_h3":
            if self.settings.min_download_mbps_minimax_h3:
                body["minDownloadMbps"] = (
                    self.settings.min_download_mbps_minimax_h3
                )
            if self.settings.min_ram_per_gpu_minimax_h3:
                body["minRAMPerGPU"] = self.settings.min_ram_per_gpu_minimax_h3
        if self.settings.network_volume_id:
            body["networkVolumeId"] = self.settings.network_volume_id
        else:
            body["volumeInGb"] = self.volume_gb_for(profile)
        if self.settings.data_center_ids:
            body["dataCenterIds"] = list(self.settings.data_center_ids)
            body["dataCenterPriority"] = "availability"
        if template_id:
            body["templateId"] = template_id
        else:
            body["imageName"] = image_name
            if self.settings.container_registry_auth_id:
                body["containerRegistryAuthId"] = (
                    self.settings.container_registry_auth_id
                )
        if self.settings.pod_ports:
            body["ports"] = list(self.settings.pod_ports)
        docker_start_cmd = self.docker_start_cmd_for(profile)
        if docker_start_cmd:
            body["dockerStartCmd"] = list(docker_start_cmd)
        return body

    def validate_ltx_t2v_contract(self) -> None:
        if tuple(self.settings.gpu_type_ids_ltx_t2v) != RUNPOD_LTX_T2V_GPU_TYPE_IDS:
            raise ValueError("ltx_t2v only supports NVIDIA GeForce RTX 5090")
        if self.settings.use_template_ltx_t2v or self.settings.template_id_ltx_t2v:
            raise ValueError("ltx_t2v RunPod templates are disabled")
        if self.settings.model_prefix_ltx_t2v != RUNPOD_LTX_T2V_MODEL_PREFIX:
            raise ValueError("ltx_t2v model prefix must use the fixed release")
        if (
            self.settings.model_manifest_key_ltx_t2v
            != RUNPOD_LTX_T2V_MODEL_MANIFEST_KEY
        ):
            raise ValueError("ltx_t2v model manifest key must use the fixed release")

    def validate_ltx25_video_upscale_contract(self) -> None:
        gpu_type_ids = tuple(self.settings.gpu_type_ids_ltx25_video_upscale)
        if not gpu_type_ids or not set(gpu_type_ids).issubset(
            RUNPOD_LTX25_VIDEO_UPSCALE_GPU_TYPE_IDS
        ):
            raise ValueError(
                "ltx25_video_upscale GPU types must be a non-empty subset of the "
                "verified fixed set"
            )
        if self.settings.use_template_ltx25_video_upscale or self.settings.template_id_ltx25_video_upscale:
            raise ValueError("ltx25_video_upscale RunPod templates are disabled")
        if self.settings.model_prefix_ltx25_video_upscale != RUNPOD_LTX25_VIDEO_UPSCALE_MODEL_PREFIX:
            raise ValueError("ltx25_video_upscale model prefix must use the fixed release")
        if self.settings.model_manifest_key_ltx25_video_upscale != RUNPOD_LTX25_VIDEO_UPSCALE_MODEL_MANIFEST_KEY:
            raise ValueError("ltx25_video_upscale model manifest key must use the fixed release")

    def validate_minimax_h3_contract(self) -> None:
        gpu_type_ids = tuple(self.settings.gpu_type_ids_minimax_h3)
        if not gpu_type_ids or not set(gpu_type_ids).issubset(
            RUNPOD_MINIMAX_H3_ALLOWED_GPU_TYPE_IDS
        ):
            raise ValueError(
                "minimax_h3 gpuTypeIds must be a non-empty subset of verified GPU types: "
                + ",".join(RUNPOD_MINIMAX_H3_ALLOWED_GPU_TYPE_IDS)
            )
        if self.settings.use_template_minimax_h3 or self.settings.template_id_minimax_h3:
            raise ValueError("minimax_h3 RunPod templates are disabled")
        if self.settings.model_prefix_minimax_h3 != RUNPOD_MINIMAX_H3_MODEL_PREFIX:
            raise ValueError("minimax_h3 model prefix must use the fixed release")
        if self.settings.model_manifest_key_minimax_h3 != RUNPOD_MINIMAX_H3_MODEL_MANIFEST_KEY:
            raise ValueError("minimax_h3 model manifest key must use the fixed release")
        image_name = self.settings.image_name_minimax_h3
        canonical_digest_prefix = RUNPOD_PUBLIC_MINIMAX_H3_IMAGE_PREFIX.removesuffix(":") + "@sha256:"
        if not re.fullmatch(re.escape(canonical_digest_prefix) + r"[0-9a-f]{64}", image_name):
            raise ValueError("minimax_h3 requires the canonical image pinned by sha256 digest")

    def container_disk_gb_for(
        self,
        *,
        profile: RunPodTaskProfile,
        environment: str,
    ) -> int:
        del environment
        if profile.task_type == "image_to_video":
            return max(
                self.settings.container_disk_gb,
                self.settings.container_disk_gb_image_to_video,
                RUNPOD_IMAGE_TO_VIDEO_CONTAINER_DISK_GB,
            )
        if profile.task_type == "i2i_pro":
            return max(
                self.settings.container_disk_gb, RUNPOD_I2I_PRO_CONTAINER_DISK_GB
            )
        if profile.task_type == "scail2":
            return max(
                self.settings.container_disk_gb, RUNPOD_SCAIL2_CONTAINER_DISK_GB
            )
        if profile.task_type == "ltx_video":
            return max(
                self.settings.container_disk_gb,
                self.settings.container_disk_gb_ltx_video,
                RUNPOD_LTX_VIDEO_CONTAINER_DISK_GB,
            )
        if profile.task_type == "ltx_t2v":
            return max(
                self.settings.container_disk_gb,
                self.settings.container_disk_gb_ltx_t2v,
                RUNPOD_LTX_T2V_CONTAINER_DISK_GB,
            )
        if profile.task_type == "ltx25_video_upscale":
            return max(
                self.settings.container_disk_gb,
                self.settings.container_disk_gb_ltx25_video_upscale,
                RUNPOD_LTX25_VIDEO_UPSCALE_CONTAINER_DISK_GB,
            )
        if profile.task_type == "minimax_h3":
            return max(
                self.settings.container_disk_gb,
                self.settings.container_disk_gb_minimax_h3,
                RUNPOD_MINIMAX_H3_CONTAINER_DISK_GB,
            )
        if profile.task_type == "pornmaster_flux2_edit":
            return max(
                self.settings.container_disk_gb,
                self.settings.container_disk_gb_pornmaster_flux2_edit,
                RUNPOD_PORNMASTER_FLUX2_EDIT_CONTAINER_DISK_GB,
            )
        if profile.task_type == "pornmaster_flux2_edit_bf16":
            return max(
                self.settings.container_disk_gb,
                RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_CONTAINER_DISK_GB,
            )
        return self.settings.container_disk_gb

    def volume_gb_for(self, profile: RunPodTaskProfile) -> int:
        if profile.task_type == "ltx_t2v":
            return max(self.settings.volume_gb, RUNPOD_LTX_T2V_VOLUME_GB)
        if profile.task_type == "ltx25_video_upscale":
            return max(self.settings.volume_gb, RUNPOD_LTX25_VIDEO_UPSCALE_VOLUME_GB)
        if profile.task_type == "minimax_h3":
            return max(self.settings.volume_gb, RUNPOD_MINIMAX_H3_VOLUME_GB)
        return self.settings.volume_gb

    def pod_env(
        self,
        *,
        profile: RunPodTaskProfile,
        environment: str,
    ) -> dict[str, str]:
        env_config = self.environment_config(profile=profile, environment=environment)
        env = {
            "ENVIRONMENT": env_config["app_environment"],
            "RUNPOD_MANAGED": "true",
            "ALLBOT_RUNPOD_MANAGED": "true",
            "RUNPOD_ENVIRONMENT": environment,
            "RUNPOD_TASK_TYPE": profile.task_type,
            "AGENT_ID_PREFIX": profile.agent_id_prefix,
            "AGENT_ID": f"{profile.agent_id_prefix}_${{RUNPOD_POD_ID:-pending}}",
            "ALLBOT_RUNPOD_ROOT": f"{self.settings.volume_mount_path.rstrip('/')}/allbot",
            "RUNPOD_WORKSPACE_DIR": self.settings.volume_mount_path,
            "RUNPOD_VOLUME_COMFYUI_DIR": f"{self.settings.volume_mount_path.rstrip('/')}/ComfyUI",
            "RUNPOD_PREPARE_COMFYUI_ON_VOLUME": (
                "true" if self.settings.network_volume_id else "false"
            ),
            "RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE": (
                "true"
                if environment != "cloud-prod"
                and self.settings.keepalive_on_bootstrap_failure
                else "false"
            ),
            "RUNPOD_START_SSHD": env_config["start_sshd"],
            "RUNPOD_INSTALL_SSHD_IF_MISSING": env_config["install_sshd_if_missing"],
            "AGENT_SECRET_TOKEN": env_config["agent_secret_token_ref"],
            "CENTRAL_API_URL": env_config["central_api_url"],
            "MASTER_API_URL": "http://127.0.0.1:8013",
            "UPLOAD_SIDECAR_URL": "http://127.0.0.1:8013",
            "LOCAL_RELAY_HOST": "127.0.0.1",
            "LOCAL_RELAY_PORT": "8013",
            "SUPPORTED_TASK_TYPES": ",".join(env_config["supported_task_types"]),
            "POOL_MANAGED": "true",
            "POOL_PROVIDER": "runpod",
            "POOL_NODE_ID": env_config["node_id"],
            "POOL_GPU_INDEX": "0",
            "POOL_RUNTIME_PROFILE": profile.runtime_profile,
            "COMFY_API_URL": "http://127.0.0.1:8188",
            "COMFY_WS_URL": "ws://127.0.0.1:8188/ws",
            "COMFY_INPUT_DIR": "./input",
            "COMFY_OUTPUT_DIR": "./output",
            "MINIO_ENDPOINT": self.settings.minio_endpoint
            or "<RUNPOD_SECRET:MINIO_ENDPOINT>",
            "MINIO_ACCESS_KEY": env_config["minio_access_key_ref"],
            "MINIO_SECRET_KEY": env_config["minio_secret_key_ref"],
            "MINIO_BUCKET": env_config["bucket"],
            "MINIO_INPUT_BUCKET": env_config["bucket"],
            "MINIO_RESULT_BUCKET": env_config["bucket"],
            "MINIO_TEMPLATE_BUCKET": env_config["bucket"],
            "MINIO_SECURE": "true",
            "RUNPOD_MODEL_SYNC_ENABLED": (
                "true" if env_config["model_sync_enabled"] else "false"
            ),
            "RUNPOD_MODEL_DOWNLOAD_CONCURRENCY": str(
                self.settings.model_download_concurrency
            ),
            "RUNPOD_MODEL_BUCKET": env_config["model_bucket"],
            "RUNPOD_MODEL_PREFIX": env_config["model_prefix"],
            "RUNPOD_MODEL_MANIFEST_KEY": env_config["model_manifest_key"],
            "RUNPOD_MODEL_ENDPOINT": self.settings.model_endpoint
            or self.settings.minio_endpoint,
            "RUNPOD_MODEL_ACCESS_KEY": env_config["model_access_key_ref"],
            "RUNPOD_MODEL_SECRET_KEY": env_config["model_secret_key_ref"],
            "RUNPOD_MODEL_SECURE": "true" if self.settings.model_secure else "false",
            "RUNPOD_COMFY_CUSTOM_NODES_ENABLED": (
                "true" if env_config["comfy_custom_nodes_enabled"] else "false"
            ),
            "RUNPOD_COMFY_KJNODES_ENABLED": (
                "true" if env_config["comfy_kjnodes_enabled"] else "false"
            ),
            "PIPELINE_ENABLED": "true",
            "PIPELINE_MAX_RUNNING_TASKS": "1",
            "CANCEL_LOCK_ON_POP": "true",
            "PREFETCH_ENABLED": "true",
            "PREFETCH_RESERVE_TASK": "true",
            "PREFETCH_DEPTH": "1",
            "PREFETCH_TASK_TYPES": ",".join(env_config["supported_task_types"]),
            "PREFETCH_CONSUME_WAIT_SECONDS": "10",
            **pipeline_environment_for_profile(profile.task_type),
        }
        if environment == "cloud-prod":
            env["AGENT_ID"] = env_config["agent_id"]
            env["AGENT_ID_PREFIX"] = env_config["agent_id"]
            env["POOL_IMAGE_REF"] = self.prod_image_name_for(profile)
            if profile.task_type == "ltx25_video_upscale":
                env.update(
                    {
                        "RUNPOD_EMBEDDED_TEST_AGENT_ENABLED": "true",
                        "RUNPOD_TEST_AGENT_ID_PREFIX": profile.agent_id_prefix,
                        "RUNPOD_TEST_CENTRAL_API_URL": (
                            self.settings.worker_central_url_cloud_test
                        ),
                        "RUNPOD_TEST_AGENT_SECRET_TOKEN": (
                            self.settings.agent_secret_token_ref
                        ),
                        "RUNPOD_TEST_MINIO_ENDPOINT": (
                            self.settings.minio_endpoint
                            or "<RUNPOD_SECRET:MINIO_ENDPOINT>"
                        ),
                        "RUNPOD_TEST_MINIO_ACCESS_KEY": (
                            self.settings.minio_access_key_ref
                        ),
                        "RUNPOD_TEST_MINIO_SECRET_KEY": (
                            self.settings.minio_secret_key_ref
                        ),
                        "RUNPOD_TEST_MINIO_BUCKET": "user-data-test",
                        "RUNPOD_TEST_SUPPORTED_TASK_TYPES": (
                            "ltx25_video_upscale"
                        ),
                        "RUNPOD_TEST_RUNTIME_PROFILE": (
                            "ltx25_video_upscale"
                        ),
                        "RUNPOD_TEST_LOCAL_RELAY_PORT": "8014",
                    }
                )
        if profile.task_type == "wan22_video_v2":
            env["WAN22_VIDEO_V2_COMPLETION_TIMEOUT_SECONDS"] = format_seconds_env(
                self.settings.wan22_video_v2_completion_timeout_seconds
            )
            env["WAN22_VIDEO_V2_EXIT_ON_TIMEOUT"] = (
                "true" if self.settings.wan22_video_v2_exit_on_timeout else "false"
            )
            if self.settings.wan22_video_v2_comfy_extra_args:
                env["COMFY_EXTRA_ARGS"] = self.settings.wan22_video_v2_comfy_extra_args
        if profile.task_type == "ltx25_video_upscale":
            env["TASK_COMPLETION_TIMEOUT_SECONDS"] = str(
                RUNPOD_LTX25_VIDEO_UPSCALE_TASK_COMPLETION_TIMEOUT_SECONDS
            )
        if profile.task_type == "pornmaster_flux2_edit_bf16":
            env["COMFY_EXTRA_ARGS"] = (
                RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_COMFY_EXTRA_ARGS
            )
        if profile.task_type == "minimax_h3":
            env["COMFYUI_DIR"] = "/opt/ComfyUI"
            env["RUNPOD_MODEL_TARGET_DIR"] = (
                f"{self.settings.volume_mount_path.rstrip('/')}/ComfyUI/models"
            )
            env["MINIMAX_H3_FORCE_PYTORCH_ATTENTION"] = "true"
            env["COMFY_EXTRA_ARGS"] = RUNPOD_MINIMAX_H3_COMFY_EXTRA_ARGS
            env["COMFY_PROCESS_RECOVERY_ENABLED"] = "true"
            env["COMFY_PROCESS_RECOVERY_MIN_FAILURES"] = "3"
            env["COMFY_PROCESS_RECOVERY_SECONDS"] = "60"
        workflow_overrides = self.workflow_overrides_for(profile)
        if workflow_overrides:
            env["TASK_TYPE_WORKFLOW_OVERRIDES"] = workflow_overrides
        extra_env = dict(self.settings.extra_env)
        if environment == "cloud-prod" and env_config["start_sshd"] != "true":
            extra_env.pop("PUBLIC_KEY", None)
        env.update(extra_env)
        return env

    def pod_name(self, *, profile: RunPodTaskProfile, environment: str) -> str:
        if environment == "cloud-prod":
            return prod_pod_name_from_agent_id(
                self.settings.prod_agent_id,
                max_manual_slots=self.settings.prod_max_manual_slots,
                profile=prod_worker_profile_for_task_type(profile.task_type),
            )
        return f"allbot-runpod-test-{profile.runtime_profile.replace('_', '-')}"

    def environment_config(
        self,
        *,
        profile: RunPodTaskProfile,
        environment: str,
    ) -> dict[str, Any]:
        if environment == "cloud-test":
            return {
                "app_environment": "test",
                "agent_id": f"{profile.agent_id_prefix}_${{RUNPOD_POD_ID:-pending}}",
                "central_api_url": self.settings.worker_central_url_cloud_test,
                "supported_task_types": profile.supported_task_types,
                "bucket": "user-data-test",
                "node_id": "runpod-cloud-test",
                "agent_secret_token_ref": self.settings.agent_secret_token_ref,
                "minio_access_key_ref": self.settings.minio_access_key_ref,
                "minio_secret_key_ref": self.settings.minio_secret_key_ref,
                "start_sshd": "true",
                "install_sshd_if_missing": "true",
                "model_sync_enabled": self.settings.model_sync_enabled,
                "model_bucket": self.settings.model_bucket,
                "model_prefix": self.model_prefix_for(profile),
                "model_manifest_key": self.model_manifest_key_for(profile),
                "model_access_key_ref": self.settings.model_access_key_ref,
                "model_secret_key_ref": self.settings.model_secret_key_ref,
                "comfy_custom_nodes_enabled": self.settings.comfy_custom_nodes_enabled,
                "comfy_kjnodes_enabled": self.settings.comfy_kjnodes_enabled,
            }
        if environment == "cloud-prod":
            model_prefix = self.prod_model_prefix_for(profile)
            model_manifest_key = self.prod_model_manifest_key_for(
                profile, model_prefix
            )
            return {
                "app_environment": "prod",
                "agent_id": self.settings.prod_agent_id,
                "central_api_url": self.settings.worker_central_url_cloud_prod,
                "supported_task_types": self.prod_supported_task_types_for(profile),
                "bucket": self.settings.prod_bucket,
                "node_id": self.settings.prod_node_id,
                "agent_secret_token_ref": self.settings.prod_agent_secret_token_ref,
                "minio_access_key_ref": self.settings.prod_minio_access_key_ref,
                "minio_secret_key_ref": self.settings.prod_minio_secret_key_ref,
                "start_sshd": "true",
                "install_sshd_if_missing": "true",
                "model_sync_enabled": True,
                "model_bucket": self.settings.model_bucket or "allbot-model-cache",
                "model_prefix": model_prefix,
                "model_manifest_key": model_manifest_key,
                "model_access_key_ref": self.settings.model_access_key_ref,
                "model_secret_key_ref": self.settings.model_secret_key_ref,
                "comfy_custom_nodes_enabled": False,
                "comfy_kjnodes_enabled": False,
            }
        raise ValueError(
            "RunPodProvider v0 only supports environment=cloud-test/cloud-prod"
        )

    def mutation_guard(
        self,
        *,
        action: str,
        task_type: str,
        existing_pods: list[dict[str, Any]],
        projected_new_cost_per_hr: float,
    ) -> dict[str, Any]:
        del action, task_type, existing_pods
        reasons: list[str] = []
        if self.settings.dry_run:
            reasons.append("RUNPOD_DRY_RUN=true")
        if not self.settings.autoscaler_enabled:
            reasons.append("RUNPOD_AUTOSCALER_ENABLED=false")

        return {
            "allowed": not reasons,
            "reasons": reasons,
            "settings": {
                "dry_run": self.settings.dry_run,
                "autoscaler_enabled": self.settings.autoscaler_enabled,
                "projected_new_cost_per_hr": projected_new_cost_per_hr,
            },
        }

    def projected_profile_cost(
        self,
        profile: RunPodTaskProfile,
        pods: list[dict[str, Any]],
    ) -> float:
        configured = self.configured_projected_cost(profile)
        if configured > 0:
            return configured
        costs = [pod_cost(pod) for pod in pods if pod_cost(pod) > 0]
        return costs[0] if costs else 0.0

    def configured_projected_cost(self, profile: RunPodTaskProfile) -> float:
        if profile.task_type == "img2img_lora":
            return self.settings.projected_cost_per_hr_img2img_lora
        if profile.task_type == "wan22_aio_video":
            return self.settings.projected_cost_per_hr_wan22_aio_video
        if profile.task_type == "image_to_video":
            return self.settings.projected_cost_per_hr_image_to_video
        if profile.task_type == "wan22_video_v2":
            return self.settings.projected_cost_per_hr_wan22_video_v2
        if profile.task_type == "i2i_pro":
            return self.settings.projected_cost_per_hr_i2i_pro
        if profile.task_type == "scail2":
            return self.settings.projected_cost_per_hr_scail2
        if profile.task_type == "ltx_video":
            return self.settings.projected_cost_per_hr_ltx_video
        if profile.task_type == "ltx_t2v":
            return self.settings.projected_cost_per_hr_ltx_t2v
        if profile.task_type == "ltx25_video_upscale":
            return self.settings.projected_cost_per_hr_ltx25_video_upscale
        if profile.task_type == "minimax_h3":
            return self.settings.projected_cost_per_hr_minimax_h3
        if profile.task_type == "pornmaster_flux2_edit":
            return self.settings.projected_cost_per_hr_pornmaster_flux2_edit
        return 0.0

    @staticmethod
    def profile_for_task_type(task_type: str) -> RunPodTaskProfile:
        try:
            return RUNPOD_TASK_PROFILES[task_type]
        except KeyError as exc:
            raise ValueError(
                "RunPodProvider v0 only supports "
                "img2img_lora/img2img/wan22_aio_video/image_to_video/"
                "wan22_video_v2/i2i_pro/scail2/ltx_video/ltx_t2v/"
                "pornmaster_flux2_edit_bf16 profiles"
            ) from exc

    def gpu_type_ids_for(self, profile: RunPodTaskProfile) -> tuple[str, ...]:
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_IMG2IMG_LORA":
            return self.settings.gpu_type_ids_img2img_lora
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_WAN22_AIO_VIDEO":
            return self.settings.gpu_type_ids_wan22_aio_video
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_IMAGE_TO_VIDEO":
            return self.settings.gpu_type_ids_image_to_video
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_WAN22_VIDEO_V2":
            return self.settings.gpu_type_ids_wan22_video_v2
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_I2I_PRO":
            return self.settings.gpu_type_ids_i2i_pro
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_SCAIL2":
            return self.settings.gpu_type_ids_scail2
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_LTX_VIDEO":
            return self.settings.gpu_type_ids_ltx_video
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_LTX_T2V":
            return self.settings.gpu_type_ids_ltx_t2v
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_LTX25_VIDEO_UPSCALE":
            return self.settings.gpu_type_ids_ltx25_video_upscale
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_MINIMAX_H3":
            return self.settings.gpu_type_ids_minimax_h3
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_PORNMASTER_FLUX2_EDIT":
            return self.settings.gpu_type_ids_pornmaster_flux2_edit
        if profile.gpu_type_env_key == "RUNPOD_GPU_TYPE_IDS_PORNMASTER_FLUX2_EDIT_BF16":
            return RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_GPU_TYPE_IDS
        raise ValueError(f"unsupported RunPod task profile: {profile.task_type}")

    def prod_gpu_type_ids_for(self, profile: RunPodTaskProfile) -> tuple[str, ...]:
        if profile.task_type == "ltx_video":
            return self.settings.gpu_type_ids_ltx_video
        if profile.task_type == "ltx_t2v":
            return self.settings.gpu_type_ids_ltx_t2v
        if profile.task_type == "ltx25_video_upscale":
            return self.settings.gpu_type_ids_ltx25_video_upscale
        if profile.task_type == "minimax_h3":
            return self.settings.gpu_type_ids_minimax_h3
        if profile.task_type == "pornmaster_flux2_edit":
            return self.settings.gpu_type_ids_pornmaster_flux2_edit
        if profile.task_type == "pornmaster_flux2_edit_bf16":
            return RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_GPU_TYPE_IDS
        return self.settings.prod_gpu_type_ids

    def template_id_for(self, profile: RunPodTaskProfile) -> str:
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_IMG2IMG_LORA":
            if not self.settings.use_template_img2img_lora:
                return ""
            return self.settings.template_id_img2img_lora
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_WAN22_AIO_VIDEO":
            if not self.settings.use_template_wan22_aio_video:
                return ""
            return self.settings.template_id_wan22_aio_video
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_IMAGE_TO_VIDEO":
            if not self.settings.use_template_image_to_video:
                return ""
            return self.settings.template_id_image_to_video
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_WAN22_VIDEO_V2":
            if not self.settings.use_template_wan22_video_v2:
                return ""
            return self.settings.template_id_wan22_video_v2
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_I2I_PRO":
            if not self.settings.use_template_i2i_pro:
                return ""
            return self.settings.template_id_i2i_pro
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_SCAIL2":
            if not self.settings.use_template_scail2:
                return ""
            return self.settings.template_id_scail2
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_LTX_VIDEO":
            if not self.settings.use_template_ltx_video:
                return ""
            return self.settings.template_id_ltx_video
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_LTX_T2V":
            if not self.settings.use_template_ltx_t2v:
                return ""
            return self.settings.template_id_ltx_t2v
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_LTX25_VIDEO_UPSCALE":
            if not self.settings.use_template_ltx25_video_upscale:
                return ""
            return self.settings.template_id_ltx25_video_upscale
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_MINIMAX_H3":
            if not self.settings.use_template_minimax_h3:
                return ""
            return self.settings.template_id_minimax_h3
        if profile.template_env_key == "RUNPOD_TEMPLATE_ID_PORNMASTER_FLUX2_EDIT":
            if not self.settings.use_template_pornmaster_flux2_edit:
                return ""
            return self.settings.template_id_pornmaster_flux2_edit
        raise ValueError(f"unsupported RunPod task profile: {profile.task_type}")

    def image_name_for(self, profile: RunPodTaskProfile) -> str:
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_IMG2IMG_LORA":
            return self.settings.image_name_img2img_lora
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_WAN22_AIO_VIDEO":
            return self.settings.image_name_wan22_aio_video
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO":
            return self.settings.image_name_image_to_video
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2":
            return self.settings.image_name_wan22_video_v2
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_I2I_PRO":
            return self.settings.image_name_i2i_pro
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_SCAIL2":
            return self.settings.image_name_scail2
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_LTX_VIDEO":
            return self.settings.image_name_ltx_video
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_LTX_T2V":
            return self.settings.image_name_ltx_t2v
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_LTX25_VIDEO_UPSCALE":
            return self.settings.image_name_ltx25_video_upscale
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_MINIMAX_H3":
            return self.settings.image_name_minimax_h3
        if profile.image_env_key == "RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT":
            return self.settings.image_name_pornmaster_flux2_edit
        raise ValueError(f"unsupported RunPod task profile: {profile.task_type}")

    def prod_image_name_for(self, profile: RunPodTaskProfile) -> str:
        image_name = self.image_name_for(profile)
        if profile.task_type == "img2img_lora" and not image_name:
            return RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE
        return image_name

    @staticmethod
    def pending_image_name_for(profile: RunPodTaskProfile) -> str:
        if profile.task_type in {"wan22_aio_video", "image_to_video", "wan22_video_v2"}:
            return "allbot/comfy-runpod-wan22-aio-video:pending"
        if profile.task_type == "i2i_pro":
            return "allbot/comfy-runpod-i2i-pro:pending"
        if profile.task_type == "scail2":
            return "allbot/comfy-runpod-scail2:pending"
        if profile.task_type == "ltx_video":
            return "allbot/comfy-runpod-ltx-video:pending"
        if profile.task_type == "ltx_t2v":
            return "allbot/comfy-runpod-ltx-t2v:pending"
        if profile.task_type == "ltx25_video_upscale":
            return "allbot/comfy-runpod-ltx25-video-upscale:pending"
        if profile.task_type == "minimax_h3":
            return "allbot/comfy-runpod-minimax-h3:pending"
        if profile.task_type == "pornmaster_flux2_edit":
            return "allbot/comfy-runpod-pornmaster-flux2-edit:pending"
        if profile.task_type == "pornmaster_flux2_edit_bf16":
            return "allbot/comfy-runpod-pornmaster-flux2-edit:pending"
        return "allbot/comfy-runpod-img2img:pending"

    def docker_start_cmd_for(self, profile: RunPodTaskProfile) -> tuple[str, ...]:
        if profile.task_type == "img2img_lora":
            return self.settings.docker_start_cmd_img2img_lora
        if profile.task_type == "wan22_aio_video":
            return self.settings.docker_start_cmd_wan22_aio_video
        if profile.task_type == "image_to_video":
            return self.settings.docker_start_cmd_image_to_video
        if profile.task_type == "wan22_video_v2":
            return self.settings.docker_start_cmd_wan22_video_v2
        if profile.task_type == "i2i_pro":
            return self.settings.docker_start_cmd_i2i_pro
        if profile.task_type == "scail2":
            return self.settings.docker_start_cmd_scail2 or RUNPOD_SCAIL2_DOCKER_START_CMD
        if profile.task_type == "ltx_video":
            return (
                self.settings.docker_start_cmd_ltx_video
                or RUNPOD_LTX_VIDEO_DOCKER_START_CMD
            )
        if profile.task_type == "ltx_t2v":
            return (
                self.settings.docker_start_cmd_ltx_t2v
                or RUNPOD_LTX_T2V_DOCKER_START_CMD
            )
        if profile.task_type == "ltx25_video_upscale":
            return (
                self.settings.docker_start_cmd_ltx25_video_upscale
                or RUNPOD_LTX25_VIDEO_UPSCALE_DOCKER_START_CMD
            )
        if profile.task_type == "minimax_h3":
            return (
                self.settings.docker_start_cmd_minimax_h3
                or RUNPOD_MINIMAX_H3_DOCKER_START_CMD
            )
        if profile.task_type == "pornmaster_flux2_edit":
            return (
                self.settings.docker_start_cmd_pornmaster_flux2_edit
                or RUNPOD_PORNMASTER_FLUX2_EDIT_DOCKER_START_CMD
            )
        if profile.task_type == "pornmaster_flux2_edit_bf16":
            return RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_DOCKER_START_CMD
        return ()

    def workflow_overrides_for(self, profile: RunPodTaskProfile) -> str:
        if profile.task_type == "i2i_pro":
            return self._workflow_overrides_json(
                self.settings.task_type_workflow_overrides_i2i_pro,
                env_name="RUNPOD_TASK_TYPE_WORKFLOW_OVERRIDES_I2I_PRO",
            )
        if profile.task_type == "ltx_video":
            return self._workflow_overrides_json(
                self.settings.task_type_workflow_overrides_ltx_video,
                env_name="RUNPOD_TASK_TYPE_WORKFLOW_OVERRIDES_LTX_VIDEO",
            )
        return ""

    @staticmethod
    def _workflow_overrides_json(raw: str, *, env_name: str) -> str:
        raw = raw.strip()
        if not raw:
            return ""
        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in parsed.items()
        ):
            raise ValueError(
                f"{env_name} must be a JSON object of task_type to workflow filename"
            )
        return json.dumps(parsed, separators=(",", ":"))

    def model_prefix_for(self, profile: RunPodTaskProfile) -> str:
        if profile.task_type == "wan22_aio_video":
            return self.settings.model_prefix_wan22_aio_video
        if profile.task_type == "image_to_video":
            return self.settings.model_prefix_image_to_video
        if profile.task_type == "wan22_video_v2":
            return self.settings.model_prefix_wan22_video_v2
        if profile.task_type == "i2i_pro":
            return self.settings.model_prefix_i2i_pro
        if profile.task_type == "scail2":
            return self.settings.model_prefix_scail2
        if profile.task_type == "ltx_video":
            return self.settings.model_prefix_ltx_video
        if profile.task_type == "ltx_t2v":
            return self.settings.model_prefix_ltx_t2v
        if profile.task_type == "ltx25_video_upscale":
            return self.settings.model_prefix_ltx25_video_upscale
        if profile.task_type == "minimax_h3":
            return self.settings.model_prefix_minimax_h3
        if profile.task_type == "pornmaster_flux2_edit":
            return self.settings.model_prefix_pornmaster_flux2_edit
        if profile.task_type == "pornmaster_flux2_edit_bf16":
            return RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_PREFIX
        return self.settings.model_prefix

    def model_manifest_key_for(self, profile: RunPodTaskProfile) -> str:
        if profile.task_type == "wan22_aio_video":
            return self.settings.model_manifest_key_wan22_aio_video
        if profile.task_type == "image_to_video":
            return self.settings.model_manifest_key_image_to_video
        if profile.task_type == "wan22_video_v2":
            return self.settings.model_manifest_key_wan22_video_v2
        if profile.task_type == "i2i_pro":
            return self.settings.model_manifest_key_i2i_pro
        if profile.task_type == "scail2":
            return self.settings.model_manifest_key_scail2
        if profile.task_type == "ltx_video":
            return self.settings.model_manifest_key_ltx_video
        if profile.task_type == "ltx_t2v":
            return self.settings.model_manifest_key_ltx_t2v
        if profile.task_type == "ltx25_video_upscale":
            return self.settings.model_manifest_key_ltx25_video_upscale
        if profile.task_type == "minimax_h3":
            return self.settings.model_manifest_key_minimax_h3
        if profile.task_type == "pornmaster_flux2_edit":
            return self.settings.model_manifest_key_pornmaster_flux2_edit
        if profile.task_type == "pornmaster_flux2_edit_bf16":
            return RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_MODEL_MANIFEST_KEY
        return self.settings.model_manifest_key

    def prod_supported_task_types_for(
        self,
        profile: RunPodTaskProfile,
    ) -> tuple[str, ...]:
        if profile.task_type == "img2img_lora":
            return self.settings.prod_supported_task_types
        if profile.task_type == "image_to_video":
            return profile.supported_task_types
        if profile.task_type == "wan22_video_v2":
            return profile.supported_task_types
        if profile.task_type == "i2i_pro":
            return profile.supported_task_types
        if profile.task_type == "scail2":
            return profile.supported_task_types
        if profile.task_type == "ltx_video":
            return profile.supported_task_types
        if profile.task_type == "ltx_t2v":
            return profile.supported_task_types
        if profile.task_type == "ltx25_video_upscale":
            return profile.supported_task_types
        if profile.task_type == "minimax_h3":
            return profile.supported_task_types
        if profile.task_type == "pornmaster_flux2_edit":
            return RUNPOD_PORNMASTER_FLUX2_EDIT_SUPPORTED_TASK_TYPES
        if profile.task_type == "pornmaster_flux2_edit_bf16":
            return RUNPOD_PORNMASTER_FLUX2_EDIT_BF16_SUPPORTED_TASK_TYPES
        raise ValueError(
            f"unsupported cloud-prod RunPod task profile: {profile.task_type}"
        )

    def prod_model_prefix_for(self, profile: RunPodTaskProfile) -> str:
        if profile.task_type == "img2img_lora":
            return self.settings.model_prefix or "img2img_lora/2026-06-10"
        return self.model_prefix_for(profile)

    def prod_model_manifest_key_for(
        self,
        profile: RunPodTaskProfile,
        model_prefix: str,
    ) -> str:
        if profile.task_type == "img2img_lora":
            return self.settings.model_manifest_key or f"{model_prefix}/manifest.json"
        return self.model_manifest_key_for(profile) or f"{model_prefix}/manifest.json"
