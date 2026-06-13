from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .providers.runpod import RUNPOD_TASK_PROFILES, RunPodProvider, redact_payload


@dataclass(frozen=True)
class RunPodWorkersScaleOptions:
    profile: str
    desired: int
    environment: str = "cloud-test"
    execute: bool = False


class RunPodWorkersScaler:
    def __init__(
        self,
        provider: RunPodProvider,
        options: RunPodWorkersScaleOptions,
    ) -> None:
        self.provider = provider
        self.options = options

    def render_scale(self) -> dict[str, Any]:
        self._validate()
        profile = RUNPOD_TASK_PROFILES[self.options.profile]
        requests = [
            self.provider.render_create_pod_request(
                task_type=self.options.profile,
                environment=self.options.environment,
            )
            for _ in range(self.options.desired)
        ]
        return {
            "ok": True,
            "dry_run": True,
            "action": "render-scale",
            "profile": self.options.profile,
            "task_type": profile.task_type,
            "environment": self.options.environment,
            "desired": self.options.desired,
            "would_create_count": self.options.desired,
            "create_requests": requests,
        }

    def scale(self) -> dict[str, Any]:
        self._validate()
        listed = self.provider.list_pods(managed_only=True)
        if not listed.get("ok"):
            return {
                "ok": False,
                "dry_run": True,
                "action": "scale",
                "profile": self.options.profile,
                "error": listed.get("error") or "runpod list-pods failed",
            }
        pods = list(listed.get("pods") or [])
        profile_pods = self._profile_pods(pods)
        delta = self.options.desired - len(profile_pods)
        creates: list[dict[str, Any]] = []
        deletes: list[dict[str, Any]] = []

        if delta > 0:
            for _ in range(delta):
                create = self.provider.create_pod(
                    task_type=self.options.profile,
                    environment=self.options.environment,
                    existing_pods=pods,
                    execute=self.options.execute,
                )
                creates.append(create)
                if create.get("ok") and not create.get("dry_run"):
                    pod = create.get("pod")
                    if isinstance(pod, dict):
                        pods.append(pod)
        elif delta < 0:
            for pod in profile_pods[self.options.desired :]:
                pod_id = str(pod.get("id") or "")
                if not pod_id:
                    continue
                deletes.append(
                    self.provider.delete_pod(
                        pod_id=pod_id,
                        task_type=self.options.profile,
                        existing_pods=pods,
                        execute=self.options.execute,
                    )
                )

        ok = all(item.get("ok") for item in creates + deletes)
        if not creates and not deletes:
            ok = True
        return redact_payload(
            {
                "ok": ok,
                "dry_run": not self.options.execute,
                "action": "scale",
                "execute": self.options.execute,
                "profile": self.options.profile,
                "environment": self.options.environment,
                "desired": self.options.desired,
                "current": len(profile_pods),
                "delta": delta,
                "creates": creates,
                "deletes": deletes,
            }
        )

    def _profile_pods(self, pods: list[dict[str, Any]]) -> list[dict[str, Any]]:
        profile = RUNPOD_TASK_PROFILES[self.options.profile]
        matched: list[dict[str, Any]] = []
        for pod in pods:
            env = pod.get("env") or {}
            if str(env.get("RUNPOD_TASK_TYPE") or "") != profile.task_type:
                continue
            if (
                str(env.get("RUNPOD_ENVIRONMENT") or self.options.environment)
                != self.options.environment
            ):
                continue
            matched.append(pod)
        return matched

    def _validate(self) -> None:
        if self.options.profile not in RUNPOD_TASK_PROFILES:
            supported = ", ".join(sorted(RUNPOD_TASK_PROFILES))
            raise ValueError(
                f"unsupported RunPod workers profile: {self.options.profile}; supported: {supported}"
            )
        if self.options.environment != "cloud-test":
            raise ValueError("runpod workers scale only supports --env cloud-test")
        if self.options.desired < 0:
            raise ValueError("--desired must be >= 0")
