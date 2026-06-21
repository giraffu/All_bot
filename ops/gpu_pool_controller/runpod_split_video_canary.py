from __future__ import annotations

import json
import struct
import time
import zlib
from pathlib import Path
from typing import Any

from .providers.runpod import (
    RUNPOD_TASK_PROFILES,
    RunPodProvider,
    redact_payload,
    redact_text,
)
from .runpod_canary import (
    EXPECTED_MODEL_BUCKET,
    EXPECTED_RUNPOD_CLOUD_TEST_CENTRAL_URL,
    EXPECTED_TEST_BUCKET,
    HEALTHY_WORKER_STATUSES,
    RunPodCanaryError,
    RunPodCanaryOptions,
    RunPodCanaryRunner,
    TERMINAL_TASK_STATUSES,
    _extract_pod_id,
    _canary_profile_spec,
    _find_runpod_worker,
    _find_worker_current_task,
    _is_cloud_test_non_runpod_worker,
    _join_url,
    _pod_summary,
    _utc_now_iso,
    _worker_summary,
    _worker_supports_any_expected_type,
    _worker_supports_expected_types,
    result_url_path,
)
from .runpod_video_manifests import (
    create_model_r2_client_from_env,
    prepare_split_video_manifests,
)


SPLIT_VIDEO_PROFILES = ("image_to_video", "wan22_video_v2")
SPLIT_VIDEO_TASK_TYPES = ("image_to_video", "wan22_video_v2")
DEFAULT_SPLIT_VIDEO_PROMPT = "镜头中出现一个女人"
DEFAULT_SPLIT_VIDEO_RESULTS_DIR = Path("runpod_video_test_results")


