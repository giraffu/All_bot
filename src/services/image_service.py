from typing import Any, AsyncGenerator

from src.api_client import (
    download_image,
    download_video,
    get_system_status,
    listen_for_progress,
    submit_image_to_video_task,
    submit_face_swap,
    submit_face_video,
    submit_i2i_pro,
    submit_i2i_draw,
    submit_img2img,
    submit_img2img_lora,
    submit_ltx_video,
    submit_perfect_video_edit,
    submit_perfect_video_insert,
    submit_txt2img,
    submit_wan22_video_v2,
)


class ImageService:
    async def submit_ltx_video_task(
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
        """Submit ltx video task"""
        return await submit_ltx_video(
            task_id,
            prompt,
            image_path,
            lora_name=lora_name,
            lora_strength=lora_strength,
            lora_items=lora_items,
            width=width,
            height=height,
            length=length,
            priority=priority,
        )

    async def submit_wan22_video_v2_task(
        self,
        task_id: str,
        prompt: str,
        image_path: str,
        *,
        end_image_path: str | None = None,
        negative_prompt: str = " ",
        use_end_frame: bool = False,
        color_match: bool = False,
        perfect_loop: bool = False,
        upscale: bool = False,
        extract_last_frame: bool = False,
        length: int = 5,
        priority: int = 0,
    ) -> str:
        return await submit_wan22_video_v2(
            task_id,
            prompt,
            image_path,
            end_image_path=end_image_path,
            negative_prompt=negative_prompt,
            use_end_frame=use_end_frame,
            color_match=color_match,
            perfect_loop=perfect_loop,
            upscale=upscale,
            extract_last_frame=extract_last_frame,
            length=length,
            priority=priority,
        )

    async def submit_face_video(
        self,
        task_id: str,
        face_image_path: str,
        video_path: str,
        resolution: int = 512,
        duration: int = 121,
        priority: int = 0,
    ) -> str:
        """Submit face video task"""
        return await submit_face_video(
            task_id,
            face_image_path,
            video_path,
            resolution=resolution,
            duration=duration,
            priority=priority,
        )

    async def submit_task(
        self,
        task_id: str,
        prompt: str,
        image_paths: list[str],
        negative_prompt: str,
        priority: int = 0,
    ) -> str:
        """Submit image generation task"""
        return await submit_img2img(
            task_id, prompt, image_paths, negative_prompt, priority=priority
        )

    async def submit_face_swap_task(
        self,
        task_id: str,
        face_image_path: str,
        body_image_path: str,
        priority: int = 0,
    ) -> str:
        """Submit face swap task"""
        return await submit_face_swap(
            task_id, face_image_path, body_image_path, priority=priority
        )

    async def submit_i2i_pro_task(
        self, task_id: str, prompt: str, image_path: str, seed: int, priority: int = 0
    ) -> str:
        """Submit i2i pro task"""
        return await submit_i2i_pro(
            task_id, prompt, image_path, seed, priority=priority
        )

    async def submit_i2i_draw_task(
        self, task_id: str, prompt: str, image_path: str, seed: int, priority: int = 0
    ) -> str:
        """Submit i2i draw task"""
        return await submit_i2i_draw(
            task_id, prompt, image_path, seed, priority=priority
        )

    async def submit_txt2img_task(self, prompt: str, priority: int = 0) -> str:
        """Submit txt2img task"""
        return await submit_txt2img(prompt, priority=priority)

    async def submit_img2img_lora_task(
        self,
        task_id: str,
        prompt: str,
        image_paths: list[str],
        lora_name: str,
        negative_prompt: str = " ",
        priority: int = 0,
        lora_strength: float = 1.0,
    ) -> str:
        """Submit img2img_lora task and get task_id."""
        return await submit_img2img_lora(
            task_id,
            prompt,
            image_paths,
            lora_name,
            negative_prompt=negative_prompt,
            priority=priority,
            lora_strength=lora_strength,
        )

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
        """Submit perfect video edit task"""
        return await submit_perfect_video_edit(
            task_id,
            prompt,
            image_path,
            width=width,
            height=height,
            length=length,
            priority=priority,
        )

    async def submit_perfect_video_lora(
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
        """Compat wrapper for the legacy perfect video lora task"""
        return await self.submit_image_to_video_task(
            task_id=task_id,
            prompt=prompt,
            image_path=image_path,
            lora_name=lora_name,
            width=width,
            height=height,
            length=length,
            priority=priority,
        )

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
        """Submit unified image_to_video task"""
        return await submit_image_to_video_task(
            task_id,
            prompt,
            image_path,
            lora_name,
            width=width,
            height=height,
            length=length,
            priority=priority,
        )

    async def submit_perfect_video_insert_task(
        self,
        task_id: str,
        prompt: str,
        image_path: str,
        width: int = 512,
        height: int = 512,
        length: int = 81,
        priority: int = 0,
    ) -> str:
        """Submit perfect video insert task"""
        return await submit_perfect_video_insert(
            task_id,
            prompt,
            image_path,
            width=width,
            height=height,
            length=length,
            priority=priority,
        )

    async def monitor_progress(
        self, task_id: str, is_video: bool = False
    ) -> AsyncGenerator[dict, None]:
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


# Singleton instance
image_service = ImageService()
