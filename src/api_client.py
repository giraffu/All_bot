# api_client.py
import asyncio
import logging
import uuid
from typing import Any, Optional

import httpx
from asgi_correlation_id import correlation_id

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
    SCAIL2_ACTION_TRANSFER_ENDPOINT,
    SCAIL2_FACE_SWAP_V2_ENDPOINT,
    SCAIL2_VIDEO_REPLACEMENT_ENDPOINT,
    STATUS_ENDPOINT,
    TXT2IMG_ENDPOINT,
    VIDEO_ENDPOINT,
    WAN22_VIDEO_V2_ENDPOINT,
)
from src.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from src.domain_config.scail2_video import (
    SCAIL2_ACTION_TRANSFER_TASK_TYPE,
    SCAIL2_FACE_SWAP_V2_TASK_TYPE,
    SCAIL2_VIDEO_REPLACEMENT_TASK_TYPE,
)
from src.utils import async_retry

logger = logging.getLogger(__name__)

# Circuit Breaker Instance
circuit_breaker = CircuitBreaker(failure_threshold=15, reset_timeout=30)
BOT_STATUS_POLL_INTERVAL = 15.0


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
        use_circuit_breaker = kwargs.pop("use_circuit_breaker", True)
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
            if use_circuit_breaker:
                return await circuit_breaker.call(_do_request)
            return await _do_request()
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
        lora_name: str | None = "",
        *,
        end_image_path: str | None = None,
        negative_prompt: str = " ",
        use_end_frame: bool = False,
        resolution_preset: str = "preview",
        wan22_model_profile: str = "",
        width: int = 512,
        height: int = 512,
        length: int = 5,
        extract_last_frame: bool = True,
        priority: int = 0,
    ) -> str:
        """
        Submit image_to_video task.
        image_path: MinIO Object Key
        lora_name: Name of the LoRA to inject
        """
        return await self._submit_wan22_aio_video_task(
            endpoint=IMAGE_TO_VIDEO_ENDPOINT,
            execution_task_type="image_to_video",
            task_id=task_id,
            prompt=prompt,
            image_path=image_path,
            end_image_path=end_image_path,
            negative_prompt=negative_prompt,
            use_end_frame=use_end_frame,
            resolution_preset=resolution_preset,
            wan22_model_profile=wan22_model_profile,
            length=length,
            priority=priority,
            lora_name=lora_name or "",
            width=width,
            height=height,
            extract_last_frame=extract_last_frame,
        )

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
        resolution_preset: str = "preview",
        wan22_model_profile: str = "",
        length: int = 5,
        priority: int = 0,
    ) -> str:
        return await self._submit_wan22_aio_video_task(
            endpoint=WAN22_VIDEO_V2_ENDPOINT,
            execution_task_type="wan22_video_v2",
            task_id=task_id,
            prompt=prompt,
            image_path=image_path,
            end_image_path=end_image_path,
            negative_prompt=negative_prompt,
            use_end_frame=use_end_frame,
            resolution_preset=resolution_preset,
            wan22_model_profile=wan22_model_profile,
            length=length,
            priority=priority,
        )

    @async_retry(max_retries=3)
    async def submit_scail2_video_task(
        self,
        task_id: str,
        *,
        task_type: str,
        reference_image_path: str,
        motion_video_path: str,
        prompt: str,
        negative_prompt: str = " ",
        length: int = 5,
        priority: int = 0,
    ) -> str:
        endpoint_by_type = {
            SCAIL2_ACTION_TRANSFER_TASK_TYPE: SCAIL2_ACTION_TRANSFER_ENDPOINT,
            SCAIL2_VIDEO_REPLACEMENT_TASK_TYPE: SCAIL2_VIDEO_REPLACEMENT_ENDPOINT,
            SCAIL2_FACE_SWAP_V2_TASK_TYPE: SCAIL2_FACE_SWAP_V2_ENDPOINT,
        }
        endpoint = endpoint_by_type.get(task_type)
        if endpoint is None:
            raise ValueError(f"Unsupported SCAIL-2 task type: {task_type}")

        data = {
            "task_id": task_id,
            "image": reference_image_path,
            "video": motion_video_path,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "length": length,
            "priority": priority,
        }
        logger.info(
            "Submitting %s task. Prompt: %s, Duration: %ss, Priority: %s",
            task_type,
            prompt,
            length,
            priority,
        )
        response = await self._request("POST", endpoint, json=data)
        return response.json()["task_id"]

    async def _submit_wan22_aio_video_task(
        self,
        *,
        endpoint: str,
        execution_task_type: str,
        task_id: str,
        prompt: str,
        image_path: str,
        end_image_path: str | None,
        negative_prompt: str,
        use_end_frame: bool,
        resolution_preset: str,
        wan22_model_profile: str,
        length: int,
        priority: int,
        lora_name: str | None = None,
        width: int | None = None,
        height: int | None = None,
        extract_last_frame: bool | None = None,
    ) -> str:
        data: dict[str, Any] = {
            "task_id": task_id,
            "image": image_path,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "use_end_frame": use_end_frame,
            "resolution_preset": resolution_preset,
            "wan22_model_profile": wan22_model_profile,
            "length": length,
            "priority": priority,
        }
        if end_image_path:
            data["end_image"] = end_image_path
        if lora_name is not None:
            data["lora_name"] = lora_name
        if width is not None:
            data["width"] = width
        if height is not None:
            data["height"] = height
        if extract_last_frame is not None:
            data["extract_last_frame"] = extract_last_frame

        logger.info(
            "Submitting %s task. Prompt: %s, Use end frame: %s, Resolution preset: %s, Priority: %s",
            execution_task_type,
            prompt,
            use_end_frame,
            resolution_preset,
            priority,
        )
        response = await self._request("POST", endpoint, json=data)
        return response.json()["task_id"]

    @async_retry(max_retries=3)
    async def cancel_task(self, task_id: str) -> dict:
        url = f"{API_BASE}/api/tasks/{task_id}"
        response = await self._request("DELETE", url)
        return response.json()

    async def get_system_status(self) -> Optional[dict]:
        url = f"{API_BASE}/system/status"
        try:
            r = await self._request(
                "GET",
                url,
                timeout=12,
                use_circuit_breaker=False,
            )
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

    async def _fetch_progress_status(self, status_url: str) -> dict[str, Any]:
        response = await self._request("GET", status_url, timeout=10)
        return self._normalize_progress_payload(response.json())

    @staticmethod
    def _normalize_progress_payload(payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        if "error_msg" in normalized and "error" not in normalized:
            normalized["error"] = normalized["error_msg"]
        return normalized

    @staticmethod
    def _is_terminal_progress_payload(payload: dict[str, Any]) -> bool:
        status = payload.get("status")
        if status == "done":
            return True
        if status in ["error", "cancelled"]:
            raise RuntimeError(payload.get("error", "generation failed or cancelled"))
        return False

    async def _iter_pubsub_progress(self, *, task_id: str, status_url: str):
        import json

        import redis.asyncio as redis

        from config import REDIS_URL

        redis_client = None
        pubsub = None
        channel = f"comfy:task_events:{task_id}"
        try:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            pubsub = redis_client.pubsub()
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
                        event_data = self._normalize_progress_payload(
                            json.loads(message["data"])
                        )
                        logger.debug(f"Pub/Sub received for {task_id}: {event_data}")
                        yield event_data
                        if self._is_terminal_progress_payload(event_data):
                            break
                    else:
                        info = await self._fetch_progress_status(status_url)
                        yield info
                        if self._is_terminal_progress_payload(info):
                            break
                except asyncio.TimeoutError:
                    info = await self._fetch_progress_status(status_url)
                    yield info
                    if self._is_terminal_progress_payload(info):
                        break
        finally:
            if pubsub:
                try:
                    await pubsub.unsubscribe(channel)
                except Exception as exc:
                    logger.debug(
                        "Pub/Sub unsubscribe failed for %s during cleanup: %s",
                        task_id,
                        exc,
                    )
                try:
                    await pubsub.close()
                except Exception as exc:
                    logger.debug(
                        "Pub/Sub close failed for %s during cleanup: %s",
                        task_id,
                        exc,
                    )
            if redis_client:
                try:
                    await redis_client.aclose()
                except Exception as exc:
                    logger.debug(
                        "Redis client close failed for %s during Pub/Sub cleanup: %s",
                        task_id,
                        exc,
                    )

    async def _iter_poll_progress(self, *, task_id: str, status_url: str):
        while True:
            try:
                info = await self._fetch_progress_status(status_url)
                yield info
                if self._is_terminal_progress_payload(info):
                    break

                await asyncio.sleep(BOT_STATUS_POLL_INTERVAL)
            except Exception as inner_e:
                if (
                    isinstance(inner_e, httpx.HTTPStatusError)
                    and inner_e.response.status_code == 404
                ):
                    logger.warning(
                        f"Task {task_id} deleted by central (404), treating as cancelled."
                    )
                    yield {"status": "cancelled", "error": "Task cancelled (404)"}
                    raise RuntimeError("cancelled")
                logger.warning(f"Poll status failed for {task_id}: {inner_e}")
                await asyncio.sleep(BOT_STATUS_POLL_INTERVAL)

    async def listen_for_progress(self, task_id: str, is_video: bool = False):
        """
        Async generator for task progress using low-frequency HTTP polling.
        """
        status_url = f"{STATUS_ENDPOINT}/{task_id}"

        async for info in self._iter_poll_progress(
            task_id=task_id,
            status_url=status_url,
        ):
            yield info

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
