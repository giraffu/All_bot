import asyncio
import asyncpg
from datetime import datetime, timedelta

async def main():
    conn = await asyncpg.connect('postgresql://postgres:postgrespassword@192.168.1.115:5432/bot_db')
    
    # 查找最近 30 分钟的任务
    time_threshold = datetime.utcnow() - timedelta(minutes=30)
    
    # 获取表结构
    cols = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='history'")
    print("History Columns:", [c['column_name'] for c in cols])
    
    histories = await conn.fetch("SELECT * FROM history WHERE created_at > $1 ORDER BY created_at DESC LIMIT 5", time_threshold)
    for h in histories:
        print(dict(h))

    # 查询有没有 refund 的 user_logs
    refund_logs = await conn.fetch("SELECT * FROM user_logs WHERE created_at > $1 AND credit_change > 0 AND operation_type = 'refund'", time_threshold)
    print(f"Found {len(refund_logs)} refund logs in the last 30 minutes.")

    # 查所有 status = 'failed' 或者类似状态的任务
    failed_tasks = await conn.fetch("SELECT * FROM history WHERE created_at > $1 AND status = 'failed'", time_threshold)
    print(f"Found {len(failed_tasks)} failed tasks in history.")
    
    # 查 error 状态的
    error_tasks = await conn.fetch("SELECT * FROM history WHERE created_at > $1 AND status = 'error'", time_threshold)
    print(f"Found {len(error_tasks)} error tasks in history.")

    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
