from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class OperationStatus(str, Enum):
    QUEUED = "queued"
    VALIDATING = "validating"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    INTERRUPTED = "interrupted"
    RECOVERY_REQUIRED = "recovery_required"

    def __str__(self) -> str:
        return self.value


TERMINAL_OPERATION_STATUSES = {
    OperationStatus.SUCCEEDED,
    OperationStatus.FAILED,
    OperationStatus.ROLLED_BACK,
    OperationStatus.INTERRUPTED,
    OperationStatus.RECOVERY_REQUIRED,
}


class SwitchRequest(BaseModel):
    target_slot_id: str = Field(min_length=1, max_length=160)
    expected_current_slot_id: str | None = Field(default=None, max_length=160)
    confirmation_profile: str = Field(min_length=1, max_length=100)


class WorkspaceSelectionRequest(BaseModel):
    expected_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    slots: list[Literal["A", "B", "C", "D", "E", "F", "G", "H"]] = Field(
        min_length=1, max_length=8
    )
    confirmation: str = Field(min_length=1, max_length=180)


class ModuleBuildRequest(BaseModel):
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    modules: list[str] = Field(min_length=1, max_length=40)
    confirmation: str = Field(min_length=1, max_length=1000)


class GPUTarget(BaseModel):
    operator: Literal["runpod", "lan"]
    slot: str = Field(min_length=1, max_length=160)


class ModuleDeployRequest(BaseModel):
    environment: Literal["test", "prod"]
    artifacts: dict[str, str] = Field(min_length=1, max_length=40)
    targets: dict[str, GPUTarget] = Field(default_factory=dict)
    confirmation: str = Field(min_length=1, max_length=1000)
