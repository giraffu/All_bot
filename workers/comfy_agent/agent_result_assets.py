from typing import Any

RESULT_ASSET_KEYS = ("images", "gifs", "videos")
WAN22_AIO_VIDEO_TASK_TYPES = {"wan22_video_v2", "image_to_video"}
SCAIL2_VIDEO_TASK_TYPES = {"scail2_action_transfer", "scail2_video_replacement"}
VIDEO_PRIMARY_TASK_TYPES = WAN22_AIO_VIDEO_TASK_TYPES | SCAIL2_VIDEO_TASK_TYPES


def coerce_first_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return {}


def extract_ws_data_content(data: dict[str, Any]) -> dict[str, Any]:
    return coerce_first_mapping(data.get("data", {}))


def result_asset_keys_for_task(task_type: str | None) -> tuple[str, ...]:
    if task_type in VIDEO_PRIMARY_TASK_TYPES:
        return ("videos", "gifs")
    return RESULT_ASSET_KEYS


def pick_first_output_asset(
    outputs: Any,
    *,
    task_type: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(outputs, dict):
        return None
    asset_keys = result_asset_keys_for_task(task_type)
    for asset_key in asset_keys:
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            assets = node_output.get(asset_key, [])
            if assets:
                asset = assets[0]
                if isinstance(asset, dict):
                    return {**asset, "_asset_key": asset_key}
                return asset
    return None


def result_asset_priority(asset: dict[str, Any] | None, *, task_type: str | None) -> int:
    if not isinstance(asset, dict):
        return -1
    asset_key = str(asset.get("_asset_key") or "").strip().lower()
    if task_type in VIDEO_PRIMARY_TASK_TYPES:
        return {"videos": 3, "gifs": 2}.get(asset_key, 0)
    return 0


def build_safe_result_object_name(task_id: str, asset: dict[str, Any]) -> str:
    return (
        f"{task_id}_{asset.get('subfolder', '')}_{asset.get('filename')}"
        .replace("/", "_")
        .lstrip("_")
    )


def iter_output_assets(outputs: Any) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    if not isinstance(outputs, dict):
        return collected
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for asset_key in RESULT_ASSET_KEYS:
            assets = node_output.get(asset_key, [])
            if not isinstance(assets, list):
                continue
            for asset in assets:
                if isinstance(asset, dict):
                    collected.append(asset)
    return collected


def resolve_history_result_asset(
    history: dict[str, Any] | None,
    *,
    prompt_id: str | None,
    task_id: str | None,
    task_type: str | None = None,
) -> dict[str, str] | None:
    if not history or not prompt_id or not task_id or prompt_id not in history:
        return None

    outputs = history[prompt_id].get("outputs", {})
    asset = pick_first_output_asset(outputs, task_type=task_type)
    if not asset:
        return None

    original_filename = asset.get("filename", "")
    if not original_filename:
        return None

    return {
        "safe_name": build_safe_result_object_name(task_id, asset),
        "filename": original_filename,
        "subfolder": asset.get("subfolder", ""),
        "type": asset.get("type", ""),
        "asset_key": asset.get("_asset_key", ""),
    }


def resolve_history_extra_output_assets(
    history: dict[str, Any] | None,
    *,
    prompt_id: str | None,
    task_id: str | None,
    task_type: str | None = None,
) -> dict[str, dict[str, Any]]:
    if task_type not in WAN22_AIO_VIDEO_TASK_TYPES or not history or not prompt_id or not task_id:
        return {}
    prompt_history = history.get(prompt_id)
    if not isinstance(prompt_history, dict):
        return {}
    outputs = prompt_history.get("outputs", {})
    if not isinstance(outputs, dict):
        return {}

    resolved: dict[str, dict[str, Any]] = {}
    for asset in iter_output_assets(outputs):
        filename = str(asset.get("filename") or "")
        if "last_frame" not in filename.lower():
            continue
        resolved["last_frame"] = {
            "path": build_safe_result_object_name(task_id, asset),
            "media_type": "image",
            "filename": filename,
            "subfolder": asset.get("subfolder", ""),
            "type": asset.get("type", "output"),
        }
        break
    return resolved


def resolve_comfy_view_type(asset: dict[str, Any] | None) -> str:
    if not asset:
        return "output"

    asset_type = str(asset.get("type", "") or "").strip().lower()
    if asset_type in {"temp", "output", "input"}:
        return asset_type

    subfolder = str(asset.get("subfolder", "") or "").strip().lower()
    if subfolder == "temp" or subfolder.startswith("temp/") or "/temp/" in f"/{subfolder}/":
        return "temp"

    filename = str(asset.get("filename", "") or "").strip().lower()
    if "/temp/" in filename or filename.startswith("temp/"):
        return "temp"

    return "output"
