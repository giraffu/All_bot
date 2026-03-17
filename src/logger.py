import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
from .database.core import AsyncSessionLocal
from .database.models import History, User
from .services.storage import storage

logger = logging.getLogger("bot")

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
        self.logger = logging.getLogger("bot.user")

    def save_input_image(self, src_path: str) -> str:
        """
        Upload input image to MinIO.
        Returns the object key.
        """
        src = Path(src_path)
        if not src.exists():
            return ""
        
        filename = src.name
        # Object key: user_id/input_images/filename
        object_name = f"{self.user_id}/input_images/{filename}"
        
        # Upload to MinIO
        result = storage.upload_file(src_path, object_name)
        
        if result:
            self.logger.info(f"[User:{self.user_id}({self.username})] Saved input to MinIO: {object_name}")
            return object_name
        else:
            self.logger.error(f"[User:{self.user_id}({self.username})] Failed to save input to MinIO")
            return ""

    def save_output_image(self, image_bytes: bytes, task_id: str, extension: str = "png") -> str:
        """
        Save generated media bytes to MinIO.
        Returns the object key.
        """
        # Clean extension (remove dot if present)
        ext = extension.lstrip('.')
        filename = f"{task_id}.{ext}"
        
        # Object key: user_id/output_images/filename
        object_name = f"{self.user_id}/output_images/{filename}"
        
        # Upload to MinIO
        content_type = "video/mp4" if ext in ["mp4", "webm"] else "image/png"
        result = storage.upload_bytes(image_bytes, object_name, content_type=content_type)
        
        if result:
            self.logger.info(f"[User:{self.user_id}({self.username})] Saved output to MinIO: {object_name}")
            return object_name
        else:
            self.logger.error(f"[User:{self.user_id}({self.username})] Failed to save output to MinIO")
            return ""

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
