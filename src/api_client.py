# api_client.py
import asyncio
import httpx
import logging
import uuid
import os
from typing import Optional
from src.utils import async_retry
from config import (
    IMG2IMG_ENDPOINT, STATUS_ENDPOINT, IMAGE_ENDPOINT, POLL_INTERVAL, 
    VIDEO_ENDPOINT, API_BASE, FACE_SWAP_ENDPOINT, 
    PERFECT_VIDEO_EDIT_ENDPOINT, PERFECT_VIDEO_INSERT_ENDPOINT,
    TEXT_TO_IMAGE_ENDPOINT,
    API_TOKEN
)
from src.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from src.services.storage import storage

logger = logging.getLogger(__name__)

# Circuit Breaker Instance
circuit_breaker = CircuitBreaker(failure_threshold=15, reset_timeout=30)

class APIClient:
    """
    Unified API Client with Circuit Breaker, Retries, Tracing, and MinIO integration.
    """
    
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {API_TOKEN}"
        }
        # Create a single persistent client to reuse connections
        limits = httpx.Limits(max_keepalive_connections=200, max_connections=500)
        self.client = httpx.AsyncClient(trust_env=False, timeout=60, limits=limits)

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """
        Internal request wrapper with Circuit Breaker and Tracing.
        """
        trace_id = str(uuid.uuid4())
        headers = kwargs.get("headers", {})
        headers.update(self.headers)
        headers["X-Trace-ID"] = trace_id
        kwargs["headers"] = headers

        async def _do_request():
            logger.debug(f"[{trace_id}] {method} {url}")
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()
            return response

        try:
            return await circuit_breaker.call(_do_request)
        except CircuitBreakerOpenException:
            logger.error(f"[{trace_id}] Circuit Breaker is OPEN. Request to {url} blocked.")
            raise
        except Exception as e:
            logger.error(f"[{trace_id}] Request failed: {e}")
            raise

    @async_retry(max_retries=3)
    async def submit_perfect_video_insert(self, prompt: str, image_path: str, width: int = 512, height: int = 512, length: int = 81, priority: int = 0) -> str:
        """
        Submit perfect_video_insert task.
        image_path: MinIO Object Key
        """
        from config import MINIO_TEMPLATE_BUCKET
        if image_path.startswith("template:"):
            image_bytes = storage.get_file_bytes(image_path.split("template:")[1], bucket=MINIO_TEMPLATE_BUCKET)
        else:
            image_bytes = storage.get_file_bytes(image_path)
            
        if not image_bytes:
            raise ValueError(f"Failed to retrieve file from storage: {image_path}")

        files = {"image": (os.path.basename(image_path.replace("template:", "")), image_bytes, "image/jpeg")}
        data = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "length": length,
            "priority": priority
        }

        r = await self._request("POST", PERFECT_VIDEO_INSERT_ENDPOINT, files=files, data=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_perfect_video_edit(self, prompt: str, image_path: str, width: int = 512, height: int = 512, length: int = 81, priority: int = 0) -> str:
        """
        Submit perfect_video_edit task.
        image_path: MinIO Object Key
        """
        from config import MINIO_TEMPLATE_BUCKET
        if image_path.startswith("template:"):
            image_bytes = storage.get_file_bytes(image_path.split("template:")[1], bucket=MINIO_TEMPLATE_BUCKET)
        else:
            image_bytes = storage.get_file_bytes(image_path)
            
        if not image_bytes:
            raise ValueError(f"Failed to retrieve file from storage: {image_path}")

        files = {"image": (os.path.basename(image_path.replace("template:", "")), image_bytes, "image/jpeg")}
        data = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "length": length,
            "priority": priority
        }

        r = await self._request("POST", PERFECT_VIDEO_EDIT_ENDPOINT, files=files, data=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_img2img(self, prompt: str, image_paths: list[str], negative_prompt: str = " ", priority: int = 0) -> str:
        """
        Submit img2img task.
        image_paths: List of MinIO Object Keys
        """
        files_payload = []
        from config import MINIO_TEMPLATE_BUCKET
        
        # FastAPI might only expect one "image" field based on the changelog,
        # but if we have multiple, we either send them as a list if supported, 
        # or we might need to send them as separate fields (e.g. image1, image2)
        # Assuming the backend handles multiple 'image' fields for multi-image tasks like penetration
        for i, path in enumerate(image_paths):
            if path.startswith("template:"):
                # Extract real path and fetch from template bucket
                real_path = path.split("template:")[1]
                content = storage.get_file_bytes(real_path, bucket=MINIO_TEMPLATE_BUCKET)
            else:
                content = storage.get_file_bytes(path)
                
            if not content:
                logger.warning(f"Skipping missing file: {path}")
                continue
            
            if i == 0:
                files_payload.append(("image", (os.path.basename(path.replace("template:", "")), content, "image/jpeg")))
            else:
                files_payload.append(("image2", (os.path.basename(path.replace("template:", "")), content, "image/jpeg")))
        
        if not files_payload:
            raise ValueError("No valid images found for submission")

        data = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "num_inference_steps": 6,
            "guidance_scale": 1.0,
            "seed": -1,
            "priority": priority
        }

        logger.info(f"Submitting img2img task. Prompt: {prompt}, Negative: {negative_prompt}, Priority: {priority}")
        r = await self._request("POST", IMG2IMG_ENDPOINT, files=files_payload, data=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_face_swap(self, face_image_path: str, body_image_path: str, priority: int = 0) -> str:
        """
        Submit face swap task.
        paths: MinIO Object Keys
        """
        from config import MINIO_TEMPLATE_BUCKET
        
        if face_image_path.startswith("template:"):
            face_bytes = storage.get_file_bytes(face_image_path.split("template:")[1], bucket=MINIO_TEMPLATE_BUCKET)
        else:
            face_bytes = storage.get_file_bytes(face_image_path)
            
        if body_image_path.startswith("template:"):
            body_bytes = storage.get_file_bytes(body_image_path.split("template:")[1], bucket=MINIO_TEMPLATE_BUCKET)
        else:
            body_bytes = storage.get_file_bytes(body_image_path)
        
        if not face_bytes or not body_bytes:
            raise ValueError("Failed to retrieve face or body image from storage")

        files = {
            "face_image": (os.path.basename(face_image_path.replace("template:", "")), face_bytes, "image/jpeg"),
            "body_image": (os.path.basename(body_image_path.replace("template:", "")), body_bytes, "image/jpeg"),
        }
        
        data = {
            "priority": priority
        }

        logger.info(f"Submitting face_swap task. Face: {face_image_path}, Body: {body_image_path}, Priority: {priority}")
        r = await self._request("POST", FACE_SWAP_ENDPOINT, files=files, data=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_text_to_image(self, prompt: str) -> str:
        """
        Submit text to image task (T2I Pornmaster Turbo).
        """
        data = {
            "prompt": prompt
        }
        params = {"async": "true"}

        logger.info(f"Submitting text_to_image task. Prompt: {prompt}")
        r = await self._request("POST", TEXT_TO_IMAGE_ENDPOINT, json=data, params=params)
        return r.json()["task_id"]

    async def get_system_status(self) -> Optional[dict]:
        url = f"{API_BASE}/system/status"
        try:
            r = await self._request("GET", url, timeout=5)
            return r.json()
        except Exception:
            return None



    @async_retry(max_retries=3)
    async def download_image(self, task_id: str) -> bytes:
        url = f"{IMAGE_ENDPOINT}/{task_id}"
        try:
            r = await self._request("GET", url)
            return r.content
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise RuntimeError("后端未找到生成的图片（可能是因为节点保存到了 temp 文件夹而导致读取失败），请联系管理员修复后端工作流。")
            raise RuntimeError(f"获取图片失败: HTTP {e.response.status_code}")

    @async_retry(max_retries=3)
    async def download_video(self, task_id: str) -> bytes:
        url = f"{VIDEO_ENDPOINT}/{task_id}"
        try:
            r = await self._request("GET", url)
            return r.content
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise RuntimeError("后端未找到生成的视频文件。")
            raise RuntimeError(f"获取视频失败: HTTP {e.response.status_code}")

    async def listen_for_progress(self, task_id: str, is_video: bool = False):
        """
        Async generator for task progress.
        """
        status_url = f"{STATUS_ENDPOINT}/{task_id}"
        
        while True:
            try:
                r = await self._request("GET", status_url, timeout=10)
                info = r.json()
                logger.debug(f"Task {task_id} status info: {info}")
                
                status = info.get("status")

                if status == "pending":
                    # Normalize queue_pos logic removed to let service handle it
                    pass
                
                yield info
                
                if status == "done":
                    return
                
                if status == "error":
                    raise RuntimeError(info.get("error", "generation failed"))
                
                await asyncio.sleep(POLL_INTERVAL)
                
            except Exception as e:
                logger.warning(f"Poll status failed for {task_id}: {e}")
                await asyncio.sleep(POLL_INTERVAL)

    async def close(self):
        """Close the underlying HTTP client"""
        if hasattr(self, 'client') and not self.client.is_closed:
            await self.client.aclose()

# Singleton Instance
api_client = APIClient()

# Export functions to maintain compatibility with existing imports
# These wrappers call the singleton instance methods
submit_perfect_video_insert = api_client.submit_perfect_video_insert
submit_perfect_video_edit = api_client.submit_perfect_video_edit
submit_img2img = api_client.submit_img2img
submit_face_swap = api_client.submit_face_swap
submit_text_to_image = api_client.submit_text_to_image
download_image = api_client.download_image
download_video = api_client.download_video
get_system_status = api_client.get_system_status

listen_for_progress = api_client.listen_for_progress

