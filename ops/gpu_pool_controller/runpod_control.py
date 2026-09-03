from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class RunPodControlError(ValueError):
    pass


@dataclass(frozen=True)
class RunPodControlConfig:
    central_url: str
    web_user_id: int
    web_pwd_ver: int
    web_bearer_token: str
    agent_token: str
    jwt_channel: str
    agent_token_required_message: str = "AGENT_SECRET_TOKEN is required for control"


def join_url(base: str, *parts: str) -> str:
    return "/".join([base.rstrip("/"), *(part.strip("/") for part in parts if part)])


class RunPodControlClient:
    def __init__(
        self,
        config: RunPodControlConfig,
        *,
        http_json_func: Callable[..., dict[str, Any]],
        error_type: type[Exception] = RunPodControlError,
    ) -> None:
        self.config = config
        self._http_json = http_json_func
        self._error_type = error_type

    def web_token(self) -> str:
        if self.config.web_bearer_token:
            return self.config.web_bearer_token
        try:
            from src.web_api.core.security import create_access_token
        except Exception as exc:
            raise self._error(f"failed to load Web JWT signer: {exc}") from exc
        return create_access_token(
            subject=str(self.config.web_user_id),
            pwd_ver=self.config.web_pwd_ver,
            channel=self.config.jwt_channel,
        )

    def web_auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.web_token()}"}

    def agent_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.agent_token}"}

    def require_agent_token(self) -> None:
        if not self.config.agent_token:
            raise self._error(self.config.agent_token_required_message)

    def get_agent_control(self, agent_id: str) -> dict[str, Any]:
        self.require_agent_token()
        return self._http_json(
            "GET",
            join_url(
                self.config.central_url,
                "api",
                "agent",
                "task",
                "control",
                agent_id,
            ),
            headers=self.agent_headers(),
        )

    def set_agent_control(
        self,
        agent_id: str,
        state: str,
        *,
        reason: str,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        self.require_agent_token()
        body: dict[str, Any] = {"state": state, "reason": reason}
        if ttl_seconds and state != "enabled":
            body["ttl_seconds"] = ttl_seconds
        return self._http_json(
            "POST",
            join_url(
                self.config.central_url,
                "api",
                "agent",
                "task",
                "control",
                agent_id,
            ),
            json_body=body,
            headers=self.agent_headers(),
        )

    def fetch_workers(self) -> list[dict[str, Any]]:
        payload = self._http_json(
            "GET",
            join_url(self.config.central_url, "system", "workers"),
        )
        workers = payload.get("workers") or []
        if not isinstance(workers, list):
            raise self._error("Central /system/workers returned non-list workers")
        return [worker for worker in workers if isinstance(worker, dict)]

    def _error(self, message: str) -> Exception:
        return self._error_type(message)


def worker_types(worker: dict[str, Any]) -> set[str]:
    return {
        item.strip()
        for item in str(worker.get("types") or "").split(",")
        if item.strip()
    }


def is_cloud_test_non_runpod_worker(worker: dict[str, Any]) -> bool:
    agent_id = str(worker.get("agent_id") or "")
    provider = str(worker.get("provider") or "")
    is_test_lane = agent_id.startswith(
        ("cloud_worker_test_", "lan_aio_test_")
    )
    return is_test_lane and provider != "runpod"


def worker_supports_any_expected_type(
    worker: dict[str, Any],
    *,
    expected_types: tuple[str, ...],
) -> bool:
    return bool(worker_types(worker).intersection(expected_types))


def select_cloud_test_worker_ids_to_disable(
    workers: list[dict[str, Any]],
    *,
    expected_types: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        str(worker.get("agent_id") or "")
        for worker in workers
        if is_cloud_test_non_runpod_worker(worker)
        and worker_supports_any_expected_type(worker, expected_types=expected_types)
    )
