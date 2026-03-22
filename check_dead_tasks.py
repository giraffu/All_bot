import asyncio
from sqlalchemy import select, and_
from src.database.core import AsyncSessionLocal
from src.database.models import UserLog, History
from datetime import datetime, timedelta

async def check_dead_tasks():
    # 假设最近一小时内因重启产生的记录
    time_threshold = datetime.now() - timedelta(hours=2)
    
    async with AsyncSessionLocal() as session:
        # 查找这期间扣费的记录
        stmt = select(UserLog).where(
            and_(
                UserLog.created_at > time_threshold,
                UserLog.credit_change < 0,
                UserLog.operation_type != "refund_restart",
                UserLog.operation_type != "refund"
            )
        )
        result = await session.execute(stmt)
        deductions = result.scalars().all()
        
        # 查找这期间成功的历史记录
        stmt_hist = select(History).where(History.created_at > time_threshold)
        result_hist = await session.execute(stmt_hist)
        histories = result_hist.scalars().all()
        
        # 查找退款记录
        stmt_refund = select(UserLog).where(
            and_(
                UserLog.created_at > time_threshold,
                UserLog.credit_change > 0,
                UserLog.operation_type.in_(["refund_restart", "refund"])
            )
        )
        result_refund = await session.execute(stmt_refund)
        refunds = result_refund.scalars().all()

        print(f"Total deductions in last 2 hours: {len(deductions)}")
        print(f"Total successful generations (history) in last 2 hours: {len(histories)}")
        print(f"Total refunds in last 2 hours: {len(refunds)}")

if __name__ == "__main__":
    asyncio.run(check_dead_tasks())
