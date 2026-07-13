from sqlalchemy import func, select

from src.database.models import User


async def get_user_by_username(session, username: str):
    stmt = select(User).where(func.lower(User.username) == username.lower())
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(session, user_id: int):
    return await session.get(User, user_id)
