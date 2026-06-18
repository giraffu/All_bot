from src.i18n.translator import get_text


def _translate(lang: str, key: str, **kwargs) -> str:
    return get_text(key, lang or "zh", **kwargs)


def normalize_pending_queue_position(info: dict) -> int | str | None:
    raw_pos = info.get("queue_pos")
    if raw_pos is not None:
        try:
            return int(raw_pos) + 1
        except (ValueError, TypeError):
            return raw_pos
    return info.get("queue_remaining")


def build_pending_status_text(
    *,
    info: dict,
    vip_suffix: str,
    lang: str = "zh",
) -> str:
    queue_pos = normalize_pending_queue_position(info)
    if queue_pos is None:
        return f"{_translate(lang, 'task.status_pending')}{vip_suffix}"
    return (
        f"{_translate(lang, 'task.status_pending_position', queue_pos=queue_pos)}"
        f"{vip_suffix}"
    )


def build_running_status_text(
    *,
    is_video: bool,
    progress: int | float,
    lang: str = "zh",
) -> str:
    if is_video:
        return _translate(lang, "task.status_generating_video")
    return _translate(lang, "task.status_wait_generating")


def build_done_progress_text(*, lang: str = "zh") -> str:
    return _translate(lang, "task.status_generating_progress", progress=100)
