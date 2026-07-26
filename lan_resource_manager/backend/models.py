from __future__ import annotations

from enum import Enum

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
