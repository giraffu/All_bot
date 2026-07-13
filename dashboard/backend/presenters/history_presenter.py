from config import MINIO_TEMPLATE_BUCKET
from dashboard.backend.presenters.storage_presenter_utils import build_storage_url


def build_history_input_file_url(*, input_file: str | None, storage_service) -> str | None:
    if not input_file:
        return None

    urls: list[str] = []
    for file_name in input_file.split("|"):
        if file_name.startswith("template:"):
            template_path = file_name[9:]
            urls.append(
                build_storage_url(
                    storage_service=storage_service,
                    object_name=template_path,
                    bucket=MINIO_TEMPLATE_BUCKET,
                )
            )
        else:
            urls.append(
                build_storage_url(
                    storage_service=storage_service,
                    object_name=file_name,
                )
            )
    return "|".join(urls)


def build_history_output_file_url(*, output_file: str | None, storage_service) -> str | None:
    if not output_file:
        return None
    if "/" not in output_file:
        return build_storage_url(
            storage_service=storage_service,
            object_name=output_file,
            bucket="comfyui-temp",
        )
    return build_storage_url(storage_service=storage_service, object_name=output_file)


def build_history_item_payload(
    *,
    history,
    storage_service,
    username: str | None = None,
    full_name: str | None = None,
    worker_id: str | None = None,
) -> dict:
    item_dict = {column.name: getattr(history, column.name) for column in history.__table__.columns}
    if username is not None:
        item_dict["username"] = username
    if full_name is not None:
        item_dict["full_name"] = full_name
    item_dict["worker_id"] = worker_id

    input_file_url = build_history_input_file_url(
        input_file=history.input_file,
        storage_service=storage_service,
    )
    if input_file_url:
        item_dict["input_file_url"] = input_file_url

    output_file_url = build_history_output_file_url(
        output_file=history.output_file,
        storage_service=storage_service,
    )
    if output_file_url:
        item_dict["output_file_url"] = output_file_url

    return item_dict
