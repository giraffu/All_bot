"""
Legacy compatibility import path for the Telegram Bot task facade.

New Telegram-side callers should import `src.services.bot_task_service`.
This module remains as a thin re-export shell to avoid breaking older imports.
"""

from src.services.bot_task_service import TaskService, task_service

__all__ = ["TaskService", "task_service"]
