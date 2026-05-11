import asyncio
from sqlalchemy import select
from src.database.core import AsyncSessionLocal
from src.database.models import User, UserLog

async def main():
    async with AsyncSessionLocal() as session:
        user = await session.execute(select(User).where(User.id == 10000000021038))
        u = user.scalar_one_or_none()
        if u:
            print(f"User ID: {u.id}, Telegram ID: {u.telegram_id}, Credits: {u.credits}, Identity: {u.current_identity}, Expire: {u.identity_expire_at}")
        
        logs = await session.execute(select(UserLog).where(UserLog.user_id == 10000000021038).order_by(UserLog.id.desc()).limit(5))
        for l in logs.scalars().all():
            print(f"Log: {l.operation_type}, Change: {l.credit_change}, Current: {l.current_balance}, Info: {l.extra_info}")

asyncio.run(main())
