from pydantic import BaseModel, Field, field_validator


class CharacterBuildRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=500)
    source_object_key: str = Field(min_length=1, max_length=1024)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("人物名称不能为空")
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


class CharacterResponse(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    task_id: str
    source_object_key: str
    sheet_object_key: str | None
    preview_url: str | None = None


class CharacterBuildResponse(BaseModel):
    character_id: str
    task_id: str
    status: str
    cost: int
    balance_remaining: int
