import asyncio
import asyncpg
from datetime import datetime, timedelta

async def main():
    conn = await asyncpg.connect('postgresql://postgres:postgrespassword@192.168.1.115:5432/bot_db')
    
    # 查找最近1小时内状态为 error 的任务
    time_threshold = datetime.utcnow() - timedelta(hours=2)
    
    # 获取表结构
    tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    print("Tables:", [t['table_name'] for t in tables])
    
    if 'tasks' in [t['table_name'] for t in tables]:
        tasks = await conn.fetch("SELECT * FROM tasks WHERE status = 'error' AND created_at > $1", time_threshold)
        print(f"Found {len(tasks)} failed tasks.")
    
    if 'user_logs' in [t['table_name'] for t in tables]:
        # 看看有没有 refund 记录
        logs = await conn.fetch("SELECT * FROM user_logs WHERE created_at > $1 ORDER BY created_at DESC LIMIT 10", time_threshold)
        for log in logs:
            print(dict(log))

    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
