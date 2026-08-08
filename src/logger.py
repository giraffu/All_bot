import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
import uuid

from asgi_correlation_id import correlation_id
from sqlalchemy import select, text

from .database.core import AsyncSessionLocal
from .database.models import History, User
from .services.storage import storage
from shared.r2_retention_contract import (
    build_staged_user_upload_key,
    build_task_result_key,
)

logger = logging.getLogger("bot")


def setup_logging(log_file="logs/bot.log"):
    """
    Setup standard logging configuration.
    Output to file and console with TraceID.
    """
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    # Configure format with correlation_id
    log_format = (
        "%(asctime)s - %(levelname)s - %(name)s - [%(correlation_id)s] - %(message)s"
    )

    class CorrelationIdFilter(logging.Filter):
        def filter(self, record):
            trace_id = correlation_id.get()
            record.correlation_id = (
                f"TraceID: {trace_id}" if trace_id else "TraceID: None"
            )
            return True

    # Configure root logger
    handlers = [
        RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        ),
        logging.StreamHandler(),
    ]

    for handler in handlers:
        handler.setFormatter(logging.Formatter(log_format))
        handler.addFilter(CorrelationIdFilter())

    logging.basicConfig(level=logging.INFO, handlers=handlers)

    # Reduce noise from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


class UserLogger:
    def __init__(self, user_id: int, username: str = "unknown"):
        self.user_id = int(user_id)  # Store as int for DB
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
        object_name = build_staged_user_upload_key(
            user_id=self.user_id, upload_id=uuid.uuid4().hex, filename=filename
        )

        # Upload to MinIO
        result = storage.upload_file(src_path, object_name)

        if result:
            self.logger.info(
                f"[User:{self.user_id}({self.username})] Saved input to MinIO: {object_name}"
            )
            return object_name
        else:
            self.logger.error(
                f"[User:{self.user_id}({self.username})] Failed to save input to MinIO"
            )
            return ""

    def save_output_image(
        self, image_bytes: bytes, task_id: str, extension: str = "png"
    ) -> str:
        """
        Save generated media bytes to MinIO.
        Returns the object key.
        """
        # Clean extension (remove dot if present)
        ext = extension.lstrip(".")
        filename = f"primary.{ext}"
        object_name = build_task_result_key(
            task_id=task_id, source_name=filename, role="primary"
        )

        # Upload to MinIO
        content_type = "video/mp4" if ext in ["mp4", "webm"] else "image/png"
        result = storage.upload_bytes(
            image_bytes, object_name, content_type=content_type
        )

        if result:
            self.logger.info(
                f"[User:{self.user_id}({self.username})] Saved output to MinIO: {object_name}"
            )
            return object_name
        else:
            self.logger.error(
                f"[User:{self.user_id}({self.username})] Failed to save output to MinIO"
            )
            return ""

    def log_interaction(self, message: str, type: str = "Interaction"):
        """Log user interaction"""
        self.logger.info(f"[User:{self.user_id}({self.username})] {type}: {message}")

    async def log_task(
        self,
        prompt: str,
        input_images: list[str],
        output_image: str,
        task_id: str = None,
        type: str = "image",
        allow_contribute: bool = True,
        source: str = "bot",
        billing_resolution: str | None = None,
        width: int | None = None,
        height: int | None = None,
        duration: int | None = None,
        requested_duration: int | None = None,
        extra_outputs: dict | None = None,
    ):
        """
        Log task details to database (History table)
        """
        # Join input images with a separator (e.g. |) if multiple
        input_file_str = "|".join(input_images) if input_images else ""

        self.logger.info(
            f"[User:{self.user_id}({self.username})] Task Completed ({type}). Prompt: '{prompt}'"
        )

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

            previous_generation_count = int(user.generation_count or 0)
            existing_history = None
            if task_id:
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {
                        "lock_key": f"history:{self.user_id}:{task_id}:{source}",
                    },
                )
                existing_result = await session.execute(
                    select(History)
                    .where(
                        History.user_id == self.user_id,
                        History.task_id == task_id,
                        History.source == source,
                    )
                    .order_by(
                        History.is_visible.desc(),
                        History.is_public.desc(),
                        History.id.asc(),
                    )
                    .limit(1)
                )
                existing_history = existing_result.scalar_one_or_none()

            if existing_history:
                existing_history.type = type
                existing_history.prompt = prompt
                existing_history.input_file = input_file_str
                existing_history.output_file = output_image
                existing_history.extra_outputs = extra_outputs
                existing_history.billing_resolution = billing_resolution
                existing_history.width = width
                existing_history.height = height
                existing_history.duration = duration
                existing_history.requested_duration = requested_duration
                existing_history.allow_contribute = allow_contribute
                user.last_activity = datetime.now()
                from .services.media_archive_service import enqueue_history_media_archive

                await enqueue_history_media_archive(session, existing_history)
                await session.commit()
                return False

            history_entry = History(
                user_id=self.user_id,
                task_id=task_id,
                type=type,
                prompt=prompt,
                input_file=input_file_str,
                output_file=output_image,
                extra_outputs=extra_outputs,
                billing_resolution=billing_resolution,
                width=width,
                height=height,
                duration=duration,
                requested_duration=requested_duration,
                created_at=datetime.now(),
                allow_contribute=allow_contribute,
                source=source,
            )
            session.add(history_entry)

            from .services.media_archive_service import enqueue_history_media_archive

            await enqueue_history_media_archive(session, history_entry)

            # Update user stats
            user.generation_count = previous_generation_count + 1
            user.last_activity = datetime.now()

            if previous_generation_count == 0:
                from src.quota import QuotaManager

                await QuotaManager().process_generation_referral_reward(
                    self.user_id, session=session
                )

            await session.commit()
            return True
