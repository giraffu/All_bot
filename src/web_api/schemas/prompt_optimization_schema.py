from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PromptTemplateRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: int = Field(ge=1)


class PromptMediaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["start_image", "end_image"]
    object_key: str


class PromptOptimizationTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_request_id: UUID
    target_task_type: str
    template: PromptTemplateRef
    prompt: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any]
    media: list[PromptMediaInput] = Field(min_length=1, max_length=2)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("prompt must not be blank")
        return normalized


class PromptOptimizationTaskResponse(BaseModel):
    task_id: str
    status: str
    cost: int
    balance_remaining: int

