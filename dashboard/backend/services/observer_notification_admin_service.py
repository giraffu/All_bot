from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg


def _asyncpg_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


class ObserverNotificationAdminService:
    """Low-traffic dashboard adapter for the isolated observer database."""

    def __init__(
        self,
        database_url: str,
        *,
        connect: Callable[[str], Awaitable[Any]] = asyncpg.connect,
    ):
        self._database_url = _asyncpg_url(database_url)
        self._connect = connect

    async def _connection(self):
        return await self._connect(self._database_url)

    async def get_settings(self) -> dict[str, Any]:
        connection = await self._connection()
        try:
            settings = await connection.fetchrow(
                """
                SELECT queue_alerts_enabled, group_collection_enabled,
                       daily_reports_enabled, weekly_reports_enabled,
                       monthly_reports_enabled
                FROM observer_runtime_settings
                WHERE singleton = TRUE
                """
            )
            if settings is None:
                raise RuntimeError("observer runtime schema is not initialized")
            admin_rows = await connection.fetch(
                """
                SELECT telegram_user_id FROM observer_admin_recipients
                WHERE enabled = TRUE ORDER BY telegram_user_id
                """
            )
            group_rows = await connection.fetch(
                """
                SELECT chat_id FROM observer_authorized_chats
                WHERE enabled = TRUE ORDER BY chat_id
                """
            )
            return {
                "admin_telegram_user_ids": [
                    int(row["telegram_user_id"]) for row in admin_rows
                ],
                "authorized_group_ids": [int(row["chat_id"]) for row in group_rows],
                "queue_alerts_enabled": bool(settings["queue_alerts_enabled"]),
                "group_collection_enabled": bool(
                    settings["group_collection_enabled"]
                ),
                "daily_reports_enabled": bool(settings["daily_reports_enabled"]),
                "weekly_reports_enabled": bool(settings["weekly_reports_enabled"]),
                "monthly_reports_enabled": bool(
                    settings["monthly_reports_enabled"]
                ),
            }
        finally:
            await connection.close()

    async def update_settings(
        self,
        *,
        admin_telegram_user_ids: list[int],
        authorized_group_ids: list[int],
        queue_alerts_enabled: bool,
        group_collection_enabled: bool,
        daily_reports_enabled: bool,
        weekly_reports_enabled: bool,
        monthly_reports_enabled: bool,
    ) -> dict[str, Any]:
        admins = sorted(set(admin_telegram_user_ids))
        groups = sorted(set(authorized_group_ids))
        connection = await self._connection()
        try:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE observer_runtime_settings
                    SET queue_alerts_enabled = $1,
                        group_collection_enabled = $2,
                        daily_reports_enabled = $3,
                        weekly_reports_enabled = $4,
                        monthly_reports_enabled = $5,
                        recipients_initialized = TRUE,
                        groups_initialized = TRUE,
                        updated_at = NOW()
                    WHERE singleton = TRUE
                    """,
                    queue_alerts_enabled,
                    group_collection_enabled,
                    daily_reports_enabled,
                    weekly_reports_enabled,
                    monthly_reports_enabled,
                )
                await connection.execute("DELETE FROM observer_admin_recipients")
                if admins:
                    await connection.executemany(
                        """
                        INSERT INTO observer_admin_recipients (telegram_user_id)
                        VALUES ($1)
                        """,
                        [(chat_id,) for chat_id in admins],
                    )
                await connection.execute("DELETE FROM observer_authorized_chats")
                if groups:
                    await connection.executemany(
                        """
                        INSERT INTO observer_authorized_chats (chat_id)
                        VALUES ($1)
                        """,
                        [(chat_id,) for chat_id in groups],
                    )
        finally:
            await connection.close()
        return await self.get_settings()

    async def list_reports(self, *, page: int, page_size: int) -> dict[str, Any]:
        return await self._list_rows(
            table="observer_report_runs",
            columns=(
                "run_key, report_type, period_start, period_end, status, attempts, "
                "model_id, content, error, completed_at, updated_at"
            ),
            page=page,
            page_size=page_size,
        )

    async def list_notifications(
        self, *, page: int, page_size: int
    ) -> dict[str, Any]:
        return await self._list_rows(
            table="observer_notification_logs",
            columns=(
                "id, event_type, destination_chat_id, status, content_preview, "
                "error_type, created_at"
            ),
            page=page,
            page_size=page_size,
            order_column="created_at",
        )

    async def _list_rows(
        self,
        *,
        table: str,
        columns: str,
        page: int,
        page_size: int,
        order_column: str = "updated_at",
    ) -> dict[str, Any]:
        allowed_tables = {"observer_report_runs", "observer_notification_logs"}
        if table not in allowed_tables:
            raise ValueError("unsupported observer table")
        connection = await self._connection()
        try:
            total_row = await connection.fetchrow(f"SELECT COUNT(*) AS total FROM {table}")
            rows = await connection.fetch(
                f"""
                SELECT {columns} FROM {table}
                ORDER BY {order_column} DESC
                LIMIT $1 OFFSET $2
                """,
                page_size,
                (page - 1) * page_size,
            )
            return {
                "items": [dict(row) for row in rows],
                "total": int(total_row["total"] if total_row else 0),
                "page": page,
                "page_size": page_size,
            }
        finally:
            await connection.close()
