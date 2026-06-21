from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ops.gpu_pool_controller.lan_aio_prod import load_lan_aio_prod_slots
from ops.gpu_pool_controller.runpod_profile_catalog import RUNPOD_ADMIN_PROFILE_OPTIONS
from ops.gpu_pool_controller.providers.runpod import (
    normalize_prod_worker_profile,
    prod_slot_from_agent_id,
    prod_worker_profile_from_agent_id,
)

RUNPOD_PROFILE_OPTIONS: tuple[dict[str, Any], ...] = RUNPOD_ADMIN_PROFILE_OPTIONS


@dataclass
class RunPodAdminCommandBuilder:
    project_root: Path

    def default_env_file(self, env_name: str, candidates: tuple[Path, ...]) -> str:
        configured = os.getenv(env_name, "").strip()
        if configured:
            return configured
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return str(candidates[0])

    def container_env_file(self) -> Path:
        configured = os.getenv(
            "DASHBOARD_RUNPOD_CONTAINER_ENV_FILE", "/app/.env"
        ).strip()
        return Path(configured)

    def runpod_env_file(self) -> str:
        return self.default_env_file(
            "DASHBOARD_RUNPOD_ENV_FILE",
            (
                self.container_env_file(),
                self.project_root / ".env.cloud.test",
                self.project_root / ".env",
            ),
        )

    def prod_env_file(self) -> str:
        return self.default_env_file(
            "DASHBOARD_RUNPOD_PROD_ENV_FILE",
            (
                self.container_env_file(),
                self.project_root / ".env.cloud.prod",
                self.project_root / ".env",
            ),
        )

    def runpod_ops_script(self) -> str:
        return os.getenv(
            "DASHBOARD_RUNPOD_OPS_SCRIPT",
            str(self.project_root / "scripts" / "runpod_prod_ops.sh"),
        )

    def lan_aio_ops_script(self) -> str:
        return os.getenv(
            "DASHBOARD_LAN_AIO_OPS_SCRIPT",
            str(self.project_root / "scripts" / "lan_aio_fleet_prod_ops.py"),
        )

    def lan_aio_prod_env_file(self) -> str:
        return self.default_env_file(
            "DASHBOARD_LAN_AIO_PROD_ENV_FILE",
            (
                self.container_env_file(),
                self.project_root / ".env.cloud.prod",
                self.project_root / ".env",
            ),
        )

    def lan_aio_aio_env_file(self) -> str:
        return self.default_env_file(
            "DASHBOARD_LAN_AIO_AIO_ENV_FILE",
            (
                self.container_env_file(),
                self.project_root / ".env.lan-aio-prod",
                self.project_root / ".env",
            ),
        )

    def lan_aio_model_env_file(self) -> str:
        return self.default_env_file(
            "DASHBOARD_LAN_AIO_MODEL_ENV_FILE",
            (
                self.container_env_file(),
                self.project_root / ".env.lan.model-cache",
                self.project_root / ".env",
            ),
        )

    def base_command(
        self,
        action: str,
        *,
        profile: str,
        slot: str | None = None,
    ) -> list[str]:
        command = [
            "bash",
            self.runpod_ops_script(),
            action,
            "--profile",
            profile,
            "--runpod-env-file",
            self.runpod_env_file(),
            "--prod-env-file",
            self.prod_env_file(),
        ]
        if slot:
            command.extend(["--slot", slot])
        return command

    def lan_aio_restart_command(self, slot_id: str) -> list[str]:
        return [
            "python3",
            self.lan_aio_ops_script(),
            "restart-aio",
            "--slot",
            slot_id,
            "--prod-env-file",
            self.lan_aio_prod_env_file(),
            "--aio-env-file",
            self.lan_aio_aio_env_file(),
            "--model-env-file",
            self.lan_aio_model_env_file(),
            "--execute",
        ]

    def default_prod_max_manual_slots(self) -> int:
        raw = os.getenv("RUNPOD_PROD_MAX_MANUAL_SLOTS", "").strip()
        if not raw:
            return 100
        try:
            value = int(raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=500,
                detail="RUNPOD_PROD_MAX_MANUAL_SLOTS must be an integer",
            ) from exc
        return max(1, value)

    def operation_env(
        self,
        *,
        prod_max_manual_slots: int | None = None,
    ) -> dict[str, str]:
        env = dict(os.environ)
        for legacy_limit in (
            "RUNPOD_MAX_PODS_TOTAL",
            "RUNPOD_MAX_PODS_PER_TYPE",
            "RUNPOD_MAX_HOURLY_COST_USD",
        ):
            env.pop(legacy_limit, None)
        env["RUNPOD_DRY_RUN"] = "false"
        env["RUNPOD_AUTOSCALER_ENABLED"] = "true"
        env["RUNPOD_PROD_MAX_MANUAL_SLOTS"] = str(
            prod_max_manual_slots or self.default_prod_max_manual_slots()
        )
        return env

    def requested_count_or_422(self, item: Any) -> int:
        raw = item.count if item.count is not None else item.desired_count
        if raw is None:
            raise HTTPException(
                status_code=422,
                detail="items[].count is required",
            )
        requested = int(raw)
        if requested < 1:
            raise HTTPException(
                status_code=422,
                detail="items[].count must be >= 1",
            )
        return requested

    def normalize_profile_or_422(self, profile: str) -> str:
        try:
            return normalize_prod_worker_profile(profile)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def agent_selection_or_422(
        self,
        agent_id: str,
        *,
        max_manual_slots: int,
    ) -> tuple[str, str]:
        try:
            profile = prod_worker_profile_from_agent_id(agent_id)
            slot = prod_slot_from_agent_id(
                agent_id,
                profile=profile,
                max_manual_slots=max_manual_slots,
            )
            return profile, slot
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def lan_aio_slot_selection_or_422(self, agent_id: str):
        normalized_agent_id = str(agent_id or "").strip()
        for slot in load_lan_aio_prod_slots(include_disabled=True).values():
            if slot.agent_id == normalized_agent_id:
                if not slot.enabled:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "LAN AIO slot is not enabled for Dashboard restart: "
                            f"{slot.id}"
                        ),
                    )
                return slot
        raise HTTPException(
            status_code=422,
            detail=f"unsupported LAN AIO worker agent_id: {agent_id}",
        )
