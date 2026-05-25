import contextlib
import os
import uuid

from src.constants import TMP_DIR

FSM_TEMP_DIR = os.path.join(TMP_DIR, "fsm")


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
    await telegram_file.download_to_drive(local_path)
    return local_path


def cleanup_fsm_temp_files(paths: list[str] | tuple[str, ...]) -> None:
    for path in paths:
        if not path:
            continue
        normalized_path = os.path.abspath(path)
        if not normalized_path.startswith(os.path.abspath(TMP_DIR)):
            continue
        with contextlib.suppress(OSError):
            os.remove(normalized_path)
