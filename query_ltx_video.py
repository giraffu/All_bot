import asyncio
import os
import sys

sys.path.append(os.getcwd())

from sqlalchemy import select, func, desc
from src.database.core import AsyncSessionLocal
from src.database.models import User, UserLog
from src.constants import MODE_LTX_VIDEO

async def calculate_ltx_video_spending():
    async with AsyncSessionLocal() as session:
        stmt = (
            select(
                User.telegram_id,
                User.username,
                func.sum(-UserLog.credit_change).label("total_spent")
            )
            .join(UserLog, User.id == UserLog.user_id)
            .where(UserLog.operation_type == MODE_LTX_VIDEO)
            .group_by(User.telegram_id, User.username)
            .order_by(desc("total_spent"))
        )
        
        result = await session.execute(stmt)
        rows = result.all()
        
        print(f"| {'Telegram ID':<15} | {'Username':<20} | {'Total Spent':<15} |")
        print(f"|{'-'*17}|{'-'*22}|{'-'*17}|")
        
        if not rows:
            print("暂无消耗记录。")
            return

        for row in rows:
            username = row.username if row.username else "Unknown"
            print(f"| {row.telegram_id:<15} | {username:<20} | {row.total_spent:<15} |")

if __name__ == "__main__":
    asyncio.run(calculate_ltx_video_spending())
