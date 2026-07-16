from src.services import task_service_message_support as support
from src.services.task_service_types import BotTaskMessageSpec


def test_build_message_spec_returns_expected_dataclass():
    spec = support.build_message_spec(
        initial_status_text="init",
        submitted_status_text="submitted",
        progress_wait_text="waiting",
        completion_caption="done",
        missing_output_message="missing",
        cancellation_message_template="cancel {cost}",
    )

    assert spec == BotTaskMessageSpec(
        initial_status_text="init",
        submitted_status_text="submitted",
        progress_wait_text="waiting",
        completion_caption="done",
        missing_output_message="missing",
        cancellation_message_template="cancel {cost}",
    )


def test_with_submitted_status_returns_updated_copy():
    spec = BotTaskMessageSpec(initial_status_text="init")

    updated = support.with_submitted_status(spec, "submitted")

    assert updated.submitted_status_text == "submitted"
    assert spec.submitted_status_text is None


def test_resolve_display_mode_name_uses_context_translator_when_available():
    class _Context:
        def t(self, value: str, **_kwargs) -> str:
            return f"translated:{value}"

    display_name = support.resolve_display_mode_name(
        "mode-a",
        context=_Context(),
        mode_name_map={"mode-a": "task.mode_a"},
    )

    assert display_name == "translated:task.mode_a"


def test_resolve_display_mode_name_hides_unknown_task_type_without_translator():
    display_name = support.resolve_display_mode_name(
        "mode-b",
        context=object(),
        mode_name_map={},
    )

    assert display_name == "生成任务"


def test_build_status_message_appends_notice_and_wait_text():
    message = support.build_status_message(
        "🚀 正在处理自定义视频生成任务 (画质:720p, 时长:5s)",
        notice="\n✨ [新手特权] 前2次生成享受极速排队通道！",
        wait_text="⏳ 正在生成自定义视频，请耐心等待...",
    )

    assert (
        message
        == "🚀 正在处理自定义视频生成任务 (画质:720p, 时长:5s)...\n✨ [新手特权] 前2次生成享受极速排队通道！\n⏳ 正在生成自定义视频，请耐心等待..."
    )
