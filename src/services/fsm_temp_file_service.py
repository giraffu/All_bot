import contextlib
import os
from collections.abc import Iterable, Mapping, MutableMapping
import uuid

from src.constants import TMP_DIR

FSM_TEMP_DIR = os.path.join(TMP_DIR, "fsm")
FSM_TEMP_PATH_KEYS = {
    "image_path",
    "end_image_path",
    "video_path",
    "reference_image_path",
    "motion_video_path",
    "start_image_path",
    "end_frame_path",
    "reference_audio",
    "reference_video",
    "extension_start_frame",
}
FSM_TEMP_PATH_LIST_KEYS = {
    "images",
    "image_paths",
    "input_paths",
    "input_files",
}
FSM_TOP_LEVEL_TEMP_PATH_KEYS = {
    "last_face_image",
}


def _ensure_fsm_temp_dir(base_dir: str = FSM_TEMP_DIR) -> str:
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


async def download_telegram_file_to_fsm_temp(
    *,
    telegram_file,
    suffix: str,
    name_hint: str | None = None,
    base_dir: str = FSM_TEMP_DIR,
) -> str:
    temp_dir = _ensure_fsm_temp_dir(base_dir)
    file_name = f"{uuid.uuid4()}_{name_hint or 'fsm'}{suffix}"
    local_path = os.path.join(temp_dir, file_name)
    try:
        await telegram_file.download_to_drive(local_path)
    except BaseException:
        # asyncio.wait_for cancels the download coroutine on timeout. Remove
        # any bytes already written so a stalled Telegram transfer cannot
        # leave orphaned FSM files behind.
        with contextlib.suppress(OSError):
            os.remove(local_path)
        raise
    return local_path


def cleanup_fsm_temp_files(paths: Iterable[str]) -> None:
    for path in paths:
        if not path:
            continue
        normalized_path = os.path.abspath(path)
        tmp_root = os.path.abspath(TMP_DIR)
        if os.path.commonpath([normalized_path, tmp_root]) != tmp_root:
            continue
        with contextlib.suppress(OSError):
            os.remove(normalized_path)


def _collect_fsm_temp_paths(value) -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            key_text = str(key)
            if key_text in FSM_TEMP_PATH_KEYS and isinstance(nested_value, str):
                paths.append(nested_value)
                continue
            if (
                key_text in FSM_TEMP_PATH_LIST_KEYS
                and isinstance(nested_value, Iterable)
                and not isinstance(nested_value, str | bytes)
            ):
                paths.extend(item for item in nested_value if isinstance(item, str))
                continue
            if isinstance(nested_value, Mapping | list | tuple | set):
                paths.extend(_collect_fsm_temp_paths(nested_value))
        return paths

    if isinstance(value, list | tuple | set):
        for item in value:
            if isinstance(item, str):
                paths.append(item)
            elif isinstance(item, Mapping | list | tuple | set):
                paths.extend(_collect_fsm_temp_paths(item))
    return paths


def cleanup_fsm_user_data(user_data: MutableMapping | None) -> list[str]:
    """Remove active FSM state and delete temp files referenced by FSM data."""
    if user_data is None:
        return []

    fsm_data_keys = [
        key for key in list(user_data.keys()) if str(key).endswith("_data")
    ]
    temp_paths: list[str] = []
    for key in fsm_data_keys:
        temp_paths.extend(_collect_fsm_temp_paths(user_data.get(key)))
    for key in FSM_TOP_LEVEL_TEMP_PATH_KEYS:
        value = user_data.get(key)
        if isinstance(value, str):
            temp_paths.append(value)

    cleanup_fsm_temp_files(tuple(dict.fromkeys(temp_paths)))
    user_data.pop("in_conversation", None)
    for key in fsm_data_keys:
        user_data.pop(key, None)
    for key in FSM_TOP_LEVEL_TEMP_PATH_KEYS:
        user_data.pop(key, None)
    return temp_paths
