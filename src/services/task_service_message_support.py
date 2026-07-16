from dataclasses import replace
from typing import Callable, Optional

from src.i18n.translator import get_text
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


def resolve_context_lang(context) -> str:
    lang = getattr(context, "lang", None)
    if lang:
        return lang
    user_data = getattr(context, "user_data", None)
    if isinstance(user_data, dict):
        return user_data.get("language_code", "zh")
    return "zh"


def translate_context_text(context, key: str, **kwargs) -> str:
    translator = getattr(context, "t", None)
    if callable(translator):
        translated = translator(key, **kwargs)
        if translated != key:
            return translated
    return get_text(key, resolve_context_lang(context), **kwargs)


def resolve_display_mode_name(task_type: str, *, context, mode_name_map: dict[str, str]) -> str:
    mode_name = mode_name_map.get(task_type, "task_type.other")
    return translate_context_text(context, mode_name)


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


def build_translated_cost_status_builder(
    context,
    headline_key: str,
    *,
    notice: str = "",
    wait_key: Optional[str] = None,
    **kwargs,
) -> Callable[[int], str]:
    def _builder(actual_cost: int) -> str:
        wait_text = translate_context_text(context, wait_key, **kwargs) if wait_key else None
        return build_status_message(
            translate_context_text(
                context,
                headline_key,
                actual_cost=actual_cost,
                **kwargs,
            ),
            notice=notice,
            wait_text=wait_text,
        )

    return _builder
