# api_client.py
import asyncio
import logging
import uuid
from typing import Any, Optional

import httpx

from config import (
    API_BASE,
    API_TOKEN,
    FACE_SWAP_ENDPOINT,
    FACE_VIDEO_ENDPOINT,
    IMAGE_TO_VIDEO_ENDPOINT,
    I2I_PRO_ENDPOINT,
    I2I_DRAW_ENDPOINT,
    IMAGE_ENDPOINT,
    IMG2IMG_ENDPOINT,
    IMG2IMG_LORA_ENDPOINT,
    LTX_VIDEO_ENDPOINT,
    PERFECT_VIDEO_EDIT_ENDPOINT,
    PERFECT_VIDEO_INSERT_ENDPOINT,
    POLL_INTERVAL,
    STATUS_ENDPOINT,
    TXT2IMG_ENDPOINT,
    VIDEO_ENDPOINT,
    WAN22_VIDEO_V2_ENDPOINT,
)
from src.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from src.utils import async_retry

logger = logging.getLogger(__name__)

# Circuit Breaker Instance
circuit_breaker = CircuitBreaker(failure_threshold=15, reset_timeout=30)

from asgi_correlation_id import correlation_id


class APIClient:
    """
    Unified API Client with Circuit Breaker, Retries, Tracing, and MinIO integration.
    """

    def __init__(self):
        self.headers = {"Authorization": f"Bearer {API_TOKEN}"}
        # Create a single persistent client to reuse connections
        limits = httpx.Limits(max_keepalive_connections=200, max_connections=500)
        self.client = httpx.AsyncClient(trust_env=False, timeout=60, limits=limits)

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """
        Internal request wrapper with Circuit Breaker and Tracing.
        """
        trace_id = correlation_id.get()
        if not trace_id:
            trace_id = str(uuid.uuid4())
            correlation_id.set(trace_id)

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
            logger.error(
                f"[{trace_id}] Circuit Breaker is OPEN. Request to {url} blocked."
            )
            raise
        except Exception as e:
            logger.error(f"[{trace_id}] Request failed: {e}")
            raise

    @async_retry(max_retries=3)
    async def submit_perfect_video_insert(
        self,
        task_id: str,
        prompt: str,
        image_path: str,
        width: int = 512,
        height: int = 512,
        length: int = 81,
        priority: int = 0,
    ) -> str:
        """
        Submit perfect_video_insert task.
        image_path: MinIO Object Key
        """
        # Changed to reference passing: we no longer download the file and send as multipart.
        data = {
            "task_id": task_id,
            "image": image_path,
            "prompt": prompt,
            "width": width,
            "height": height,
            "length": length,
            "priority": priority,
        }

        r = await self._request("POST", PERFECT_VIDEO_INSERT_ENDPOINT, json=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_perfect_video_edit(
        self,
        task_id: str,
        prompt: str,
        image_path: str,
        width: int = 512,
        height: int = 512,
        length: int = 81,
        priority: int = 0,
    ) -> str:
        """
        Submit perfect_video_edit task.
        image_path: MinIO Object Key
        """
        data = {
            "task_id": task_id,
            "image": image_path,
            "prompt": prompt,
            "width": width,
            "height": height,
            "length": length,
            "priority": priority,
        }

        r = await self._request("POST", PERFECT_VIDEO_EDIT_ENDPOINT, json=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_image_to_video_task(
        self,
        task_id: str,
        prompt: str,
        image_path: str,
        lora_name: str,
        width: int = 512,
        height: int = 512,
        length: int = 81,
        priority: int = 0,
    ) -> str:
        """
        Submit image_to_video task.
        image_path: MinIO Object Key
        lora_name: Name of the LoRA to inject
        """
        data = {
            "task_id": task_id,
            "image": image_path,
            "prompt": prompt,
            "lora_name": lora_name,
            "width": width,
            "height": height,
            "length": length,
            "priority": priority,
        }

        r = await self._request("POST", IMAGE_TO_VIDEO_ENDPOINT, json=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_img2img(
        self,
        task_id: str,
        prompt: str,
        image_paths: list[str],
        negative_prompt: str = " ",
        priority: int = 0,
    ) -> str:
        """
        Submit img2img task.
        image_paths: List of MinIO Object Keys
        """
        if not image_paths:
            raise ValueError("No valid images found for submission")

        data = {
            "task_id": task_id,
            "images": image_paths,  # 传递多图列表
            "image": image_paths[0],  # 保留以作向下兼容
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "num_inference_steps": 6,
            "guidance_scale": 1.0,
            "priority": priority,
        }

        # 兼容旧逻辑，如果有第二张也放到 image2
        if len(image_paths) > 1:
            data["image2"] = image_paths[1]

        logger.info(
            f"Submitting img2img task. Prompt: {prompt}, Negative: {negative_prompt}, Images: {len(image_paths)}, Priority: {priority}"
        )
        r = await self._request("POST", IMG2IMG_ENDPOINT, json=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_img2img_lora(
        self,
        task_id: str,
        prompt: str,
        image_paths: list[str],
        lora_name: str,
        negative_prompt: str = " ",
        priority: int = 0,
        lora_strength: float = 1.0,
    ) -> str:
        """
        Submit img2img_lora task.
        image_paths: List of MinIO Object Keys
        lora_name: Name of the LoRA to inject
        """
        if not image_paths:
            raise ValueError("No valid images found for submission")

        data = {
            "task_id": task_id,
            "images": image_paths,
            "image": image_paths[0],
            "prompt": prompt,
            "lora_name": lora_name,
            "lora_strength": lora_strength,
            "negative_prompt": negative_prompt,
            "num_inference_steps": 6,
            "guidance_scale": 1.0,
            "priority": priority,
        }

        if len(image_paths) > 1:
            data["image2"] = image_paths[1]

        logger.info(
            f"Submitting img2img_lora task. Prompt: {prompt}, LoRA: {lora_name}, Images: {len(image_paths)}, Priority: {priority}"
        )
        r = await self._request("POST", IMG2IMG_LORA_ENDPOINT, json=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_face_swap(
        self,
        task_id: str,
        face_image_path: str,
        body_image_path: str,
        priority: int = 0,
    ) -> str:
        """
        Submit face swap task.
        paths: MinIO Object Keys
        """
        if not face_image_path or not body_image_path:
            raise ValueError("Face or body image path is missing")

        data = {
            "task_id": task_id,
            "face_image": face_image_path,
            "body_image": body_image_path,
            "priority": priority,
        }

        logger.info(
            f"Submitting face_swap task. Face: {face_image_path}, Body: {body_image_path}, Priority: {priority}"
        )
        r = await self._request("POST", FACE_SWAP_ENDPOINT, json=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_face_video(
        self,
        task_id: str,
        face_image_path: str,
        video_path: str,
        resolution: int = 512,
        duration: int = 121,
        priority: int = 0,
    ) -> str:
        """
        Submit face video task.
        paths: MinIO Object Keys
        """
        if not face_image_path or not video_path:
            raise ValueError("Face or video path is missing")

        data = {
            "task_id": task_id,
            "face_image": face_image_path,
            "video": video_path,
            "resolution": resolution,
            "duration": duration,
            "priority": priority,
        }

        logger.info(
            f"Submitting face_video task. Face: {face_image_path}, Video: {video_path}, Priority: {priority}"
        )
        r = await self._request("POST", FACE_VIDEO_ENDPOINT, json=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_i2i_pro(
        self, task_id: str, prompt: str, image_path: str, seed: int, priority: int = 0
    ) -> str:
        """
        Submit i2i pro task.
        """
        data = {
            "task_id": task_id,
            "image": image_path,
            "prompt": prompt,
            "seed": seed,
            "priority": priority,
        }

        logger.info(
            f"Submitting i2i_pro task. Prompt: {prompt}, Seed: {seed}, Priority: {priority}"
        )
        r = await self._request("POST", I2I_PRO_ENDPOINT, json=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_i2i_draw(
        self, task_id: str, prompt: str, image_path: str, seed: int, priority: int = 0
    ) -> str:
        """
        Submit i2i draw task.
        """
        data = {
            "task_id": task_id,
            "image": image_path,
            "prompt": prompt,
            "seed": seed,
            "priority": priority,
        }

        logger.info(
            f"Submitting i2i_draw task. Prompt: {prompt}, Seed: {seed}, Priority: {priority}"
        )
        r = await self._request("POST", I2I_DRAW_ENDPOINT, json=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_txt2img_task(
        self,
        task_id: str,
        prompt: str,
        priority: int = 0,
    ) -> str:
        """
        Submit txt2img via the standard simple-task route.
        """
        data = {
            "task_id": task_id,
            "prompt": prompt,
            "priority": priority,
        }

        logger.info(f"Submitting txt2img task. Prompt: {prompt}, Priority: {priority}")
        r = await self._request("POST", TXT2IMG_ENDPOINT, json=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_ltx_video(
        self,
        task_id: str,
        prompt: str,
        image_path: str,
        lora_name: str | None = None,
        lora_strength: float | None = None,
        lora_items: list[dict[str, Any]] | None = None,
        width: int = 1280,
        height: int = 704,
        length: int = 5,
        priority: int = 0,
    ) -> str:
        """
        Submit ltx_video task.
        image_path: MinIO Object Key
        """
        data = {
            "task_id": task_id,
            "image": image_path,
            "prompt": prompt,
            "width": width,
            "height": height,
            "length": length,
            "priority": priority,
        }
        if lora_name:
            data["lora_name"] = lora_name
        if lora_strength is not None:
            data["lora_strength"] = lora_strength
        if lora_items:
            data["lora_items"] = lora_items

        logger.info(
            f"Submitting ltx_video task. Prompt: {prompt}, Priority: {priority}"
        )
        r = await self._request("POST", LTX_VIDEO_ENDPOINT, json=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def submit_wan22_video_v2(
        self,
        task_id: str,
        prompt: str,
        image_path: str,
        *,
        end_image_path: str | None = None,
        negative_prompt: str = " ",
        use_end_frame: bool = False,
        length: int = 5,
        priority: int = 0,
    ) -> str:
        data = {
            "task_id": task_id,
            "image": image_path,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "use_end_frame": use_end_frame,
            "length": length,
            "priority": priority,
        }
        if end_image_path:
            data["end_image"] = end_image_path

        logger.info(
            "Submitting wan22_video_v2 task. Prompt: %s, Use end frame: %s, Priority: %s",
            prompt,
            use_end_frame,
            priority,
        )
        r = await self._request("POST", WAN22_VIDEO_V2_ENDPOINT, json=data)
        return r.json()["task_id"]

    @async_retry(max_retries=3)
    async def cancel_task(self, task_id: str) -> dict:
        url = f"{API_BASE}/api/tasks/{task_id}"
        response = await self._request("DELETE", url)
        return response.json()

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
                raise RuntimeError(
                    "后端未找到生成的图片（可能是因为节点保存到了 temp 文件夹而导致读取失败），请联系管理员修复后端工作流。"
                )
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
        Async generator for task progress using Redis Pub/Sub.
        """
        status_url = f"{STATUS_ENDPOINT}/{task_id}"

        # Initial HTTP poll to get current state
        try:
            r = await self._request("GET", status_url, timeout=10)
            info = r.json()
            logger.debug(f"Task {task_id} initial status: {info}")
            yield info

            status = info.get("status")
            if status == "done":
                return
            if status in ["error", "cancelled"]:
                raise RuntimeError(info.get("error", "generation failed or cancelled"))
        except Exception as e:
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
                yield {"status": "cancelled", "error": "Task cancelled (404)"}
                raise RuntimeError(f"Task {task_id} not found on server (404).")
            logger.warning(f"Initial status fetch failed for {task_id}: {e}")

        # Subscribe to Pub/Sub
        import json

        import redis.asyncio as redis

        from config import REDIS_URL

        redis_client = None
        pubsub = None
        try:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            pubsub = redis_client.pubsub()
            channel = f"comfy:task_events:{task_id}"
            await pubsub.subscribe(channel)
            logger.info(f"Subscribed to {channel}")

            while True:
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(
                            ignore_subscribe_messages=True, timeout=10.0
                        ),
                        timeout=15.0,
                    )
                    if message and message.get("data"):
                        event_data = json.loads(message["data"])
                        if "error_msg" in event_data and "error" not in event_data:
                            event_data["error"] = event_data["error_msg"]

                        logger.debug(f"Pub/Sub received for {task_id}: {event_data}")
                        yield event_data

                        status = event_data.get("status")
                        if status == "done":
                            break
                        if status in ["error", "cancelled"]:
                            raise RuntimeError(
                                event_data.get(
                                    "error", "generation failed or cancelled"
                                )
                            )
                    else:
                        # Periodically poll via HTTP just in case we miss a message
                        r = await self._request("GET", status_url, timeout=10)
                        info = r.json()
                        yield info

                        status = info.get("status")
                        if status == "done":
                            break
                        if status in ["error", "cancelled"]:
                            raise RuntimeError(
                                info.get("error", "generation failed or cancelled")
                            )
                except asyncio.TimeoutError:
                    # Timeout from wait_for, do HTTP poll
                    r = await self._request("GET", status_url, timeout=10)
                    info = r.json()
                    yield info

                    status = info.get("status")
                    if status == "done":
                        break
                    if status in ["error", "cancelled"]:
                        raise RuntimeError(
                            info.get("error", "generation failed or cancelled")
                        )
        except Exception as e:
            logger.error(
                f"Pub/Sub error for {task_id}: {e}. Falling back to HTTP polling."
            )
            # Fallback to pure polling
            while True:
                try:
                    r = await self._request("GET", status_url, timeout=10)
                    info = r.json()
                    yield info

                    status = info.get("status")
                    if status == "done":
                        break
                    if status in ["error", "cancelled"]:
                        raise RuntimeError(
                            info.get("error", "generation failed or cancelled")
                        )

                    await asyncio.sleep(POLL_INTERVAL)
                except Exception as inner_e:
                    if isinstance(inner_e, httpx.HTTPStatusError) and inner_e.response.status_code == 404:
                        logger.warning(f"Task {task_id} deleted by central (404), treating as cancelled.")
                        yield {"status": "cancelled", "error": "Task cancelled (404)"}
                        raise RuntimeError("cancelled")
                    logger.warning(f"Poll status failed for {task_id}: {inner_e}")
                    await asyncio.sleep(POLL_INTERVAL)
        finally:
            if pubsub:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            if redis_client:
                await redis_client.aclose()

    @async_retry(max_retries=3)
    async def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        status_url = f"{STATUS_ENDPOINT}/{task_id}"
        try:
            response = await self._request("GET", status_url, timeout=10)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return response.json()

    async def close(self):
        """Close the underlying HTTP client"""
        if hasattr(self, "client") and not self.client.is_closed:
            await self.client.aclose()

api_client = APIClient()
