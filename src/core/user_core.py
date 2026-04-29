from datetime import datetime
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.database.core import AsyncSessionLocal
from src.database.models import User


async def get_or_create_user_by_telegram(tg_id: int, username: str = None, full_name: str = None) -> Tuple[User, bool]:
    """根据 TG ID 获取内部 User 对象。如果不存在则创建（内部 ID 自动生成）。
    返回: (User实例, 是否为新创建)
    """
    import re
    # 过滤非法的 TG username (通常是因为传入了带有空格或特殊字符的 full_name)
    if username and not re.match(r"^[a-zA-Z0-9_]{4,64}$", username):
        if not full_name:
            full_name = username
        username = None

    async with AsyncSessionLocal() as session:
        # 首先尝试通过 telegram_id 查找
        stmt = select(User).where(User.telegram_id == tg_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            updated = False
            # 只有当用户没有设置密码时（纯TG用户），才允许Telegram用户名覆盖现有道号
            if username and user.username != username and not user.hashed_password:
                user.username = username
                updated = True
            if full_name and user.full_name != full_name:
                user.full_name = full_name
                updated = True
            
            if updated:
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
            return user, False
            
        # 如果不存在 telegram_id，为了兼容第一阶段的遗留数据，也检查一下 id 是否等于 tg_id
        stmt = select(User).where(User.id == tg_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            # 如果按旧 id 查到了，更新 telegram_id
            if not user.telegram_id:
                user.telegram_id = tg_id
                await session.commit()
            return user, False

        # 如果都不存在，说明是全新用户，使用自动生成的内部 ID 创建
        new_user = User(
            telegram_id=tg_id,
            username=username,
            full_name=full_name,
            credits=6,
            last_activity=datetime.now()
        )
        session.add(new_user)
        try:
            await session.commit()
            return new_user, True
        except IntegrityError:
            await session.rollback()
            # 并发创建情况，再次查询
            stmt = select(User).where(User.telegram_id == tg_id)
            result = await session.execute(stmt)
            existing_user = result.scalar_one_or_none()
            if existing_user:
                return existing_user, False
            
            # 如果查询不到，说明不是 telegram_id 冲突，而是 username 冲突
            fallback_user = User(
                telegram_id=tg_id,
                username=None,
                full_name=full_name,
                credits=6,
                last_activity=datetime.now()
            )
            session.add(fallback_user)
            try:
                await session.commit()
                return fallback_user, True
            except IntegrityError:
                await session.rollback()
                raise

async def get_or_create_user_by_google(google_id: str, email: str, full_name: str = None) -> User:
    """根据 Google ID 获取内部 User 对象。如果不存在则创建。"""
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.google_id == google_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            return user

        new_user = User(
            google_id=google_id,
            email=email,
            full_name=full_name,
            credits=6,
            last_activity=datetime.now()
        )
        session.add(new_user)
        try:
            await session.commit()
            return new_user
        except IntegrityError:
            await session.rollback()
            stmt = select(User).where(User.google_id == google_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
