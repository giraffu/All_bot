from dataclasses import replace
from typing import Callable, Optional

from src.services.task_service_types import BotTaskMessageSpec


def build_message_spec(
    *,
    initial_status_text: str,
    submitted_status_text: Optional[str] = None,
    progress_wait_text: Optional[str] = None,
    completion_caption: Optional[str] = None,
    missing_output_message: str = "生成完成但未获取到文件路径，已退还灵石",
    cancellation_message_template: str = "任务已撤销，预扣的 {cost} 灵石已全额退回。",
) -> BotTaskMessageSpec:
    return BotTaskMessageSpec(
        initial_status_text=initial_status_text,
        submitted_status_text=submitted_status_text,
        progress_wait_text=progress_wait_text,
        completion_caption=completion_caption,
        missing_output_message=missing_output_message,
        cancellation_message_template=cancellation_message_template,
    )


def with_submitted_status(
    spec: BotTaskMessageSpec, submitted_status_text: str
) -> BotTaskMessageSpec:
    return replace(spec, submitted_status_text=submitted_status_text)


def with_completion_caption(
    spec: BotTaskMessageSpec, completion_caption: str
) -> BotTaskMessageSpec:
    return replace(spec, completion_caption=completion_caption)


def resolve_display_mode_name(task_type: str, *, context, mode_name_map: dict[str, str]) -> str:
    mode_name = mode_name_map.get(task_type, task_type)
    return context.t(mode_name) if hasattr(context, "t") else mode_name


def build_status_message(
    headline: str,
    *,
    notice: str = "",
    wait_text: Optional[str] = None,
) -> str:
    message = f"{headline}...{notice}"
    if wait_text:
        return f"{message}\n{wait_text}"
    return message


def build_cost_status_builder(
    headline_template: str,
    *,
    notice: str = "",
    wait_text: Optional[str] = None,
) -> Callable[[int], str]:
    def _builder(actual_cost: int) -> str:
        return build_status_message(
            headline_template.format(actual_cost=actual_cost),
            notice=notice,
            wait_text=wait_text,
        )

    return _builder
