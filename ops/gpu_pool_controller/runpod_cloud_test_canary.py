from __future__ import annotations

import json
import os
import struct
import time
import urllib.parse
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .providers.runpod import RUNPOD_TASK_PROFILES, redact_payload
from .runpod_control import join_url
from .runpod_http import safe_url


EXPECTED_TEST_BUCKET = "user-data-test"
TERMINAL_TASK_STATUSES = {"done", "error", "cancelled"}
SCAIL2_SAMPLE_REFERENCE_URL = (
    "https://i.gyazo.com/567acaf722ca9e839ec7cb834c1ed344/max_size/1200.jpg"
)
SCAIL2_SAMPLE_MOTION_VIDEO_URL = (
    "https://i.gyazo.com/53461ca17746349fbd11e69798460ea6.mp4"
)
SCAIL2_CANARY_NEGATIVE_PROMPT = (
    "low quality, artifacts, text, watermark, distorted face, bad hands"
)


class RunPodCloudTestCanaryError(ValueError):
    pass


@dataclass(frozen=True)
class RunPodCloudTestCanaryConfig:
    task_type: str
    web_api_url: str
    central_url: str
    input_object_key: str
    scail2_reference_object_key: str
    scail2_motion_video_object_key: str
    output_dir: Path
    download_results_dir: Path | None
    task_timeout_seconds: float
    task_poll_interval_seconds: float
    prompt: str
    negative_prompt: str
    result_bucket: str = EXPECTED_TEST_BUCKET


