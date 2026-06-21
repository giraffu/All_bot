from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class RunPodProdWorkerControlError(ValueError):
    pass


@dataclass(frozen=True)
class RunPodProdWorkerControlConfig:
    central_url: str
    web_api_url: str
    web_user_id: int
    web_pwd_ver: int
    web_bearer_token: str
    agent_token: str


def join_url(base: str, *parts: str) -> str:
    return "/".join([base.rstrip("/"), *(part.strip("/") for part in parts if part)])


class RunPodProdWorkerControlClient:
    def __init__(
        self,
        config: RunPodProdWorkerControlConfig,
        *,
        http_json_func: Callable[..., dict[str, Any]],
        error_type: type[Exception] = RunPodProdWorkerControlError,
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
            channel="runpod_prod_worker",
        )

    def web_auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.web_token()}"}

    def agent_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.agent_token}"}

    def require_agent_token(self) -> None:
        if not self.config.agent_token:
            raise self._error("AGENT_SECRET_TOKEN is required for prod-worker control")

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
    ) -> dict[str, Any]:
        self.require_agent_token()
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
            json_body={"state": state, "reason": reason},
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
