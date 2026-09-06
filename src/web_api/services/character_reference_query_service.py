from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select

from shared.character_reference_sheet import INGREDIENTS_CHARACTER_PANEL_VERSION
from src.database.models import CharacterReference
from src.web_api.common.utils import release_read_transaction


@dataclass(frozen=True, slots=True)
class ReadyCharacterIngredient:
    sheet_object_key: str
    description: str


async def resolve_ready_character_sheet(
    *, db, user_id: int, character_id: str
) -> ReadyCharacterIngredient:
    row = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if (
        row is None
        or row.status != "ready"
        or getattr(row, "moderation_status", "active") != "active"
        or not row.sheet_object_key
    ):
        raise HTTPException(status_code=400, detail="人物不存在、未就绪或已删除。")
    if not row.sheet_object_key.endswith(
        f"/{INGREDIENTS_CHARACTER_PANEL_VERSION}.png"
    ):
        raise HTTPException(
            status_code=400,
            detail="人物参考图版本已失效，请重新保存人物。",
        )
    ingredient = ReadyCharacterIngredient(
        sheet_object_key=row.sheet_object_key,
        description=str(row.description or "").strip(),
    )
    await release_read_transaction(db)
    return ingredient
