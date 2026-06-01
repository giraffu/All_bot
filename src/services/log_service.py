import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core import AsyncSessionLocal
from src.database.models import UserLog

logger = logging.getLogger(__name__)


class LogService:
    """
    Service for handling user operation logs with persistence, querying, and retry logic.
    """

    @staticmethod
    async def log_action(
        user_id: int,
        username: Optional[str],
        operation_type: str,
        credit_change: int,
        current_balance: int,
        extra_info: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        session: AsyncSession | None = None,
    ) -> bool:
        """
        Asynchronously log a user action with retry mechanism.

        Args:
            user_id: Telegram User ID
            username: Telegram Username
            operation_type: Type of operation (e.g., 'checkin', 'generate', 'invite')
            credit_change: Amount of credits changed (positive or negative)
            current_balance: Balance after operation
            extra_info: Dictionary containing additional metadata
            max_retries: Number of retry attempts for DB write
            session: Optional existing transaction. When provided, the caller
                owns commit/rollback and logging failures are raised to keep the
                write-path atomic.
        """
        import asyncio

        extra_info_str = json.dumps(extra_info) if extra_info else None
        log_entry = UserLog(
            user_id=user_id,
            username=username,
            operation_type=operation_type,
            credit_change=credit_change,
            current_balance=current_balance,
            created_at=datetime.now(),
            extra_info=extra_info_str,
        )

        if session is not None:
            session.add(log_entry)
            try:
                await session.flush()
            except Exception:
                logger.error(
                    "Failed to stage user log inside existing transaction",
                    exc_info=True,
                )
                raise
            return True

        for attempt in range(max_retries):
            async with AsyncSessionLocal() as session:
                try:
                    log_entry = UserLog(
                        user_id=user_id,
                        username=username,
                        operation_type=operation_type,
                        credit_change=credit_change,
                        current_balance=current_balance,
                        created_at=datetime.now(),
                        extra_info=extra_info_str,
                    )
                    session.add(log_entry)
                    await session.commit()
                    return True
                except SQLAlchemyError as e:
                    await session.rollback()
                    if attempt == max_retries - 1:
                        logger.error(
                            f"Failed to write user log after {max_retries} attempts: {e}",
                            exc_info=True,
                        )
                        return False
                    logger.warning(
                        f"Database error writing log (attempt {attempt + 1}/{max_retries}): {e}"
                    )
                    await asyncio.sleep(0.1 * (2**attempt))  # Exponential backoff
                except Exception as e:
                    logger.error(
                        f"Unexpected error writing user log: {e}", exc_info=True
                    )
                    return False
        return False

    @staticmethod
    async def get_logs(
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        operation_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Query user logs with filtering and pagination.
        Returns a dict containing 'total', 'page', 'page_size', 'total_pages', and 'items'.
        """
        async with AsyncSessionLocal() as session:
            query = select(UserLog)
            count_query = select(func.count()).select_from(UserLog)

            # Apply filters
            conditions = []
            if user_id:
                conditions.append(UserLog.user_id == user_id)
            if username:
                conditions.append(UserLog.username.ilike(f"%{username}%"))
            if operation_type:
                conditions.append(UserLog.operation_type == operation_type)
            if start_date:
                conditions.append(UserLog.created_at >= start_date)
            if end_date:
                conditions.append(UserLog.created_at <= end_date)

            if conditions:
                query = query.where(*conditions)
                count_query = count_query.where(*conditions)

            # Get total count
            try:
                total_result = await session.execute(count_query)
                total = total_result.scalar() or 0
            except Exception as e:
                logger.error(f"Error counting logs: {e}")
                total = 0

            # Pagination
            offset = (page - 1) * page_size
            query = (
                query.order_by(desc(UserLog.created_at)).offset(offset).limit(page_size)
            )

            try:
                result = await session.execute(query)
                logs = result.scalars().all()
            except Exception as e:
                logger.error(f"Error fetching logs: {e}")
                logs = []

            items = []
            for log in logs:
                try:
                    items.append(
                        {
                            "id": log.id,
                            "user_id": log.user_id,
                            "username": log.username,
                            "operation_type": log.operation_type,
                            "credit_change": log.credit_change,
                            "current_balance": log.current_balance,
                            "created_at": log.created_at.isoformat(),
                            "extra_info": json.loads(log.extra_info)
                            if log.extra_info
                            else {},
                        }
                    )
                except Exception as e:
                    logger.error(f"Error serializing log entry {log.id}: {e}")
                    continue

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
                if page_size > 0
                else 0,
                "items": items,
            }
