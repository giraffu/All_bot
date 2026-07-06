from src.services.gallery_apply_context_presenter import (
    build_storage_input_file_url as _build_storage_input_file_url,
)
from src.services.gallery_apply_context_presenter import (
    call_with_optional_db,
    release_read_transaction,
    run_with_optional_db,
    storage,
)
from src.web_api.services.apply_context_service import (
    build_apply_context_response,
    build_history_apply_context_response,
    probe_apply_context_media_metadata,
    resolve_apply_context_media_metadata,
    resolve_history_billing_resolution,
)

__all__ = [
    "build_apply_context_response",
    "build_history_apply_context_response",
    "probe_apply_context_media_metadata",
    "resolve_apply_context_media_metadata",
    "resolve_history_billing_resolution",
    "build_storage_input_file_url",
    "run_with_optional_db",
    "call_with_optional_db",
    "release_read_transaction",
    "storage",
]


def build_storage_input_file_url(file_path: str | None) -> str | None:
    return _build_storage_input_file_url(file_path, storage_adapter=storage)
