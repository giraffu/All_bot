from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import asyncpg

from observer_bot.domain import GroupMessage


def _asyncpg_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


class ObserverRepository:
    def __init__(self, database_url: str):
        self._database_url = _asyncpg_url(database_url)
        self._pool: asyncpg.Pool | None = None

    async def open(self) -> None:
        self._pool = await asyncpg.create_pool(
            self._database_url,
            min_size=1,
            max_size=4,
            command_timeout=30,
            server_settings={"application_name": "observer-bot"},
        )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _ready_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("observer repository is not open")
        return self._pool

    async def save_group_message(self, message: GroupMessage) -> None:
        await self._ready_pool().execute(
            """
            INSERT INTO observer_group_messages (
                chat_id, message_id, thread_id, chat_title, author_user_id,
                author_username, author_display_name, content, sent_at, edited_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (chat_id, message_id) DO UPDATE SET
                thread_id = EXCLUDED.thread_id,
                chat_title = EXCLUDED.chat_title,
                author_user_id = EXCLUDED.author_user_id,
                author_username = EXCLUDED.author_username,
                author_display_name = EXCLUDED.author_display_name,
                content = EXCLUDED.content,
                sent_at = EXCLUDED.sent_at,
                edited_at = EXCLUDED.edited_at,
                updated_at = NOW()
            """,
            message.chat_id,
            message.message_id,
            message.thread_id,
            message.chat_title,
            message.author_user_id,
            message.author_username,
            message.author_display_name,
            message.content,
            message.sent_at,
            message.edited_at,
        )

    async def list_group_messages(
        self, *, start: datetime, end: datetime, limit: int = 50_000
    ) -> list[GroupMessage]:
        rows = await self._ready_pool().fetch(
            """
            SELECT chat_id, message_id, thread_id, chat_title, author_user_id,
                   author_username, author_display_name, content, sent_at, edited_at
            FROM observer_group_messages
            WHERE sent_at >= $1 AND sent_at < $2
            ORDER BY sent_at ASC
            LIMIT $3
            """,
            start,
            end,
            limit,
        )
        return [GroupMessage(**dict(row)) for row in rows]

    async def get_state(self, key: str) -> dict[str, Any]:
        row = await self._ready_pool().fetchrow(
            "SELECT payload FROM observer_alert_states WHERE state_key = $1", key
        )
        if row is None:
            return {}
        payload = row["payload"]
        return dict(json.loads(payload) if isinstance(payload, str) else payload)

    async def set_state(self, key: str, value: dict[str, Any]) -> None:
        await self._ready_pool().execute(
            """
            INSERT INTO observer_alert_states (state_key, payload)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (state_key) DO UPDATE SET
                payload = EXCLUDED.payload,
                updated_at = NOW()
            """,
            key,
            json.dumps(value, ensure_ascii=False),
        )

    async def claim_report(
        self,
        *,
        run_key: str,
        report_type: str,
        start: datetime,
        end: datetime,
    ) -> bool:
        row = await self._ready_pool().fetchrow(
            """
            INSERT INTO observer_report_runs (
                run_key, report_type, period_start, period_end, status
            ) VALUES ($1, $2, $3, $4, 'running')
            ON CONFLICT (run_key) DO UPDATE SET
                status = 'running',
                attempts = observer_report_runs.attempts + 1,
                error = NULL,
                locked_at = NOW(),
                updated_at = NOW()
            WHERE (
                observer_report_runs.status = 'failed'
                OR (
                    observer_report_runs.status = 'running'
                    AND observer_report_runs.locked_at < NOW() - INTERVAL '1 hour'
                )
            ) AND observer_report_runs.attempts < 3
            RETURNING run_key
            """,
            run_key,
            report_type,
            start,
            end,
        )
        return row is not None

    async def complete_report(self, *, run_key: str, model_id: str, content: str) -> None:
        await self._ready_pool().execute(
            """
            UPDATE observer_report_runs
            SET status = 'completed', model_id = $2, content = $3,
                completed_at = NOW(), updated_at = NOW()
            WHERE run_key = $1
            """,
            run_key,
            model_id,
            content,
        )

    async def fail_report(self, *, run_key: str, error: str) -> None:
        await self._ready_pool().execute(
            """
            UPDATE observer_report_runs
            SET status = 'failed', error = $2, updated_at = NOW()
            WHERE run_key = $1
            """,
            run_key,
            error[:2000],
        )

    async def delete_messages_before(self, cutoff: datetime) -> int:
        result = await self._ready_pool().execute(
            "DELETE FROM observer_group_messages WHERE sent_at < $1", cutoff
        )
        return int(result.rsplit(" ", 1)[-1])
