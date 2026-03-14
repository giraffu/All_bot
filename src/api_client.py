# api_client.py
import asyncio
import httpx
import logging
from src.utils import async_retry
from config import IMG2IMG_ENDPOINT, STATUS_ENDPOINT, IMAGE_ENDPOINT, POLL_INTERVAL, VIDEO_STATUS_ENDPOINT, VIDEO_ENDPOINT, API_BASE, FACE_SWAP_ENDPOINT, PERFECT_VIDEO_EDIT_ENDPOINT, PERFECT_VIDEO_INSERT_ENDPOINT, QUEUE_POSITION_ENDPOINT

import os

logger = logging.getLogger(__name__)

@async_retry(max_retries=3)
async def submit_perfect_video_insert(prompt: str, image_path: str, width: int = 512, height: int = 512, length: int = 81) -> str:
    """
    提交 perfect_video_insert 任务并获取 task_id
    """
    async with httpx.AsyncClient(trust_env=False) as client:
        f = None
        try:
            f = open(image_path, "rb")
            files = {"image": (os.path.basename(image_path), f, "image/jpeg")}
            
            data = {
                "prompt": prompt,
                "width": width,
                "height": height,
                "length": length
            }

            r = await client.post(PERFECT_VIDEO_INSERT_ENDPOINT, files=files, data=data, timeout=60)
            r.raise_for_status()
            return r.json()["task_id"]
        finally:
            if f:
                f.close()

@async_retry(max_retries=3)
async def submit_perfect_video_edit(prompt: str, image_path: str, width: int = 512, height: int = 512, length: int = 81) -> str:
    """
    提交 perfect_video_edit 任务并获取 task_id
    """
    async with httpx.AsyncClient(trust_env=False) as client:
        f = None
        try:
            f = open(image_path, "rb")
            files = {"image": (os.path.basename(image_path), f, "image/jpeg")}
            
            data = {
                "prompt": prompt,
                "width": width,
                "height": height,
                "length": length
            }

            r = await client.post(PERFECT_VIDEO_EDIT_ENDPOINT, files=files, data=data, timeout=60)
            r.raise_for_status()
            return r.json()["task_id"]
        finally:
            if f:
                f.close()

@async_retry(max_retries=3)
async def submit_img2img(prompt: str, image_paths: list[str], negative_prompt: str = " "):
    async with httpx.AsyncClient(trust_env=False) as client:
        file_handles = []
        try:
            files_payload = []
            for path in image_paths:
                f = open(path, "rb")
                file_handles.append(f)
                # httpx accepts list of tuples for multiple files with same key
                files_payload.append(("images", (os.path.basename(path), f)))
            
            data = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "num_inference_steps": 6,
                "guidance_scale": 1.0,
                "seed": -1,
            }

            r = await client.post(IMG2IMG_ENDPOINT, files=files_payload, data=data, timeout=30)
            r.raise_for_status()
            return r.json()["task_id"]
        finally:
            for f in file_handles:
                f.close()

@async_retry(max_retries=3)
async def submit_face_swap(face_image_path: str, body_image_path: str):
    """
    提交换脸任务
    """
    async with httpx.AsyncClient(trust_env=False) as client:
        f1, f2 = None, None
        try:
            f1 = open(face_image_path, "rb")
            f2 = open(body_image_path, "rb")
            
            files = {
                "face_image": (os.path.basename(face_image_path), f1),
                "body_image": (os.path.basename(body_image_path), f2),
            }
            
            r = await client.post(FACE_SWAP_ENDPOINT, files=files, timeout=60)
            r.raise_for_status()
            return r.json()["task_id"]
        finally:
            if f1: f1.close()
            if f2: f2.close()

async def listen_for_progress(task_id: str, is_video: bool = False):
    """
    异步生成器，定期 yield 任务状态 info
    - status == done  -> 任务完成 (最后一次 yield)
    - status == error -> 抛异常
    - running / pending -> yield info (含 progress)
    """
    if is_video:
        status_url = f"{VIDEO_STATUS_ENDPOINT}/{task_id}"
    else:
        status_url = f"{STATUS_ENDPOINT}/{task_id}"
    
    async with httpx.AsyncClient(trust_env=False) as client:
        while True:
            try:
                r = await client.get(status_url, timeout=10)
                r.raise_for_status()
                info = r.json()
                logger.debug(f"Task {task_id} status info: {info}")
                
                status = info.get("status")

                if status == "pending":
                    queue_remaining = info.get("queue_remaining", "N/A")
                    print(f"⏳ [Task {task_id}] Pending... Queue size: {queue_remaining}")
                    # Normalize queue_pos if queue_remaining exists
                    if "queue_pos" not in info and "queue_remaining" in info:
                        info["queue_pos"] = info["queue_remaining"]
                
                yield info
                
                if status == "done":
                    return
                
                if status == "error":
                    raise RuntimeError(info.get("error", "generation failed"))
                
                # running / pending
                await asyncio.sleep(POLL_INTERVAL)
                
            except httpx.RequestError as e:
                # 网络波动，打印日志并重试
                print(f"Warning: Poll status failed: {e}")
                await asyncio.sleep(POLL_INTERVAL)


@async_retry(max_retries=3)
async def download_image(task_id: str) -> bytes:
    """
    根据 task_id 下载图片
    """
    url = f"{IMAGE_ENDPOINT}/{task_id}"
    async with httpx.AsyncClient(trust_env=False) as client:
        r = await client.get(url, timeout=60)
        r.raise_for_status()
        return r.content

async def get_system_status() -> dict:
    """
    获取系统当前负载状态 (活跃任务数)
    """
    url = f"{API_BASE}/system/status"
    async with httpx.AsyncClient(trust_env=False) as client:
        try:
            r = await client.get(url, timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"Warning: Failed to get system status: {e}")
            return None

@async_retry(max_retries=3)
async def get_queue_position(task_id: str) -> dict:
    """
    获取任务队列排队位置
    """
    url = f"{QUEUE_POSITION_ENDPOINT}/{task_id}"
    async with httpx.AsyncClient(trust_env=False) as client:
        try:
            r = await client.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()
            logger.debug(f"Queue position for {task_id}: {data}")
            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise e
        except Exception as e:
            print(f"Warning: Failed to get queue position: {e}")
            return None

@async_retry(max_retries=3)
async def download_video(task_id: str) -> bytes:
    """
    根据 task_id 下载视频
    """
    url = f"{VIDEO_ENDPOINT}/{task_id}"
    async with httpx.AsyncClient(trust_env=False) as client:
        r = await client.get(url, timeout=60)
        r.raise_for_status()
        return r.content
