import asyncio
import os
import sys
from datetime import datetime
from sqlalchemy import select, func, desc

# Add current directory to path so we can import src
sys.path.append(os.getcwd())

from src.database.core import AsyncSessionLocal
from src.database.models import UserLog, History

async def check_data():
    # Target time: 2026-03-16 20:00:00
    target_time = datetime(2026, 3, 16, 20, 0, 0)
    print(f"🔍 查询时间点: {target_time} 之后的记录\n")

    async with AsyncSessionLocal() as session:
        # 1. Check UserLog (User Actions)
        print("--- 📋 用户日志 (UserLog) ---")
        stmt = select(func.count()).select_from(UserLog).where(UserLog.created_at >= target_time)
        result = await session.execute(stmt)
        log_count = result.scalar()
        print(f"📊 记录总数: {log_count}")
        
        if log_count > 0:
            stmt = select(UserLog).where(UserLog.created_at >= target_time).order_by(desc(UserLog.created_at)).limit(10)
            result = await session.execute(stmt)
            logs = result.scalars().all()
            for log in logs:
                print(f"  ⏰ {log.created_at} | 用户: {log.user_id} ({log.username}) | 操作: {log.operation_type} | 变动: {log.credit_change}")
        else:
            print("  (无记录)")
        print("")

        # 2. Check History (Task Generations)
        print("--- 🎨 任务历史 (History) ---")
        stmt = select(func.count()).select_from(History).where(History.created_at >= target_time)
        result = await session.execute(stmt)
        history_count = result.scalar()
        print(f"📊 记录总数: {history_count}")

        if history_count > 0:
            stmt = select(History).where(History.created_at >= target_time).order_by(desc(History.created_at)).limit(10)
            result = await session.execute(stmt)
            histories = result.scalars().all()
            for h in histories:
                print(f"  ⏰ {h.created_at} | 用户: {h.user_id} | 类型: {h.type} | 提示词: {h.prompt[:30]}...")
        else:
            print("  (无记录)")

if __name__ == "__main__":
    asyncio.run(check_data())
