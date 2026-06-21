from __future__ import annotations

import json
import os
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .providers.runpod import RUNPOD_PROD_BUCKET, redact_payload
from .runpod_canary import (
    SCAIL2_CANARY_NEGATIVE_PROMPT,
    SCAIL2_SAMPLE_MOTION_VIDEO_URL,
    SCAIL2_SAMPLE_REFERENCE_URL,
    result_url_path,
    write_canary_png,
)
from .runpod_prod_worker_control import join_url
from .runpod_prod_worker_http import safe_url


PROD_TASK_TYPE = "img2img"
PROD_IMAGE_TO_VIDEO_TASK_TYPE = "image_to_video"
PROD_WAN22_VIDEO_V2_TASK_TYPE = "wan22_video_v2"
PROD_I2I_PRO_TASK_TYPE = "i2i_pro"
PROD_SCAIL2_ACTION_TRANSFER_TASK_TYPE = "scail2_action_transfer"
PROD_SCAIL2_VIDEO_REPLACEMENT_TASK_TYPE = "scail2_video_replacement"
PROD_TXT2IMG_PUBLIC_TASK_TYPE = "txt2img"
PROD_TXT2IMG_EXECUTION_TASK_TYPE = "t2i-pornmaster-turbo"
PROD_FACE_SWAP_TASK_TYPE = "face_swap"
TERMINAL_TASK_STATUSES = {"done", "error", "cancelled"}


class RunPodProdWorkerCanaryError(ValueError):
    pass


@dataclass(frozen=True)
class RunPodProdWorkerCanaryConfig:
    profile: str
    task_type: str
    agent_id: str
    web_api_url: str
    central_url: str
    input_object_key: str
    scail2_reference_object_key: str
    scail2_motion_video_object_key: str
    output_dir: Path
    download_results_dir: Path
    task_timeout_seconds: float
    task_poll_interval_seconds: float
    prompt: str
    negative_prompt: str


