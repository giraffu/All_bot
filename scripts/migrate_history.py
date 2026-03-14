import sys
import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.core import init_db, AsyncSessionLocal
from src.database.models import History, User

USER_DATA_DIR = "user_data"

async def migrate_history():
    print("Initializing database...")
    await init_db()

    user_data_path = Path(USER_DATA_DIR)
    if not user_data_path.exists():
        print("No user_data directory found.")
        return

    count = 0
    
    async with AsyncSessionLocal() as session:
        # Iterate over all user directories
        for user_dir in user_data_path.iterdir():
            if not user_dir.is_dir():
                continue
                
            user_id_str = user_dir.name
            if not user_id_str.isdigit():
                continue
                
            user_id = int(user_id_str)
            history_file = user_dir / "history.jsonl"
            
            if not history_file.exists():
                continue
                
            print(f"Migrating history for user {user_id}...")
            
            # Ensure user exists
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            if not result.scalar_one_or_none():
                # If user doesn't exist in DB yet (maybe they never checked in or generated but have history?), create them
                # Although they should exist from quota migration.
                session.add(User(id=user_id))
            
            # Read history lines
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            record = json.loads(line)
                            
                            # Check if timestamp exists
                            created_at = datetime.now()
                            if "timestamp" in record:
                                try:
                                    created_at = datetime.fromisoformat(record["timestamp"])
                                except ValueError:
                                    pass
                            
                            # Prepare data
                            input_images = record.get("input_images", [])
                            input_file_str = "|".join(input_images) if isinstance(input_images, list) else str(input_images)
                            
                            history_entry = History(
                                user_id=user_id,
                                task_id=record.get("output_image", "").replace(".png", "") if record.get("output_image") else None, # Rough guess for task_id if not stored explicitly
                                prompt=record.get("prompt"),
                                input_file=input_file_str,
                                output_file=record.get("output_image"),
                                created_at=created_at
                            )
                            session.add(history_entry)
                            count += 1
                            
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                print(f"Error reading {history_file}: {e}")
        
        await session.commit()
    
    print(f"Migration complete! {count} history records imported.")

if __name__ == "__main__":
    asyncio.run(migrate_history())