class RunPodSplitVideoCanaryRunner(RunPodCanaryRunner):
    def __init__(
        self,
        provider: RunPodProvider,
        options: RunPodCanaryOptions,
        profiles: tuple[str, ...] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(provider, options, **kwargs)
        self.active_profiles = self._normalize_profiles(profiles)

    def run(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "ok": False,
            "execute": self.options.execute,
            "environment": self.options.environment,
            "task_type": "split_video_profiles",
            "profiles": list(self.active_profiles),
            "started_at": _utc_now_iso(),
            "phases": [],
            "reuse_pod_ids": dict(self.options.reuse_pod_ids),
            "cleanup": {
                "requested": self.options.cleanup,
                "worker_restore": [],
                "pod_delete": [],
            },
        }
        pod_ids: dict[str, str] = {}
        worker_controls: list[dict[str, Any]] = []
        try:
            self._validate_static_options()
            self._prepare_split_manifests(summary)
            self._run_runpod_preflight(summary)
            if not self.options.execute:
                summary["ok"] = True
                summary["would_execute"] = [
                    "upload split image_to_video and wan22_video_v2 model manifests",
                    f"create {len(self.active_profiles)} RunPod cloud-test pod(s): "
                    + ", ".join(self.active_profiles),
                    "wait for infrastructure readiness and Central worker heartbeat(s)",
                    "temporarily disable non-RunPod cloud-test workers supporting active split video task types",
                    "upload or reuse one neutral 512x512 PNG object in user-data-test",
                    "submit Web /api/tasks/generate video task(s) for active profiles",
                    "download MP4 and last_frame PNG files to runpod_video_test_results/",
                    "restore test workers and delete created RunPod pod(s)",
                ]
            else:
                self._run_web_preflight(summary)
                pod_ids = self._create_pods(summary)
                for profile, pod_id in pod_ids.items():
                    self._wait_pod_readiness_for_profile(profile, pod_id, summary)
                runpod_workers = {
                    profile: self._wait_runpod_worker_for_profile(
                        profile, pod_id, summary
                    )
                    for profile, pod_id in pod_ids.items()
                }
                if self.options.disable_workers:
                    worker_controls = self._disable_test_workers(summary)
                image_object_key = self._resolve_canary_image(summary)
                summary["test_input"] = {"object_key": image_object_key}
                summary["tasks"] = []
                for task_case in self._task_cases(image_object_key):
                    worker = runpod_workers[str(task_case["worker_profile"])]
                    task_result = self._run_split_task_case(task_case, worker, summary)
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
                self._cleanup_split(
                    summary=summary,
                    pod_ids=pod_ids,
                    worker_controls=worker_controls,
                )
        return self._finish(summary)

    @staticmethod
    def _normalize_profiles(profiles: tuple[str, ...] | None) -> tuple[str, ...]:
        if not profiles:
            return SPLIT_VIDEO_PROFILES
        normalized: list[str] = []
        invalid: list[str] = []
        for profile in profiles:
            if profile not in SPLIT_VIDEO_PROFILES:
                invalid.append(profile)
                continue
            if profile not in normalized:
                normalized.append(profile)
        if invalid:
            raise RunPodCanaryError(
                "unsupported split video profile(s): " + ", ".join(invalid)
            )
        if not normalized:
            raise RunPodCanaryError("at least one split video profile is required")
        return tuple(normalized)

    @property
    def active_task_types(self) -> tuple[str, ...]:
        task_types: list[str] = []
        for profile_name in self.active_profiles:
            for task_type in RUNPOD_TASK_PROFILES[profile_name].supported_task_types:
                if task_type not in task_types:
                    task_types.append(task_type)
        return tuple(task_types)

    def _validate_static_options(self) -> None:
        if self.options.environment != "cloud-test":
            raise RunPodCanaryError("split video canary only supports --env cloud-test")
        if self.options.execute:
            settings = self.provider.settings
            missing_gates: list[str] = []
            expected_total = len(self.active_profiles)
            if settings.dry_run:
                missing_gates.append("RUNPOD_DRY_RUN=false")
            if not settings.autoscaler_enabled:
                missing_gates.append("RUNPOD_AUTOSCALER_ENABLED=true")
            if settings.max_pods_total != expected_total:
                missing_gates.append(f"RUNPOD_MAX_PODS_TOTAL={expected_total}")
            if settings.max_pods_per_type != 1:
                missing_gates.append("RUNPOD_MAX_PODS_PER_TYPE=1")
            if missing_gates:
                raise RunPodCanaryError(
                    "execute requires split video canary gates: "
                    + ", ".join(missing_gates)
                )
            if self.options.disable_workers and not self.options.agent_token:
                raise RunPodCanaryError(
                    "AGENT_SECRET_TOKEN is required to disable/restore test workers"
                )
            if self.options.reuse_pod_ids:
                invalid_reuse_profiles = sorted(
                    set(self.options.reuse_pod_ids) - set(self.active_profiles)
                )
                missing_reuse_profiles = sorted(
                    set(self.active_profiles) - set(self.options.reuse_pod_ids)
                )
                if invalid_reuse_profiles or missing_reuse_profiles:
                    raise RunPodCanaryError(
                        "--reuse-pod-id must exactly match active profiles"
                    )

    def _prepare_split_manifests(self, summary: dict[str, Any]) -> None:
        self._phase(summary, "split_video_manifests", "running")
        if not self.options.execute:
            summary["split_manifests"] = {
                "dry_run": True,
                "targets": {
                    "image_to_video": self.provider.settings.model_manifest_key_image_to_video,
                    "wan22_video_v2": self.provider.settings.model_manifest_key_wan22_video_v2,
                },
            }
            self._phase(
                summary, "split_video_manifests", "ok", summary["split_manifests"]
            )
            return
        bucket = self.provider.settings.model_bucket
        if not bucket:
            raise RunPodCanaryError(
                "RUNPOD_MODEL_BUCKET is required for split video canary"
            )
        payload = prepare_split_video_manifests(
            client=create_model_r2_client_from_env(),
            bucket=bucket,
            execute=True,
        )
        if not payload.get("ok"):
            raise RunPodCanaryError(
                "split video manifest preparation failed: "
                + json.dumps(redact_payload(payload), ensure_ascii=False)
            )
        summary["split_manifests"] = payload
        self._phase(summary, "split_video_manifests", "ok", payload)

    def _run_runpod_preflight(self, summary: dict[str, Any]) -> None:
        self._phase(summary, "runpod_validate_key", "running")
        validate = self.provider.validate_key()
        self._require_ok(validate, "runpod validate-key failed")
        self._phase(summary, "runpod_validate_key", "ok")

        self._phase(summary, "runpod_list_pods", "running")
        listed = self.provider.list_pods(managed_only=True)
        self._require_ok(listed, "runpod list-pods failed")
        if (
            self.options.execute
            and not self.options.reuse_pod_ids
            and int(listed.get("count") or 0) != 0
        ):
            raise RunPodCanaryError(
                "refusing split video canary: managed RunPod pod count is not 0"
            )
        self._phase(
            summary, "runpod_list_pods", "ok", {"count": listed.get("count", 0)}
        )

        self._phase(summary, "runpod_reconcile", "running")
        reconcile = self.provider.reconcile_managed_pods()
        self._require_ok(reconcile, "runpod reconcile-managed-pods failed")
        if (
            self.options.execute
            and not self.options.reuse_pod_ids
            and int(reconcile.get("managed_count") or 0) != 0
        ):
            raise RunPodCanaryError(
                "refusing split video canary: managed RunPod reconcile count is not 0"
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

        renders: dict[str, Any] = {}
        for profile in self.active_profiles:
            self._phase(summary, f"runpod_render_create_{profile}", "running")
            render = self.provider.render_create_pod_request(
                task_type=profile,
                environment=self.options.environment,
                redact=False,
            )
            self._validate_render_for_profile(profile, render)
            renders[profile] = self._render_summary(render)
            self._phase(
                summary, f"runpod_render_create_{profile}", "ok", renders[profile]
            )
        summary["render"] = renders

    def _validate_render_for_profile(
        self, profile_name: str, render: dict[str, Any]
    ) -> None:
        spec = _canary_profile_spec(profile_name)
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
        gpu_type_ids = tuple(str(item) for item in (body.get("gpuTypeIds") or ()))
        if spec.expected_gpu_type_ids and (
            not gpu_type_ids
            or any(item not in spec.expected_gpu_type_ids for item in gpu_type_ids)
        ):
            failures.append(
                "gpuTypeIds must be a non-empty subset of "
                + ",".join(spec.expected_gpu_type_ids)
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
                f"{profile_name} render-create sanity check failed: "
                + "; ".join(failures)
            )

    def _create_pods(self, summary: dict[str, Any]) -> dict[str, str]:
        pod_ids: dict[str, str] = {}
        if self.options.reuse_pod_ids:
            for profile in self.active_profiles:
                pod_id = self.options.reuse_pod_ids[profile]
                self._phase(
                    summary,
                    f"runpod_reuse_pod_{profile}",
                    "ok",
                    {"pod_id": pod_id},
                )
                pod_ids[profile] = pod_id
                summary.setdefault("pods", {})[profile] = {
                    "id": pod_id,
                    "reused": True,
                    "imageName": str(
                        (summary.get("render") or {})
                        .get(profile, {})
                        .get("imageName")
                        or ""
                    ),
                }
            return pod_ids
        try:
            for profile in self.active_profiles:
                self._phase(summary, f"runpod_create_pod_{profile}", "running")
                payload = self.provider.create_pod(
                    task_type=profile,
                    environment=self.options.environment,
                    execute=True,
                )
                self._require_ok(payload, f"runpod create-pod failed for {profile}")
                pod_id = _extract_pod_id(payload)
                pod_ids[profile] = pod_id
                summary.setdefault("pods", {})[profile] = _pod_summary(
                    payload,
                    str(
                        (summary.get("render") or {}).get(profile, {}).get("imageName")
                        or ""
                    ),
                )
                self._phase(
                    summary, f"runpod_create_pod_{profile}", "ok", {"pod_id": pod_id}
                )
        except Exception:
            if self.options.cleanup:
                self._delete_partial_pods(summary, pod_ids)
            raise
        return pod_ids

    def _delete_partial_pods(
        self,
        summary: dict[str, Any],
        pod_ids: dict[str, str],
    ) -> None:
        for profile, pod_id in pod_ids.items():
            delete_payload = self.provider.delete_pod(
                pod_id=pod_id,
                task_type=profile,
                execute=True,
            )
            summary.setdefault("cleanup", {}).setdefault("pod_delete", []).append(
                {
                    "profile": profile,
                    "pod_id": pod_id,
                    "ok": bool(delete_payload.get("ok")),
                    "response": redact_payload(delete_payload),
                    "partial_create_cleanup": True,
                }
            )

    def _wait_pod_readiness_for_profile(
        self,
        profile: str,
        pod_id: str,
        summary: dict[str, Any],
    ) -> None:
        self._phase(summary, f"pod_readiness_{profile}", "running", {"pod_id": pod_id})
        deadline = time.monotonic() + self.options.readiness_timeout_seconds
        last_payload: dict[str, Any] | None = None
        while time.monotonic() <= deadline:
            payload = self.provider.pod_readiness(pod_id=pod_id)
            self._require_ok(payload, f"runpod pod-readiness failed for {profile}")
            last_payload = payload
            readiness = payload.get("readiness") or {}
            if readiness.get("infrastructure_ready") is True:
                summary.setdefault("pod_readiness", {})[profile] = {
                    "pod_id": pod_id,
                    "confidence": readiness.get("confidence"),
                    "network": readiness.get("network"),
                }
                self._phase(
                    summary,
                    f"pod_readiness_{profile}",
                    "ok",
                    summary["pod_readiness"][profile],
                )
                return
            self._sleep(self.options.poll_interval_seconds)
        raise RunPodCanaryError(
            f"{profile} pod readiness timeout: "
            + json.dumps(redact_payload(last_payload), ensure_ascii=False)
        )

    def _wait_runpod_worker_for_profile(
        self,
        profile_name: str,
        pod_id: str,
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        profile = RUNPOD_TASK_PROFILES[profile_name]
        expected_agent_id = f"{profile.agent_id_prefix}_{pod_id}"
        expected_types = profile.supported_task_types
        self._phase(
            summary,
            f"central_runpod_worker_{profile_name}",
            "running",
            {"agent_id": expected_agent_id},
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
                worker, expected_types=expected_types
            ):
                status = str(worker.get("status") or "")
                if status in HEALTHY_WORKER_STATUSES:
                    summary.setdefault("runpod_workers", {})[profile_name] = (
                        _worker_summary(worker)
                    )
                    self._phase(
                        summary,
                        f"central_runpod_worker_{profile_name}",
                        "ok",
                        summary["runpod_workers"][profile_name],
                    )
                    return worker
            self._sleep(self.options.poll_interval_seconds)
        raise RunPodCanaryError(
            f"{profile_name} runpod worker heartbeat timeout: "
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

    def _worker_ids_to_disable(self) -> tuple[str, ...]:
        if self.options.worker_ids_explicit:
            return self.options.worker_ids
        return tuple(
            str(worker.get("agent_id") or "")
            for worker in self._fetch_workers()
            if _is_cloud_test_non_runpod_worker(worker)
            and _worker_supports_any_expected_type(
                worker, expected_types=self.active_task_types
            )
        )

    def _upload_canary_image(self, summary: dict[str, Any]) -> str:
        self._phase(summary, "upload_test_image", "running")
        self.options.output_dir.mkdir(parents=True, exist_ok=True)
        image_path = (
            self.options.output_dir
            / f"runpod_split_video_canary_{int(time.time())}.png"
        )
        write_video_canary_png(image_path)
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

    def _task_cases(self, image_object_key: str) -> list[dict[str, Any]]:
        base_inputs = {
            "images": [image_object_key],
            "image": image_object_key,
            "resolution": "preview",
            "resolution_preset": "preview",
            "duration": 5,
            "duration_seconds": 5,
            "extract_last_frame": True,
            "seed": 20260613,
            "negative_prompt": self.options.negative_prompt,
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
                    "prompt": self.options.prompt,
                    "negative_prompt": self.options.negative_prompt,
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
                    "prompt": self.options.prompt,
                    "negative_prompt": self.options.negative_prompt,
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
                    "prompt": self.options.prompt,
                    "negative_prompt": self.options.negative_prompt,
                    "priority": 0,
                },
            },
        ]
        return [
            case
            for case in cases
            if str(case.get("worker_profile") or "") in self.active_profiles
        ]

    def _run_split_task_case(
        self,
        task_case: dict[str, Any],
        runpod_worker: dict[str, Any],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        label = str(task_case["label"])
        payload = task_case["payload"]
        expected_task_type = str(payload["task_type"])
        expected_worker_id = str(runpod_worker.get("agent_id") or "")
        self._phase(summary, f"task_{label}", "running")
        submit_payload = self._http_json(
            "POST",
            _join_url(self.options.web_api_url, "tasks", "generate"),
            json_body=payload,
            headers=self._web_auth_headers(),
        )
        task_id = str(submit_payload.get("task_id") or "")
        if not task_id:
            raise RunPodCanaryError(f"{label}: missing task_id in Web response")
        summary.setdefault("task_attempts", []).append(
            {
                "label": label,
                "registry_task_id": task_id,
                "task_type": expected_task_type,
                "expected_worker_id": expected_worker_id,
            }
        )
        final_status, pop_evidence = self._wait_task_done(
            task_id=task_id,
            expected_worker_id=expected_worker_id,
        )
        if str(final_status.get("task_type") or "") != expected_task_type:
            raise RunPodCanaryError(
                f"{label}: Central task_type is {final_status.get('task_type')}, expected {expected_task_type}"
            )
        if final_status.get("status") != "done":
            raise RunPodCanaryError(
                f"{label}: Central terminal status is {final_status.get('status')}"
            )
        result_payload = self._wait_web_result(task_id)
        result_url = str(result_payload.get("result_url") or "")
        if result_payload.get("status") != "success" or not result_url:
            raise RunPodCanaryError(f"{label}: Web result did not become success")
        result_info = self._download_named_result(label=label, result_url=result_url)
        last_frame_info = self._download_last_frame(
            label=label, result_payload=result_payload
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

    def _download_named_result(self, *, label: str, result_url: str) -> dict[str, Any]:
        download_dir = (
            self.options.download_results_dir or DEFAULT_SPLIT_VIDEO_RESULTS_DIR
        )
        download_dir.mkdir(parents=True, exist_ok=True)
        raw, method = self._fetch_result_bytes(result_url)
        if len(raw) < 12 or b"ftyp" not in raw[:64]:
            raise RunPodCanaryError(
                f"{label}: downloaded result does not look like an MP4"
            )
        target = download_dir / f"{label}.mp4"
        target.write_bytes(raw)
        return {
            "downloaded_file": str(target),
            "download_method": method,
            "downloaded_bytes": len(raw),
        }

    def _download_last_frame(
        self,
        *,
        label: str,
        result_payload: dict[str, Any],
    ) -> dict[str, Any]:
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
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RunPodCanaryError(f"{label}: last_frame does not look like a PNG")
        download_dir = (
            self.options.download_results_dir or DEFAULT_SPLIT_VIDEO_RESULTS_DIR
        )
        download_dir.mkdir(parents=True, exist_ok=True)
        target = download_dir / f"{label}_last_frame.png"
        target.write_bytes(raw)
        return {
            "last_frame_path": result_url_path(last_frame_url),
            "last_frame_downloaded_file": str(target),
            "last_frame_download_method": method,
            "last_frame_bytes": len(raw),
        }

    def _cleanup_split(
        self,
        *,
        summary: dict[str, Any],
        pod_ids: dict[str, str],
        worker_controls: list[dict[str, Any]],
    ) -> None:
        cleanup = summary.setdefault("cleanup", {})
        cleanup_errors: list[str] = []
        if worker_controls:
            for control in worker_controls:
                agent_id = str(control.get("agent_id") or "")
                state = str(control.get("state") or "enabled")
                reason = str(
                    control.get("reason") or "runpod_split_video_canary_restore"
                )
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
        if self.options.cleanup:
            for profile, pod_id in pod_ids.items():
                try:
                    delete_payload = self.provider.delete_pod(
                        pod_id=pod_id,
                        task_type=profile,
                        execute=True,
                    )
                    if not delete_payload.get("ok"):
                        raise RunPodCanaryError(
                            str(delete_payload.get("error") or "delete failed")
                        )
                    cleanup.setdefault("pod_delete", []).append(
                        {"profile": profile, "pod_id": pod_id, "ok": True}
                    )
                except Exception as exc:
                    cleanup_errors.append(
                        f"delete pod {pod_id}: {redact_text(str(exc))}"
                    )
                    cleanup.setdefault("pod_delete", []).append(
                        {"profile": profile, "pod_id": pod_id, "ok": False}
                    )
        else:
            for profile, pod_id in pod_ids.items():
                cleanup.setdefault("pod_delete", []).append(
                    {"profile": profile, "pod_id": pod_id, "ok": False, "skipped": True}
                )
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

    @staticmethod
    def _finish(summary: dict[str, Any]) -> dict[str, Any]:
        summary["ended_at"] = _utc_now_iso()
        if summary.get("tasks"):
            results_dir = DEFAULT_SPLIT_VIDEO_RESULTS_DIR
            first_task = summary["tasks"][0]
            downloaded = first_task.get("downloaded_file")
            if downloaded:
                results_dir = Path(downloaded).parent
            results_dir.mkdir(parents=True, exist_ok=True)
            summary_path = results_dir / "summary.json"
            summary_path.write_text(
                json.dumps(redact_payload(summary), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            summary["summary_file"] = str(summary_path)
        return redact_payload(summary)


def write_video_canary_png(path: Path, *, width: int = 512, height: int = 512) -> None:
    rows = bytearray()
    cx = width // 2
    head_cy = height // 3
    body_top = height // 2
    for y in range(height):
        rows.append(0)
        for x in range(width):
            r, g, b = 132, 160, 178
            if (x - cx) ** 2 + (y - head_cy) ** 2 < 54**2:
                r, g, b = 218, 178, 144
            elif abs(x - cx) < 76 and body_top <= y < height - 70:
                r, g, b = 96, 74, 126
            elif abs(x - cx) < 28 and head_cy + 44 <= y < body_top + 20:
                r, g, b = 218, 178, 144
            elif abs(x - cx) < 64 and head_cy - 58 <= y < head_cy - 28:
                r, g, b = 52, 44, 48
            rows.extend((r, g, b))
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(
        _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    )
    png.extend(_png_chunk(b"IDAT", zlib.compress(bytes(rows), level=6)))
    png.extend(_png_chunk(b"IEND", b""))
    path.write_bytes(bytes(png))


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)