class RunPodProdWorkerCanaryCaseBuilder:
    def __init__(
        self,
        config: RunPodProdWorkerCanaryConfig,
        *,
        error_type: type[Exception] = RunPodProdWorkerCanaryError,
    ) -> None:
        self.config = config
        self._error_type = error_type

    def dry_run_steps(self) -> list[str]:
        if self.config.profile == "i2i_pro":
            task_summary = "submit prod Web i2i_pro, txt2img, and face_swap tasks serially"
        elif self.config.profile == "scail2":
            task_summary = (
                "submit prod Web scail2_action_transfer and "
                "scail2_video_replacement 5s tasks serially"
            )
        else:
            task_summary = (
                f"submit one prod Web {self.config.task_type} task "
                "as internal user_id=3"
            )
        return [
            f"verify {self.config.agent_id} heartbeat in prod Central",
            f"temporarily set {self.config.agent_id} control to enabled",
            (
                "upload or reuse one reference image and one motion video in "
                "user-data-prod"
                if self.config.profile == "scail2"
                else "upload or reuse one non-sensitive PNG in user-data-prod"
            ),
            task_summary,
            "download the result to runpod_canary_results/prod/<date>/",
            f"restore {self.config.agent_id} control to disabled",
        ]

    def scail2_task_cases(self, test_input: dict[str, str]) -> list[dict[str, Any]]:
        reference_key = str(test_input.get("reference_image_key") or "")
        motion_key = str(test_input.get("motion_video_key") or "")
        if not reference_key or not motion_key:
            raise self._error(
                "SCAIL-2 prod canary requires reference_image_key and motion_video_key"
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
                "label": "prod_scail2_action_transfer_5s",
                "expected_central_task_type": PROD_SCAIL2_ACTION_TRANSFER_TASK_TYPE,
                "payload": {
                    "task_type": PROD_SCAIL2_ACTION_TRANSFER_TASK_TYPE,
                    "inputs": dict(base_inputs),
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "priority": 0,
                },
                "result_kind": "video",
            },
            {
                "label": "prod_scail2_video_replacement_5s",
                "expected_central_task_type": PROD_SCAIL2_VIDEO_REPLACEMENT_TASK_TYPE,
                "payload": {
                    "task_type": PROD_SCAIL2_VIDEO_REPLACEMENT_TASK_TYPE,
                    "inputs": dict(base_inputs),
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "priority": 0,
                },
                "result_kind": "video",
            },
        ]

    def i2i_pro_task_cases(self, image_object_key: str) -> list[dict[str, Any]]:
        return [
            {
                "label": "prod_i2i_pro_canary",
                "expected_central_task_type": PROD_I2I_PRO_TASK_TYPE,
                "payload": {
                    "task_type": PROD_I2I_PRO_TASK_TYPE,
                    "inputs": {
                        "images": [image_object_key],
                        "image": image_object_key,
                        "seed": 20260614,
                    },
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
                    "priority": 0,
                },
                "result_kind": "image",
            },
            {
                "label": "prod_txt2img_canary",
                "expected_central_task_type": PROD_TXT2IMG_EXECUTION_TASK_TYPE,
                "payload": {
                    "task_type": PROD_TXT2IMG_PUBLIC_TASK_TYPE,
                    "inputs": {"seed": 20260614},
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
                    "priority": 0,
                },
                "result_kind": "image",
            },
            {
                "label": "prod_face_swap_canary",
                "expected_central_task_type": PROD_FACE_SWAP_TASK_TYPE,
                "payload": {
                    "task_type": PROD_FACE_SWAP_TASK_TYPE,
                    "inputs": {
                        "images": [image_object_key, image_object_key],
                        "target_image": image_object_key,
                        "face_image": image_object_key,
                    },
                    "prompt": self.config.prompt,
                    "negative_prompt": self.config.negative_prompt,
                    "priority": 0,
                },
                "result_kind": "image",
            },
        ]

    def img2img_task_case(self, image_object_key: str) -> dict[str, Any]:
        return {
            "label": "prod_img2img_canary",
            "phase_name": "task_prod_img2img_canary",
            "payload": {
                "task_type": PROD_TASK_TYPE,
                "inputs": {
                    "images": [image_object_key],
                    "image": image_object_key,
                    "num_inference_steps": 6,
                    "guidance_scale": 1.0,
                    "seed": 20260612,
                },
                "prompt": self.config.prompt,
                "negative_prompt": self.config.negative_prompt,
                "priority": 0,
            },
            "result_kind": "image",
        }

    def image_to_video_task_case(self, image_object_key: str) -> dict[str, Any]:
        return {
            "label": "prod_image_to_video_canary",
            "phase_name": "task_prod_image_to_video_canary",
            "expected_central_task_type": PROD_IMAGE_TO_VIDEO_TASK_TYPE,
            "payload": {
                "task_type": PROD_IMAGE_TO_VIDEO_TASK_TYPE,
                "inputs": {
                    "images": [image_object_key],
                    "image": image_object_key,
                    "resolution": "preview",
                    "resolution_preset": "preview",
                    "duration": 5,
                    "duration_seconds": 5,
                    "extract_last_frame": True,
                    "seed": 20260613,
                    "negative_prompt": self.config.negative_prompt,
                    "wan22_model_profile": "legacy_image_to_video",
                },
                "prompt": self.config.prompt,
                "negative_prompt": self.config.negative_prompt,
                "priority": 0,
            },
            "result_kind": "video_last_frame",
        }

    def wan22_video_v2_task_case(self, image_object_key: str) -> dict[str, Any]:
        return {
            "label": "prod_wan22_video_v2_canary",
            "phase_name": "task_prod_wan22_video_v2_canary",
            "expected_central_task_type": PROD_WAN22_VIDEO_V2_TASK_TYPE,
            "payload": {
                "task_type": PROD_WAN22_VIDEO_V2_TASK_TYPE,
                "inputs": {
                    "images": [image_object_key],
                    "image": image_object_key,
                    "resolution": "preview",
                    "resolution_preset": "preview",
                    "duration": 5,
                    "duration_seconds": 5,
                    "extract_last_frame": True,
                    "seed": 20260613,
                    "negative_prompt": self.config.negative_prompt,
                    "wan22_model_profile": "wan22_video_v2",
                },
                "prompt": self.config.prompt,
                "negative_prompt": self.config.negative_prompt,
                "priority": 0,
            },
            "result_kind": "video_last_frame",
        }

    def _error(self, message: str) -> Exception:
        return self._error_type(message)


