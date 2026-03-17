import asyncio
from typing import AsyncGenerator, Optional
from src.api_client import submit_img2img, listen_for_progress, download_image, download_video, get_system_status, submit_face_swap, submit_perfect_video_edit, submit_perfect_video_insert, get_queue_position

class ImageService:
    async def submit_task(self, prompt: str, image_paths: list[str], negative_prompt: str, priority: int = 0) -> str:
        """Submit image generation task"""
        return await submit_img2img(prompt, image_paths, negative_prompt, priority=priority)

    async def submit_face_swap_task(self, face_image_path: str, body_image_path: str, priority: int = 0) -> str:
        """Submit face swap task"""
        return await submit_face_swap(face_image_path, body_image_path, priority=priority)

    async def submit_perfect_video_edit(self, prompt: str, image_path: str, width: int = 512, height: int = 512, length: int = 81, priority: int = 0) -> str:
        """Submit perfect video edit task"""
        return await submit_perfect_video_edit(prompt, image_path, width=width, height=height, length=length, priority=priority)

    async def submit_perfect_video_insert_task(self, prompt: str, image_path: str, width: int = 512, height: int = 512, length: int = 81, priority: int = 0) -> str:
        """Submit perfect video insert task"""
        return await submit_perfect_video_insert(prompt, image_path, width=width, height=height, length=length, priority=priority)

    async def monitor_progress(self, task_id: str, is_video: bool = False) -> AsyncGenerator[dict, None]:
        """Monitor task progress"""
        async for info in listen_for_progress(task_id, is_video):
            yield info

    async def download_result(self, task_id: str) -> bytes:
        """Download generated image"""
        return await download_image(task_id)

    async def download_video_result(self, task_id: str) -> bytes:
        """Download generated video"""
        return await download_video(task_id)

    async def get_queue_info(self) -> dict:
        """Get system queue info"""
        return await get_system_status()

    async def get_queue_position(self, task_id: str) -> dict:
        """Get exact queue position for a task"""
        return await get_queue_position(task_id)

# Singleton instance
image_service = ImageService()
