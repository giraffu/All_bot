from collections.abc import Callable

from src.core.media_urls import build_storage_presigned_url
from src.services.storage import storage


def build_storage_input_file_url(file_path: str | None) -> str | None:
    if not file_path:
        return None

    return build_storage_presigned_url(
        file_path,
        lambda object_name, bucket_name: storage.get_presigned_url(
            object_name,
            bucket=bucket_name,
        ),
    )


def split_history_input_files(input_file: str | None) -> list[str]:
    if not input_file:
        return []
    return [
        item.strip()
        for item in str(input_file).split("|")
        if item and item.strip()
    ]


def build_history_input_file_payload(
    input_file: str | None,
    *,
    build_input_file_url: Callable[[str], str | None] = build_storage_input_file_url,
) -> dict[str, object]:
    input_files = split_history_input_files(input_file)
    input_file_urls = [
        build_input_file_url(file_path) or file_path
        for file_path in input_files
    ]
    return {
        "input_file": input_files[0] if input_files else None,
        "input_file_url": input_file_urls[0] if input_file_urls else None,
        "input_files": input_files,
        "input_file_urls": input_file_urls,
    }