class RunPodProdWorkerCanaryAssets:
    def __init__(
        self,
        config: RunPodProdWorkerCanaryConfig,
        *,
        http_json_func: Callable[..., dict[str, Any]],
        http_request_func: Callable[..., dict[str, Any]],
        web_auth_headers_func: Callable[[], dict[str, str]],
        phase_func: Callable[
            [dict[str, Any], str, str | None, dict[str, Any] | None],
            None,
        ],
        error_type: type[Exception] = RunPodProdWorkerCanaryError,
    ) -> None:
        self.config = config
        self._http_json = http_json_func
        self._http_request = http_request_func
        self._web_auth_headers = web_auth_headers_func
        self._phase = phase_func
        self._error_type = error_type

    def resolve_canary_image(self, summary: dict[str, Any]) -> str:
        object_key = self.config.input_object_key.strip()
        if object_key:
            self._phase(
                summary,
                "reuse_prod_test_image",
                "ok",
                {"object_key": object_key},
            )
            return object_key
        return self.upload_canary_image(summary)

    def upload_canary_image(self, summary: dict[str, Any]) -> str:
        self._phase(summary, "upload_prod_test_image", "running", None)
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        image_path = (
            self.config.output_dir / f"runpod_prod_canary_{int(time.time())}.png"
        )
        write_canary_png(image_path)
        object_key = self.upload_bytes_to_user_data(
            filename=image_path.name,
            content_type="image/png",
            body=image_path.read_bytes(),
        )
        self._phase(
            summary,
            "upload_prod_test_image",
            "ok",
            {"object_key": object_key},
        )
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

    def resolve_scail2_inputs(self, summary: dict[str, Any]) -> dict[str, str]:
        reference_key = (
            str(self.config.scail2_reference_object_key or "").strip()
            or str(self.config.input_object_key or "").strip()
        )
        motion_key = str(self.config.scail2_motion_video_object_key or "").strip()
        reused: dict[str, str] = {}
        if reference_key:
            reused["reference_image_key"] = reference_key
        if motion_key:
            reused["motion_video_key"] = motion_key
        if reused:
            self._phase(summary, "reuse_prod_scail2_inputs", "ok", reused)
        if not reference_key:
            self._phase(
                summary,
                "upload_prod_scail2_reference_image",
                "running",
                None,
            )
            reference_bytes = self.download_scail2_sample(
                SCAIL2_SAMPLE_REFERENCE_URL,
                label="reference image",
            )
            reference_key = self.upload_bytes_to_user_data(
                filename=f"prod_scail2_reference_{int(time.time())}.jpg",
                content_type="image/jpeg",
                body=reference_bytes,
            )
            self._phase(
                summary,
                "upload_prod_scail2_reference_image",
                "ok",
                {"object_key": reference_key, "bytes": len(reference_bytes)},
            )
        if not motion_key:
            self._phase(summary, "upload_prod_scail2_motion_video", "running", None)
            motion_bytes = self.download_scail2_sample(
                SCAIL2_SAMPLE_MOTION_VIDEO_URL,
                label="motion video",
            )
            motion_key = self.upload_bytes_to_user_data(
                filename=f"prod_scail2_motion_{int(time.time())}.mp4",
                content_type="video/mp4",
                body=motion_bytes,
            )
            self._phase(
                summary,
                "upload_prod_scail2_motion_video",
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
            headers={"User-Agent": "AllBot-RunPod-Prod-SCAIL2-Canary/1.0"},
            expected_statuses=(200,),
        )
        raw = response["raw"]
        if not raw:
            raise self._error(
                f"SCAIL-2 prod canary sample {label} download returned empty"
            )
        return raw

    def _error(self, message: str) -> Exception:
        return self._error_type(message)


