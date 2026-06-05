from sqlalchemy import select, text

from src.database.models import User


async def get_user_by_username(session, username: str):
    stmt = (
        select(User)
        .where(text("lower(username) = :uname"))
        .params(uname=username.lower())
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(session, user_id: int):
    return await session.get(User, user_id)
