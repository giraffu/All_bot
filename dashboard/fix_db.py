import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://postgres:postgrespassword@192.168.1.115:5432/bot_db')
    try:
        await conn.execute('ALTER TABLE users ADD COLUMN temporary_ingot INTEGER DEFAULT 0;')
        print("Column added successfully.")
    except Exception as e:
        print(f"Error adding column: {e}")
    finally:
        await conn.close()

asyncio.run(run())
