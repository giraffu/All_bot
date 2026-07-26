from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field
from typing import Literal


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


class BuildRequest(BaseModel):
    expected_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    confirmation: str = Field(min_length=1, max_length=100)


class DeploymentPlanRequest(BaseModel):
    environment: Literal["test", "prod"]
    module: str = Field(pattern=r"^[a-z0-9-]{1,80}$")
    candidate_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    maintenance: Literal["planner", "rolling"] = "planner"


class DeploymentExecuteRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=180)


class MaintenanceRequest(BaseModel):
    enabled: bool
    expected_enabled: bool
    reason: str = Field(min_length=3, max_length=240)
    confirmation: str = Field(min_length=1, max_length=100)
