import json
import logging
import os

import aiosqlite

DB_DIR = "data"
os.makedirs(DB_DIR, exist_ok=True)
DB_FILE = os.getenv("SQLITE_DB_PATH", os.path.join(DB_DIR, "group_messages.db"))


async def init_db():
    """初始化数据库并创建表"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                message_id INTEGER,
                user_id INTEGER,
                username TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                message_type TEXT,
                content TEXT,
                media_file_id TEXT,
                raw_data TEXT
            )
        """)
        await db.commit()
    logging.info(f"数据库 {DB_FILE} 已初始化")


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    import datetime

    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


async def save_message(
    chat_id: int,
    message_id: int,
    user_id: int,
    username: str,
    message_type: str,
    content: str,
    media_file_id: str,
    raw_data: dict,
):
    """保存消息到数据库"""
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                """
                INSERT INTO group_messages (
                    chat_id, message_id, user_id, username, 
                    message_type, content, media_file_id, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    message_id,
                    user_id,
                    username,
                    message_type,
                    content,
                    media_file_id,
                    json.dumps(raw_data, default=json_serial, ensure_ascii=False),
                ),
            )
            await db.commit()
    except Exception as e:
        logging.error(f"保存消息失败: {e}")
