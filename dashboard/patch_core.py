import re

with open('/home/hfy/APP/All_bot/src/database/core.py', 'r') as f:
    content = f.read()

new_migration = """
        try:
            # Check if temporary_ingot column exists
            await conn.execute(text("SELECT temporary_ingot FROM users LIMIT 1"))
        except Exception:
            try:
                logger.info("Adding temporary_ingot column to users table")
                await conn.execute(text("ALTER TABLE users ADD COLUMN temporary_ingot INTEGER DEFAULT 0"))
            except Exception as e:
                logger.warning(f"Failed to add temporary_ingot column: {e}")
"""

content = content.replace('logger.warning(f"Failed to add temp_credits column: {e}")', 'logger.warning(f"Failed to add temp_credits column: {e}")\n' + new_migration)

with open('/home/hfy/APP/All_bot/src/database/core.py', 'w') as f:
    f.write(content)
