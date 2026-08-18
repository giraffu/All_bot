from src.media_processor import (
    extract_media_metadata_from_bytes_best_effort,
    extract_media_metadata_from_storage_best_effort,
)
from src.core.task_core_default_dependencies import (
    build_default_task_core_persistence_dependencies,
)
from src.core.task_core_web_history_warmup import schedule_web_history_r2_warmup_default
from src.logger import UserLogger


def build_runtime_default_task_core_persistence_dependencies():
    return build_default_task_core_persistence_dependencies(
        schedule_web_history_r2_warmup_func=schedule_web_history_r2_warmup_default,
        user_logger_factory=UserLogger,
        extract_media_metadata_from_bytes_best_effort_func=(
            extract_media_metadata_from_bytes_best_effort
        ),
        extract_media_metadata_from_storage_best_effort_func=(
            extract_media_metadata_from_storage_best_effort
        ),
    )
