"""
Preferred semantic import path for the Telegram Bot task facade.

This module keeps `src.services.task_service` stable for compat while giving new
callers a less misleading entrypoint name.
"""

from src.services.task_service import TaskService, task_service

__all__ = ["TaskService", "task_service"]
