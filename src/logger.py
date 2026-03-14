import os
import json
import shutil
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
from .database.core import AsyncSessionLocal
from .database.models import History, User

USER_DATA_DIR = "user_data"

def setup_logging(log_file="logs/bot.log"):
    """
    Setup standard logging configuration.
    Output to file and console.
    """
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        handlers=[
            RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # Reduce noise from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

class UserLogger:
    def __init__(self, user_id: int, username: str = "unknown"):
        self.user_id = int(user_id) # Store as int for DB
        self.username = username
        self.base_dir = Path(USER_DATA_DIR) / str(self.user_id)
        self.input_dir = self.base_dir / "input_images"
        self.output_dir = self.base_dir / "output_images"
        # self.log_file = self.base_dir / "history.jsonl" # Deprecated
        
        self._ensure_dirs()
        self.logger = logging.getLogger("bot.user")

    def _ensure_dirs(self):
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_input_image(self, src_path: str) -> str:
        """
        Copy input image to user's input directory.
        Returns the filename relative to input directory.
        """
        src = Path(src_path)
        if not src.exists():
            return ""
        
        filename = src.name
        dst = self.input_dir / filename
        shutil.copy2(src, dst)
        
        # Log absolute path
        abs_path = dst.resolve()
        self.logger.info(f"[User:{self.user_id}({self.username})] Saved input: {abs_path}")
        return filename

    def save_output_image(self, image_bytes: bytes, task_id: str, extension: str = "png") -> str:
        """
        Save generated media bytes to user's output directory.
        Returns the filename.
        """
        # Clean extension (remove dot if present)
        ext = extension.lstrip('.')
        filename = f"{task_id}.{ext}"
        dst = self.output_dir / filename
        with open(dst, "wb") as f:
            f.write(image_bytes)
            
        # Log absolute path
        abs_path = dst.resolve()
        self.logger.info(f"[User:{self.user_id}({self.username})] Saved output: {abs_path} (Task: {task_id})")
        return filename

    def log_interaction(self, message: str, type: str = "Interaction"):
        """Log user interaction"""
        self.logger.info(f"[User:{self.user_id}({self.username})] {type}: {message}")

    async def log_task(self, prompt: str, input_images: list[str], output_image: str, task_id: str = None, type: str = "image"):
        """
        Log task details to database (History table)
        """
        # Join input images with a separator (e.g. |) if multiple
        input_file_str = "|".join(input_images) if input_images else ""
        
        self.logger.info(f"[User:{self.user_id}({self.username})] Task Completed ({type}). Prompt: '{prompt}'")
        
        async with AsyncSessionLocal() as session:
            # Ensure user exists (should exist if they have quota, but safety check)
            stmt = select(User).where(User.id == self.user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                # This might happen if log is called before any quota check (unlikely)
                # Or if user is new and somehow bypassed checks.
                # Create minimal user record
                user = User(id=self.user_id)
                session.add(user)
            
            history_entry = History(
                user_id=self.user_id,
                task_id=task_id,
                type=type,
                prompt=prompt,
                input_file=input_file_str,
                output_file=output_image,
                created_at=datetime.now()
            )
            session.add(history_entry)
            
            # Update user stats
            user.generation_count = (user.generation_count or 0) + 1
            user.last_activity = datetime.now()
            
            await session.commit()