class RunPodCloudTestCanaryCaseBuilder:
    def __init__(
        self,
        config: RunPodCloudTestCanaryConfig,
        *,
        error_type: type[Exception] = RunPodCloudTestCanaryError,
    ) -> None:
        self.config = config
        self._error_type = error_type

    def task_cases(self, test_input: str | dict[str, str]) -> list[dict[str, Any]]:
        profile = RUNPOD_TASK_PROFILES[self.config.task_type]
        if profile.task_type == "scail2":
            if not isinstance(test_input, dict):
                raise self._error("SCAIL-2 canary requires reference/video inputs")
            return self.scail2_task_cases(test_input)
        image_object_key = (
            test_input
            if isinstance(test_input, str)
            else str(test_input.get("object_key") or "")
        )
        if not image_object_key:
            raise self._error("canary image object key is required")
        if profile.task_type == "wan22_aio_video":
            return self.wan22_aio_video_task_cases(image_object_key)
        if profile.task_type == "i2i_pro":
            return self.i2i_pro_task_cases(image_object_key)
        if profile.task_type == "ltx_video":
            return self.ltx_video_task_cases(image_object_key)
        return self.img2img_task_cases(image_object_key)

    def img2img_task_cases(self, image_object_key: str) -> list[dict[str, Any]]:
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
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
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
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
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
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
                    "priority": 0,
                },
            },
        ]

    def wan22_aio_video_task_cases(
        self,
        image_object_key: str,
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
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
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
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
                    "priority": 0,
                },
            },
        ]

    def ltx_video_task_cases(self, image_object_key: str) -> list[dict[str, Any]]:
        return [
            {
                "label": "ltx_video_i2v_5s",
                "expected_central_task_type": "ltx_video",
                "payload": {
                    "task_type": "ltx_video",
                    "inputs": {
                        "images": [image_object_key],
                        "image": image_object_key,
                        "resolution": "1280x704",
                        "duration": 5,
                        "duration_seconds": 5,
                        "extract_last_frame": True,
                        "ltx_mode": "i2v",
                        "seed": 20260622,
                    },
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
                    "priority": 0,
                },
            }
        ]

    def i2i_pro_task_cases(self, image_object_key: str) -> list[dict[str, Any]]:
        return [
            {
                "label": "i2i_pro_single_image",
                "expected_central_task_type": "i2i_pro",
                "payload": {
                    "task_type": "i2i_pro",
                    "inputs": {
                        "images": [image_object_key],
                        "image": image_object_key,
                        "seed": 20260614,
                    },
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
                    "priority": 0,
                },
            },
            {
                "label": "txt2img_from_i2i_pro",
                "expected_central_task_type": "t2i-pornmaster-turbo",
                "payload": {
                    "task_type": "txt2img",
                    "inputs": {"seed": 20260614},
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
                    "priority": 0,
                },
            },
            {
                "label": "face_swap_v2_from_i2i_pro",
                "expected_central_task_type": "face_swap_v2",
                "payload": {
                    "task_type": "face_swap_v2",
                    "inputs": {
                        "images": [image_object_key, image_object_key],
                        "target_image": image_object_key,
                        "face_image": image_object_key,
                    },
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
                    "priority": 0,
                },
            },
        ]

    def scail2_task_cases(self, test_input: dict[str, str]) -> list[dict[str, Any]]:
        reference_key = str(test_input.get("reference_image_key") or "")
        motion_key = str(test_input.get("motion_video_key") or "")
        if not reference_key or not motion_key:
            raise self._error(
                "SCAIL-2 canary requires reference_image_key and motion_video_key"
            )
        base_inputs = {
            "images": [reference_key, motion_key],
            "image": reference_key,
            "video": motion_key,
            "resolution": "512x896",
            "duration": 5,
            "seed": 20260617,
        }
        prompt = self.config.prompt or (
            "cinematic action transfer, consistent character identity, natural motion"
        )
        negative_prompt = self.config.negative_prompt or SCAIL2_CANARY_NEGATIVE_PROMPT
        return [
            {
                "label": "scail2_action_transfer_5s",
                "expected_central_task_type": "scail2_action_transfer",
                "payload": {
                    "task_type": "scail2_action_transfer",
                    "inputs": dict(base_inputs),
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "priority": 0,
                },
            },
            {
                "label": "scail2_video_replacement_5s",
                "expected_central_task_type": "scail2_video_replacement",
                "payload": {
                    "task_type": "scail2_video_replacement",
                    "inputs": dict(base_inputs),
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "priority": 0,
                },
            },
        ]

    def split_video_task_cases(
        self,
        image_object_key: str,
        *,
        active_profiles: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        base_inputs = {
            "images": [image_object_key],
            "image": image_object_key,
            "resolution": "preview",
            "resolution_preset": "preview",
            "duration": 5,
            "duration_seconds": 5,
            "extract_last_frame": True,
            "seed": 20260613,
            "negative_prompt": self.config.negative_prompt,
        }
        cases = [
            {
                "label": "image_to_video_no_lora",
                "worker_profile": "image_to_video",
                "payload": {
                    "task_type": "image_to_video",
                    "inputs": {
                        **base_inputs,
                        "wan22_model_profile": "legacy_image_to_video",
                    },
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
                    "priority": 0,
                },
            },
            {
                "label": "image_to_video_insertion_lora",
                "worker_profile": "image_to_video",
                "lora_name": "Insertion",
                "payload": {
                    "task_type": "image_to_video",
                    "inputs": {
                        **base_inputs,
                        "wan22_model_profile": "legacy_image_to_video",
                        "lora_name": "Insertion",
                        "lora_strength": 1.0,
                    },
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
                    "priority": 0,
                },
            },
            {
                "label": "wan22_video_v2",
                "worker_profile": "wan22_video_v2",
                "payload": {
                    "task_type": "wan22_video_v2",
                    "inputs": {
                        **base_inputs,
                        "wan22_model_profile": "wan22_video_v2",
                    },
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
                    "priority": 0,
                },
            },
        ]
        return [
            case
            for case in cases
            if str(case.get("worker_profile") or "") in active_profiles
        ]

    def _error(self, message: str) -> Exception:
        return self._error_type(message)


class RunPodCloudTestCanaryAssets:
    def __init__(
        self,
        config: RunPodCloudTestCanaryConfig,
        *,
        http_json_func: Callable[..., dict[str, Any]],
        http_request_func: Callable[..., dict[str, Any]],
        web_auth_headers_func: Callable[[], dict[str, str]],
        phase_func: Callable[
            [dict[str, Any], str, str, dict[str, Any] | None],
            None,
        ],
        error_type: type[Exception] = RunPodCloudTestCanaryError,
    ) -> None:
        self.config = config
        self._http_json = http_json_func
        self._http_request = http_request_func
        self._web_auth_headers = web_auth_headers_func
        self._phase = phase_func
        self._error_type = error_type

    def upload_canary_image(self, summary: dict[str, Any]) -> str:
        self._phase(summary, "upload_test_image", "running", None)
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        image_path = self.config.output_dir / f"runpod_canary_{int(time.time())}.png"
        write_canary_png(image_path)
        object_key = self.upload_bytes_to_user_data(
            filename=image_path.name,
            content_type="image/png",
            body=image_path.read_bytes(),
        )
        self._phase(summary, "upload_test_image", "ok", {"object_key": object_key})
        return object_key

    def upload_bytes_to_user_data(
        self,
        *,
        filename: str,
        content_type: str,
        body: bytes,
    ) -> str:
        presign = self._http_json(
            "GET",
            join_url(self.config.web_api_url, "storage", "presigned-url"),
            params={"filename": filename, "content_type": content_type},
            headers=self._web_auth_headers(),
        )
        object_key = str(presign.get("object_key") or "")
        upload_url = str(presign.get("upload_url") or "")
        if not object_key or not upload_url:
            raise self._error("presigned upload response missing object_key/upload_url")
        self._http_request(
            "PUT",
            upload_url,
            body=body,
            headers={"Content-Type": content_type},
            expected_statuses=(200, 201, 204),
        )
        return object_key

    def resolve_canary_image(self, summary: dict[str, Any]) -> str:
        object_key = self.config.input_object_key.strip()
        if object_key:
            self._phase(summary, "reuse_test_image", "ok", {"object_key": object_key})
            return object_key
        return self.upload_canary_image(summary)

    def resolve_canary_inputs(self, summary: dict[str, Any]) -> dict[str, str]:
        profile = RUNPOD_TASK_PROFILES[self.config.task_type]
        if profile.task_type == "scail2":
            return self.resolve_scail2_inputs(summary)
        image_object_key = self.resolve_canary_image(summary)
        return {"object_key": image_object_key}

    def resolve_scail2_inputs(self, summary: dict[str, Any]) -> dict[str, str]:
        reference_key = (
            self.config.scail2_reference_object_key.strip()
            or self.config.input_object_key.strip()
        )
        motion_key = self.config.scail2_motion_video_object_key.strip()
        reused: dict[str, str] = {}
        if reference_key:
            reused["reference_image_key"] = reference_key
        if motion_key:
            reused["motion_video_key"] = motion_key
        if reused:
            self._phase(summary, "reuse_scail2_inputs", "ok", reused)
        if not reference_key:
            self._phase(summary, "upload_scail2_reference_image", "running", None)
            reference_bytes = self.download_scail2_sample(
                SCAIL2_SAMPLE_REFERENCE_URL,
                label="reference image",
            )
            reference_key = self.upload_bytes_to_user_data(
                filename=f"scail2_reference_{int(time.time())}.jpg",
                content_type="image/jpeg",
                body=reference_bytes,
            )
            self._phase(
                summary,
                "upload_scail2_reference_image",
                "ok",
                {"object_key": reference_key, "bytes": len(reference_bytes)},
            )
        if not motion_key:
            self._phase(summary, "upload_scail2_motion_video", "running", None)
            motion_bytes = self.download_scail2_sample(
                SCAIL2_SAMPLE_MOTION_VIDEO_URL,
                label="motion video",
            )
            motion_key = self.upload_bytes_to_user_data(
                filename=f"scail2_motion_{int(time.time())}.mp4",
                content_type="video/mp4",
                body=motion_bytes,
            )
            self._phase(
                summary,
                "upload_scail2_motion_video",
                "ok",
                {"object_key": motion_key, "bytes": len(motion_bytes)},
            )
        return {
            "reference_image_key": reference_key,
            "motion_video_key": motion_key,
        }

    def download_scail2_sample(self, url: str, *, label: str) -> bytes:
        response = self._http_request(
            "GET",
            url,
            headers={"User-Agent": "AllBot-RunPod-SCAIL2-Canary/1.0"},
            expected_statuses=(200,),
        )
        raw = response["raw"]
        if not raw:
            raise self._error(f"SCAIL-2 sample {label} download returned empty")
        return raw

    def _error(self, message: str) -> Exception:
        return self._error_type(message)


class RunPodCloudTestCanaryExecutor:
    def __init__(
        self,
        config: RunPodCloudTestCanaryConfig,
        *,
        http_json_func: Callable[..., dict[str, Any]],
        http_request_func: Callable[..., dict[str, Any]],
        web_auth_headers_func: Callable[[], dict[str, str]],
        fetch_workers_func: Callable[[], list[dict[str, Any]]],
        sleep_func: Callable[[float], None],
        phase_func: Callable[
            [dict[str, Any], str, str, dict[str, Any] | None],
            None,
        ],
        fetch_result_bytes_func: Callable[[str], tuple[bytes, str]] | None = None,
        error_type: type[Exception] = RunPodCloudTestCanaryError,
    ) -> None:
        self.config = config
        self._http_json = http_json_func
        self._http_request = http_request_func
        self._web_auth_headers = web_auth_headers_func
        self._fetch_workers = fetch_workers_func
        self._fetch_result_bytes_override = fetch_result_bytes_func
        self._sleep = sleep_func
        self._phase = phase_func
        self._error_type = error_type

    def run_task_case(
        self,
        task_case: dict[str, Any],
        runpod_worker: dict[str, Any],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        label = str(task_case["label"])
        self._phase(summary, f"task_{label}", "running", None)
        submit_payload = self._http_json(
            "POST",
            join_url(self.config.web_api_url, "tasks", "generate"),
            json_body=task_case["payload"],
            headers=self._web_auth_headers(),
        )
        task_id = str(submit_payload.get("task_id") or "")
        if not task_id:
            raise self._error(f"{label}: missing task_id in Web response")
        final_status, pop_evidence = self.wait_task_done(
            task_id=task_id,
            expected_worker_id=str(runpod_worker.get("agent_id") or ""),
        )
        task_result = {
            "label": label,
            "registry_task_id": task_id,
            "task_type": task_case["payload"]["task_type"],
            "expected_central_task_type": task_case.get(
                "expected_central_task_type",
                task_case["payload"]["task_type"],
            ),
            "lora_name": task_case.get("lora_name") or "",
            "central_status": final_status.get("status"),
            "central_task_type": final_status.get("task_type"),
            "pop_evidence": pop_evidence,
        }
        if str(final_status.get("task_type") or "") != str(
            task_result["expected_central_task_type"]
        ):
            raise self._error(
                f"{label}: Central task_type is {final_status.get('task_type')}, "
                f"expected {task_result['expected_central_task_type']}"
            )
        if final_status.get("status") != "done":
            raise self._error(
                f"{label}: Central terminal status is {final_status.get('status')}"
            )
        result_payload = self.wait_web_result(task_id)
        result_url = str(result_payload.get("result_url") or "")
        task_result["web_result_status"] = result_payload.get("status")
        task_result["result_path"] = result_url_path(result_url)
        if result_payload.get("status") != "success" or not result_url:
            raise self._error(f"{label}: Web result did not become success")
        downloaded = self.download_result_if_requested(
            label=label,
            task_id=task_id,
            result_url=result_url,
        )
        if downloaded:
            task_result.update(downloaded)
        last_frame_result = self.validate_wan22_last_frame_if_required(
            label=label,
            task_id=task_id,
            result_payload=result_payload,
        )
        if last_frame_result:
            task_result.update(last_frame_result)
        self._phase(summary, f"task_{label}", "ok", task_result)
        return task_result

    def run_split_task_case(
        self,
        task_case: dict[str, Any],
        runpod_worker: dict[str, Any],
        summary: dict[str, Any],
        *,
        default_download_dir: Path,
    ) -> dict[str, Any]:
        label = str(task_case["label"])
        payload = task_case["payload"]
        expected_task_type = str(payload["task_type"])
        expected_worker_id = str(runpod_worker.get("agent_id") or "")
        self._phase(summary, f"task_{label}", "running", None)
        submit_payload = self._http_json(
            "POST",
            join_url(self.config.web_api_url, "tasks", "generate"),
            json_body=payload,
            headers=self._web_auth_headers(),
        )
        task_id = str(submit_payload.get("task_id") or "")
        if not task_id:
            raise self._error(f"{label}: missing task_id in Web response")
        summary.setdefault("task_attempts", []).append(
            {
                "label": label,
                "registry_task_id": task_id,
                "task_type": expected_task_type,
                "expected_worker_id": expected_worker_id,
            }
        )
        final_status, pop_evidence = self.wait_task_done(
            task_id=task_id,
            expected_worker_id=expected_worker_id,
        )
        if str(final_status.get("task_type") or "") != expected_task_type:
            raise self._error(
                f"{label}: Central task_type is {final_status.get('task_type')}, "
                f"expected {expected_task_type}"
            )
        if final_status.get("status") != "done":
            raise self._error(
                f"{label}: Central terminal status is {final_status.get('status')}"
            )
        result_payload = self.wait_web_result(task_id)
        result_url = str(result_payload.get("result_url") or "")
        if result_payload.get("status") != "success" or not result_url:
            raise self._error(f"{label}: Web result did not become success")
        result_info = self.download_named_result(
            label=label,
            result_url=result_url,
            default_download_dir=default_download_dir,
        )
        last_frame_info = self.download_last_frame(
            label=label,
            result_payload=result_payload,
            default_download_dir=default_download_dir,
        )
        task_result = {
            "label": label,
            "registry_task_id": task_id,
            "task_type": expected_task_type,
            "central_status": final_status.get("status"),
            "central_task_type": final_status.get("task_type"),
            "expected_worker_id": expected_worker_id,
            "pop_evidence": pop_evidence,
            "web_result_status": result_payload.get("status"),
            "result_path": result_url_path(result_url),
            **result_info,
            **last_frame_info,
        }
        self._phase(summary, f"task_{label}", "ok", task_result)
        return task_result

    def wait_task_done(
        self,
        *,
        task_id: str,
        expected_worker_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        deadline = time.monotonic() + self.config.task_timeout_seconds
        last_status: dict[str, Any] = {}
        pop_evidence: dict[str, Any] = {
            "observed": False,
            "expected_agent_id": expected_worker_id,
            "agent_id": "",
        }
        while time.monotonic() <= deadline:
            status_payload = self._http_json(
                "GET",
                join_url(self.config.central_url, "status", task_id),
                allow_statuses=(404,),
            )
            if status_payload.get("_status") != 404:
                last_status = status_payload
            current_worker = find_worker_current_task(
                self._fetch_workers(),
                expected_worker_id,
                task_id,
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
            self._sleep(self.config.task_poll_interval_seconds)
        raise self._error(
            f"task timeout: {task_id} last_status="
            + json.dumps(redact_payload(last_status), ensure_ascii=False)
        )

    def wait_web_result(self, task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + min(self.config.task_timeout_seconds, 300.0)
        last_result: dict[str, Any] = {}
        while time.monotonic() <= deadline:
            payload = self._http_json(
                "GET",
                join_url(self.config.web_api_url, "tasks", task_id, "result"),
                headers=self._web_auth_headers(),
            )
            last_result = payload
            if payload.get("status") == "success" and payload.get("result_url"):
                return payload
            self._sleep(self.config.task_poll_interval_seconds)
        raise self._error(
            f"web result timeout: {task_id} last_result="
            + json.dumps(redact_payload(last_result), ensure_ascii=False)
        )

    def fetch_result_bytes(self, result_url: str) -> tuple[bytes, str]:
        if self._fetch_result_bytes_override is not None:
            return self._fetch_result_bytes_override(result_url)
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
            raw = self.download_result_bytes_from_s3(result_url)
        if not raw:
            raise self._error(f"downloaded result is empty: {safe_url(result_url)}")
        return raw, method

    def download_result_if_requested(
        self,
        *,
        label: str,
        task_id: str,
        result_url: str,
    ) -> dict[str, str]:
        if self.config.download_results_dir is None:
            return {}
        download_dir = self.config.download_results_dir
        download_dir.mkdir(parents=True, exist_ok=True)
        parsed = urllib.parse.urlsplit(result_url)
        suffix = Path(parsed.path).suffix or ".bin"
        target = download_dir / f"{label}_{task_id}{suffix}"
        raw, method = self.fetch_result_bytes(result_url)
        target.write_bytes(raw)
        return {"downloaded_file": str(target), "download_method": method}

    def validate_wan22_last_frame_if_required(
        self,
        *,
        label: str,
        task_id: str,
        result_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self.config.task_type not in {"wan22_aio_video", "ltx_video"}:
            return {}
        extra_outputs = result_payload.get("extra_outputs")
        last_frame = (
            extra_outputs.get("last_frame") if isinstance(extra_outputs, dict) else None
        )
        if not isinstance(last_frame, dict):
            raise self._error(f"{label}: missing extra_outputs.last_frame")
        last_frame_url = str(last_frame.get("url") or last_frame.get("path") or "")
        if not last_frame_url:
            raise self._error(f"{label}: last_frame is missing url/path")
        raw, method = self.fetch_result_bytes(last_frame_url)
        result: dict[str, Any] = {
            "last_frame_path": result_url_path(last_frame_url),
            "last_frame_bytes": len(raw),
            "last_frame_download_method": method,
        }
        if self.config.download_results_dir is not None:
            download_dir = self.config.download_results_dir
            download_dir.mkdir(parents=True, exist_ok=True)
            parsed = urllib.parse.urlsplit(last_frame_url)
            suffix = Path(parsed.path).suffix or ".png"
            target = download_dir / f"{label}_{task_id}_last_frame{suffix}"
            target.write_bytes(raw)
            result["last_frame_downloaded_file"] = str(target)
        return result

    def download_named_result(
        self,
        *,
        label: str,
        result_url: str,
        default_download_dir: Path,
    ) -> dict[str, Any]:
        download_dir = self.config.download_results_dir or default_download_dir
        download_dir.mkdir(parents=True, exist_ok=True)
        raw, method = self.fetch_result_bytes(result_url)
        if len(raw) < 12 or b"ftyp" not in raw[:64]:
            raise self._error(f"{label}: downloaded result does not look like an MP4")
        target = download_dir / f"{label}.mp4"
        target.write_bytes(raw)
        return {
            "downloaded_file": str(target),
            "download_method": method,
            "downloaded_bytes": len(raw),
        }

    def download_last_frame(
        self,
        *,
        label: str,
        result_payload: dict[str, Any],
        default_download_dir: Path,
    ) -> dict[str, Any]:
        extra_outputs = result_payload.get("extra_outputs")
        last_frame = (
            extra_outputs.get("last_frame") if isinstance(extra_outputs, dict) else None
        )
        if not isinstance(last_frame, dict):
            raise self._error(f"{label}: missing extra_outputs.last_frame")
        last_frame_url = str(last_frame.get("url") or last_frame.get("path") or "")
        if not last_frame_url:
            raise self._error(f"{label}: last_frame is missing url/path")
        raw, method = self.fetch_result_bytes(last_frame_url)
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise self._error(f"{label}: last_frame does not look like a PNG")
        download_dir = self.config.download_results_dir or default_download_dir
        download_dir.mkdir(parents=True, exist_ok=True)
        target = download_dir / f"{label}_last_frame.png"
        target.write_bytes(raw)
        return {
            "last_frame_path": result_url_path(last_frame_url),
            "last_frame_downloaded_file": str(target),
            "last_frame_download_method": method,
            "last_frame_bytes": len(raw),
        }

    def download_result_bytes_from_s3(self, result_url: str) -> bytes:
        object_key = result_url_path(result_url).lstrip("/")
        if not object_key:
            raise self._error("result URL did not contain an object key path")
        endpoint = os.getenv("MINIO_ENDPOINT", "").strip()
        access_key = os.getenv("MINIO_ACCESS_KEY", "").strip()
        secret_key = os.getenv("MINIO_SECRET_KEY", "").strip()
        bucket = os.getenv("MINIO_RESULT_BUCKET", self.config.result_bucket).strip()
        secure = os.getenv("MINIO_SECURE", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not endpoint or not access_key or not secret_key or not bucket:
            raise self._error(
                "R2 S3 fallback is missing MINIO endpoint/credentials/bucket"
            )
        endpoint_url = endpoint
        if "://" not in endpoint_url:
            endpoint_url = f"{'https' if secure else 'http'}://{endpoint_url}"
        try:
            import boto3
        except Exception as exc:
            raise self._error(
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
            raise self._error(
                f"R2 S3 result download failed for {object_key}: {exc}"
            ) from exc
        return body

    def _error(self, message: str) -> Exception:
        return self._error_type(message)


def find_worker_current_task(
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


def write_canary_png(path: Path, *, width: int = 512, height: int = 512) -> None:
    raw_rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            row.extend(
                (
                    (x * 255) // max(1, width - 1),
                    (y * 255) // max(1, height - 1),
                    128,
                )
            )
        raw_rows.append(b"\x00" + bytes(row))
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(
        _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    )
    png.extend(_png_chunk(b"IDAT", zlib.compress(b"".join(raw_rows), level=6)))
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
