import contextlib
import os

from src.constants import TMP_DIR


def cleanup_task_files(paths: list[str]) -> None:
    for path in paths:
        if path and path.startswith(TMP_DIR) and os.path.exists(path):
            with contextlib.suppress(OSError):
                os.remove(path)
