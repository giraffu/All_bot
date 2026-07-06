from src.services.gallery_apply_context_presenter import (
    build_apply_context_response,
    build_history_apply_context_response,
    call_with_optional_db,
    probe_apply_context_media_metadata,
    release_read_transaction,
    resolve_apply_context_media_metadata,
    resolve_history_billing_resolution,
    run_with_optional_db,
    storage,
)
from src.services.gallery_apply_context_presenter import (
    build_storage_input_file_url as _build_storage_input_file_url,
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
