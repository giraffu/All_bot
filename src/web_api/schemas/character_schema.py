from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CharacterBuildRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=1, max_length=500)
    source_object_key: str = Field(min_length=1, max_length=1024)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("人物名称不能为空")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("人物描述不能为空")
        return value


class CharacterPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("人物名称不能为空")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("人物描述不能为空")
        return value


class CharacterViewGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1200)
    engine: Literal["free_edit", "free_edit_v2_5", "free_edit_v3"] = "free_edit_v2_5"

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("子图提示词不能为空")
        return value


class CharacterViewUploadRequest(BaseModel):
    source_object_key: str = Field(min_length=1, max_length=1024)


class CharacterBatchCapacityResponse(BaseModel):
    limit: int = Field(ge=1)
    active: int = Field(ge=0)
    available: int = Field(ge=0)


class CharacterViewResponse(BaseModel):
    type: str
    label: str
    prompt: str
    default_prompt: str
    status: str
    task_id: str | None = None
    object_key: str | None = None
    preview_url: str | None = None


class CharacterResponse(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    task_id: str | None
    source_object_key: str
    sheet_object_key: str | None
    preview_url: str | None = None
    views: list[CharacterViewResponse] = Field(default_factory=list)


class CharacterBuildResponse(BaseModel):
    character_id: str
    task_id: str
    status: str
    cost: int
    balance_remaining: int
