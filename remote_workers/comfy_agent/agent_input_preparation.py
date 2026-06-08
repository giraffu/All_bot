import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any


async def process_single_input_asset(
    *,
    params: dict[str, Any],
    downloaded_input_paths: list[str],
    img_filename: str,
    param_key: str,
    comfy_input_dir: str,
    download_input_func: Callable[[str, str], Any],
    should_normalize_image_input_func: Callable[[str, str], bool],
    normalize_input_image_func: Callable[[str], str],
    upload_prepared_input_func: Callable[..., Awaitable[None]],
    logger,
) -> None:
    local_safe_filename = img_filename.replace("/", "_").replace("template:", "")
    local_img_path = os.path.join(comfy_input_dir, local_safe_filename)
    try:
        await asyncio.to_thread(download_input_func, img_filename, local_img_path)
        logger.info("Downloaded %s to %s", param_key, local_img_path)
        if local_img_path not in downloaded_input_paths:
            downloaded_input_paths.append(local_img_path)
        upload_path = local_img_path
        upload_name = local_safe_filename
        if should_normalize_image_input_func(param_key, img_filename):
            upload_path = await asyncio.to_thread(
                normalize_input_image_func,
                local_img_path,
            )
            upload_name = os.path.basename(upload_path)
            if upload_path not in downloaded_input_paths:
                downloaded_input_paths.append(upload_path)
            logger.info(
                "Normalized %s input for ComfyUI: %s -> %s",
                param_key,
                local_img_path,
                upload_path,
            )
        await upload_prepared_input_func(
            upload_path=upload_path,
            upload_name=upload_name,
            source_name=img_filename,
        )
        params[param_key] = upload_name
    except Exception as exc:
        logger.error("Failed to process %s %s: %s", param_key, img_filename, exc)
        raise RuntimeError(f"Failed to prepare {param_key} input '{img_filename}'") from exc


async def prepare_task_inputs(
    *,
    params: dict[str, Any],
    downloaded_input_paths: list[str],
    process_single_input_asset_func: Callable[..., Awaitable[None]],
) -> None:
    if (
        "images" in params
        and isinstance(params["images"], list)
        and len(params["images"]) > 0
    ):
        images_list = params["images"]
        tasks = []
        keys = ["image", "image2", "image3"]
        for i, img_filename in enumerate(images_list[:3]):
            tasks.append(
                process_single_input_asset_func(
                    params=params,
                    downloaded_input_paths=downloaded_input_paths,
                    img_filename=img_filename,
                    param_key=keys[i],
                )
            )
        if tasks:
            await asyncio.gather(*tasks)
    else:
        legacy_tasks = []
        if "image" in params and params["image"]:
            legacy_tasks.append(
                process_single_input_asset_func(
                    params=params,
                    downloaded_input_paths=downloaded_input_paths,
                    img_filename=params["image"],
                    param_key="image",
                )
            )
        if "image2" in params and params["image2"]:
            legacy_tasks.append(
                process_single_input_asset_func(
                    params=params,
                    downloaded_input_paths=downloaded_input_paths,
                    img_filename=params["image2"],
                    param_key="image2",
                )
            )
        if legacy_tasks:
            await asyncio.gather(*legacy_tasks)

    other_tasks = []
    for key in ["face_image", "body_image", "video", "end_image"]:
        if key in params and params[key]:
            other_tasks.append(
                process_single_input_asset_func(
                    params=params,
                    downloaded_input_paths=downloaded_input_paths,
                    img_filename=params[key],
                    param_key=key,
                )
            )
    if other_tasks:
        await asyncio.gather(*other_tasks)
