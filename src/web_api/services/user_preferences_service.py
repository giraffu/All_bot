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
