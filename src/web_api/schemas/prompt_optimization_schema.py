from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PromptTemplateRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: int = Field(ge=1)


class PromptMediaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal[
        "start_image",
        "end_image",
        "reference_character_1",
        "reference_character_2",
        "scene_background",
        "reference_image_1",
        "reference_image_2",
        "reference_image_3",
        "reference_image_4",
    ]
    object_key: str


class PromptLoraItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64)
    strength: float | None = None


class CharacterAssetRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["private", "official"]
    id: str = Field(min_length=1, max_length=64)


class EnvironmentAssetRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["official", "upload"]
    id: str | None = Field(default=None, max_length=64)
    object_key: str | None = Field(default=None, max_length=1024)


class PromptOptimizationTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_request_id: UUID
    target_task_type: str
    template: PromptTemplateRef
    prompt: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any]
    media: list[PromptMediaInput] = Field(default_factory=list, max_length=4)
    character_ids: list[str] = Field(default_factory=list, max_length=2)
    character_refs: list[CharacterAssetRef] | None = Field(default=None, max_length=2)
    environment_ref: EnvironmentAssetRef | None = None
    lora_items: list[PromptLoraItem] = Field(default_factory=list, max_length=5)

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