class RunPodProdWorkerCanaryExecutor:
    def __init__(
        self,
        config: RunPodProdWorkerCanaryConfig,
        *,
        http_json_func: Callable[..., dict[str, Any]],
        http_request_func: Callable[..., dict[str, Any]],
        web_auth_headers_func: Callable[[], dict[str, str]],
        fetch_workers_func: Callable[[], list[dict[str, Any]]],
        sleep_func: Callable[[float], None],
        phase_func: Callable[
            [dict[str, Any], str, str | None, dict[str, Any] | None],
            None,
        ],
        error_type: type[Exception] = RunPodProdWorkerCanaryError,
    ) -> None:
        self.config = config
        self._http_json = http_json_func
        self._http_request = http_request_func
        self._web_auth_headers = web_auth_headers_func
        self._fetch_workers = fetch_workers_func
        self._sleep = sleep_func
        self._phase = phase_func
        self._error_type = error_type

    def run_task_case(
        self,
        task_case: dict[str, Any],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        label = str(task_case["label"])
        phase_name = str(task_case.get("phase_name") or f"task_{label}")
        expected_task_type = str(task_case.get("expected_central_task_type") or "")
        self._phase(summary, phase_name, "running", None)
        submit_payload = self._http_json(
            "POST",
            join_url(self.config.web_api_url, "tasks", "generate"),
            json_body=task_case["payload"],
            headers=self._web_auth_headers(),
        )
        task_id = str(submit_payload.get("task_id") or "")
        if not task_id:
            prefix = f"{label}: " if expected_task_type else ""
            raise self._error(f"{prefix}missing task_id in Web response")
        final_status, pop_evidence = self.wait_task_done(task_id)
        task_result: dict[str, Any] = {
            "label": label,
            "registry_task_id": task_id,
            "task_type": task_case["payload"]["task_type"],
            "central_status": final_status.get("status"),
            "central_task_type": final_status.get("task_type"),
            "pop_evidence": pop_evidence,
        }
        if expected_task_type:
            task_result["expected_central_task_type"] = expected_task_type
            if str(final_status.get("task_type") or "") != expected_task_type:
                if label in {"prod_image_to_video_canary", "prod_wan22_video_v2_canary"}:
                    raise self._error(
                        "prod canary Central task_type is "
                        f"{final_status.get('task_type')}, expected {expected_task_type}"
                    )
                raise self._error(
                    f"{label}: Central task_type is {final_status.get('task_type')}, "
                    f"expected {expected_task_type}"
                )
        if final_status.get("status") != "done":
            if label in {"prod_img2img_canary", "prod_image_to_video_canary", "prod_wan22_video_v2_canary"}:
                raise self._error(
                    "prod canary Central terminal status is "
                    f"{final_status.get('status')}"
                )
            raise self._error(
                f"{label}: Central terminal status is {final_status.get('status')}"
            )
        result_payload = self.wait_web_result(task_id)
        result_url = str(result_payload.get("result_url") or "")
        task_result["web_result_status"] = result_payload.get("status")
        task_result["result_path"] = result_url_path(result_url)
        if result_payload.get("status") != "success" or not result_url:
            if label in {"prod_img2img_canary", "prod_image_to_video_canary", "prod_wan22_video_v2_canary"}:
                raise self._error("prod canary Web result did not become success")
            raise self._error(f"{label}: Web result did not become success")
        result_kind = str(task_case.get("result_kind") or "image")
        if result_kind == "video":
            task_result.update(
                self.download_video_result(
                    task_id=task_id,
                    result_url=result_url,
                    artifact_prefix=label,
                )
            )
        elif result_kind == "video_last_frame":
            task_result.update(
                self.download_video_result(
                    task_id=task_id,
                    result_url=result_url,
                    artifact_prefix=label,
                )
            )
            task_result.update(
                self.download_last_frame(
                    task_id=task_id,
                    result_payload=result_payload,
                    artifact_prefix=label,
                )
            )
        else:
            task_result.update(
                self.download_result(
                    task_id=task_id,
                    result_url=result_url,
                    artifact_prefix=label,
                )
            )
        self._phase(summary, phase_name, "ok", task_result)
        return task_result

    def wait_task_done(
        self,
        task_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        deadline = time.monotonic() + self.config.task_timeout_seconds
        last_status: dict[str, Any] = {}
        pop_evidence: dict[str, Any] = {
            "observed": False,
            "expected_agent_id": self.config.agent_id,
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
            current_worker = find_current_task_worker(self._fetch_workers(), task_id)
            if current_worker:
                pop_evidence = {
                    "observed": True,
                    "expected_agent_id": self.config.agent_id,
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
            self._sleep(self.config.task_poll_interval_seconds)
        raise self._error(
            f"prod canary task timeout: {task_id} last_status="
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
            f"prod canary web result timeout: {task_id} last_result="
            + json.dumps(redact_payload(last_result), ensure_ascii=False)
        )

    def download_result(
        self,
        *,
        task_id: str,
        result_url: str,
        artifact_prefix: str = "prod_img2img_canary",
    ) -> dict[str, str]:
        download_dir = self.config.download_results_dir
        download_dir.mkdir(parents=True, exist_ok=True)
        parsed = urllib.parse.urlsplit(result_url)
        suffix = Path(parsed.path).suffix or ".bin"
        target = download_dir / f"{artifact_prefix}_{task_id}{suffix}"
        raw, method = self.fetch_result_bytes(result_url)
        target.write_bytes(raw)
        return {"downloaded_file": str(target), "download_method": method}

    def download_video_result(
        self,
        *,
        task_id: str,
        result_url: str,
        artifact_prefix: str,
    ) -> dict[str, Any]:
        raw, method = self.fetch_result_bytes(result_url)
        if len(raw) < 12 or b"ftyp" not in raw[:64]:
            raise self._error("prod video canary result does not look like an MP4")
        download_dir = self.config.download_results_dir
        download_dir.mkdir(parents=True, exist_ok=True)
        target = download_dir / f"{artifact_prefix}_{task_id}.mp4"
        target.write_bytes(raw)
        return {
            "downloaded_file": str(target),
            "download_method": method,
            "downloaded_bytes": len(raw),
        }

    def download_last_frame(
        self,
        *,
        task_id: str,
        result_payload: dict[str, Any],
        artifact_prefix: str,
    ) -> dict[str, Any]:
        extra_outputs = result_payload.get("extra_outputs")
        last_frame = (
            extra_outputs.get("last_frame") if isinstance(extra_outputs, dict) else None
        )
        if not isinstance(last_frame, dict):
            raise self._error("prod video canary missing extra_outputs.last_frame")
        last_frame_url = str(last_frame.get("url") or last_frame.get("path") or "")
        if not last_frame_url:
            raise self._error("prod video canary last_frame is missing url/path")
        raw, method = self.fetch_result_bytes(last_frame_url)
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise self._error("prod video canary last_frame does not look like a PNG")
        download_dir = self.config.download_results_dir
        download_dir.mkdir(parents=True, exist_ok=True)
        target = download_dir / f"{artifact_prefix}_{task_id}_last_frame.png"
        target.write_bytes(raw)
        return {
            "last_frame_path": result_url_path(last_frame_url),
            "last_frame_downloaded_file": str(target),
            "last_frame_download_method": method,
            "last_frame_bytes": len(raw),
        }

    def fetch_result_bytes(self, result_url: str) -> tuple[bytes, str]:
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
            raw = self.download_result_bytes_from_s3(result_url)
        if not raw:
            raise self._error(f"downloaded result is empty: {safe_url(result_url)}")
        return raw, method

    def download_result_bytes_from_s3(self, result_url: str) -> bytes:
        object_key = result_url_path(result_url).lstrip("/")
        if not object_key:
            raise self._error("result URL did not contain an object key path")
        endpoint = os.getenv("MINIO_ENDPOINT", "").strip()
        access_key = os.getenv("MINIO_ACCESS_KEY", "").strip()
        secret_key = os.getenv("MINIO_SECRET_KEY", "").strip()
        bucket = os.getenv("MINIO_RESULT_BUCKET", RUNPOD_PROD_BUCKET).strip()
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


def find_current_task_worker(
    workers: list[dict[str, Any]],
    task_id: str,
) -> dict[str, Any] | None:
    for worker in workers:
        if str(worker.get("current_task_id") or "") == task_id:
            return worker
    return None
