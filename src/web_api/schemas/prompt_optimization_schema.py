from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class H3ReferenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["upload", "private_character_view", "private_character_sheet"]
    object_key: str | None = Field(default=None, max_length=1024)
    character_id: str | None = Field(default=None, max_length=64)
    view_type: Literal[
        "face_front",
        "body_front",
        "body_side",
        "body_back",
        "body_front_nude",
        "body_front_clothed",
        "torso_front",
        "genitals_front",
        "pelvis_back",
        "custom_1",
        "custom_2",
        "custom_3",
        "custom_4",
    ] | None = None

    @model_validator(mode="after")
    def validate_source_fields(self):
        if self.source == "upload":
            if not self.object_key or self.character_id is not None or self.view_type is not None:
                raise ValueError("upload reference requires only object_key")
        elif self.source == "private_character_sheet":
            if not self.character_id or self.object_key is not None or self.view_type is not None:
                raise ValueError("private character sheet requires only character_id")
        elif (
            not self.character_id
            or self.view_type is None
            or self.object_key is not None
        ):
            raise ValueError(
                "private character view requires character_id and view_type"
            )
        return self


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
    reference_refs: list[H3ReferenceRef] | None = Field(default=None, max_length=4)
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
