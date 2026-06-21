from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .runpod_control import RunPodControlClient, RunPodControlConfig, join_url


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


class RunPodProdWorkerControlClient(RunPodControlClient):
    def __init__(
        self,
        config: RunPodProdWorkerControlConfig,
        *,
        http_json_func: Callable[..., dict[str, Any]],
        error_type: type[Exception] = RunPodProdWorkerControlError,
    ) -> None:
        self.prod_worker_config = config
        super().__init__(
            RunPodControlConfig(
                central_url=config.central_url,
                web_user_id=config.web_user_id,
                web_pwd_ver=config.web_pwd_ver,
                web_bearer_token=config.web_bearer_token,
                agent_token=config.agent_token,
                jwt_channel="runpod_prod_worker",
                agent_token_required_message=(
                    "AGENT_SECRET_TOKEN is required for prod-worker control"
                ),
            ),
            http_json_func=http_json_func,
            error_type=error_type,
        )


__all__ = [
    "RunPodProdWorkerControlClient",
    "RunPodProdWorkerControlConfig",
    "RunPodProdWorkerControlError",
    "join_url",
]
