from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User
from src.services.redis_client import redis_client


async def update_user_language_preference(
    *,
    db: AsyncSession,
    user_id: int,
    language_code: str,
) -> dict[str, str]:
    stmt = (
        update(User)
        .where(User.id == user_id)
        .values(language_code=language_code)
    )
    await db.execute(stmt)
    await db.commit()

    if redis_client and redis_client.redis:
        await redis_client.redis.set(
            f"allbot:user_lang:{user_id}",
            language_code,
        )

    return {"status": "success", "language_code": language_code}


async def update_current_user_preferences_payload(
    *,
    prefs,
    current_user,
    db: AsyncSession,
    service_fn=None,
) -> dict[str, str]:
    if service_fn is None:
        service_fn = update_user_language_preference
    return await service_fn(
        db=db,
        user_id=current_user.id,
        language_code=prefs.language_code,
    )
