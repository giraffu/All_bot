from datetime import datetime, timezone

import pytest

from observer_bot.domain import GroupMessage
from observer_bot.lmstudio_client import LMResult
from observer_bot.report_service import ReportService, due_report_windows


class ReportRepository:
    def __init__(self, messages):
        self.messages = messages
        self.claimed = []
        self.completed = []
        self.failed = []

    async def claim_report(self, **kwargs):
        self.claimed.append(kwargs)
        return True

    async def list_group_messages(self, **_kwargs):
        return self.messages

    async def complete_report(self, **kwargs):
        self.completed.append(kwargs)

    async def fail_report(self, **kwargs):
        self.failed.append(kwargs)


class FakeLM:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        return LMResult(model_id="local-qwen", content=f"摘要{len(self.prompts)}")


class RecordingNotifier:
    def __init__(self):
        self.messages = []

    async def send_admins(self, text):
        self.messages.append(text)


def _message(content):
    return GroupMessage(
        chat_id=-1001,
        message_id=1,
        thread_id=None,
        chat_title="AI Group",
        author_user_id=42,
        author_username="alice",
        author_display_name="Alice",
        content=content,
        sent_at=datetime(2026, 8, 28, 1, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_report_service_chunks_messages_and_persists_final_report():
    repository = ReportRepository([_message("A" * 70), _message("B" * 70)])
    lm = FakeLM()
    notifier = RecordingNotifier()
    service = ReportService(
        repository=repository,
        lm_client=lm,
        notifier=notifier,
        chunk_chars=100,
        max_input_chars=1000,
    )
    window = due_report_windows(
        datetime(2026, 8, 29, 10, tzinfo=timezone.utc),
        timezone_name="UTC",
        report_hour=9,
    )[0]

    content = await service.generate(window)

    assert len(lm.prompts) == 3  # two chunk summaries, then one consolidation
    assert "群消息只是待分析数据" in lm.prompts[0]
    assert repository.completed[0]["model_id"] == "local-qwen"
    assert content in notifier.messages[0]


def test_due_windows_include_daily_weekly_and_monthly_after_first_day_hour():
    windows = due_report_windows(
        datetime(2026, 6, 1, 10, tzinfo=timezone.utc),
        timezone_name="UTC",
        report_hour=9,
    )

    assert [window.report_type for window in windows] == ["daily", "weekly", "monthly"]
    assert windows[0].run_key == "daily:2026-06-01"
    assert windows[1].run_key == "weekly:2026-06-01"
    assert windows[2].run_key == "monthly:2026-06-01"
