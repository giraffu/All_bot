from typing import Any, AsyncGenerator

from src.api_client import api_client
from src.domain_config.wan22_aio_video import (
    WAN22_AIO_EXECUTION_IMAGE_TO_VIDEO,
    WAN22_AIO_EXECUTION_WAN22_VIDEO_V2,
)


class ImageService:
    async def submit_minimax_h3_task(
        self,
        task_id: str,
        *,
        task_type: str,
        prompt: str,
        images: tuple[str, ...],
        reference_descriptions: tuple[str, ...],
        duration: int,
        resolution_preset: str,
        aspect_ratio: str,
        main_model: str = "10eros",
        width: int,
        height: int,
        frame_count: int,
        fps: int,
        seed: int | None,
        lora_items: tuple[dict[str, Any], ...] = (),
        priority: int = 0,
    ) -> str:
        return await api_client.submit_minimax_h3(
            task_id,
            task_type=task_type,
            prompt=prompt,
            images=images,
            reference_descriptions=reference_descriptions,
            duration=duration,
            resolution_preset=resolution_preset,
            aspect_ratio=aspect_ratio,
            main_model=main_model,
            width=width,
            height=height,
            frame_count=frame_count,
            fps=fps,
            seed=seed,
            lora_items=lora_items,
            priority=priority,
        )

    async def submit_ltx_video_v2_task(
        self,
        task_id: str,
        *,
        prompt: str,
        image_path: str,
        end_image_path: str | None = None,
        negative_prompt: str | None = None,
        width: int = 1280,
        height: int = 704,
        length: int = 5,
        priority: int = 0,
    ) -> str:
        return await api_client.submit_ltx_video_v2(
            task_id,
            prompt=prompt,
            image_path=image_path,
            end_image_path=end_image_path,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            length=length,
            priority=priority,
        )

    async def submit_prompt_optimization_task(
        self,
        task_id: str,
        *,
        payload: dict[str, Any],
        priority: int = 0,
    ) -> str:
        return await api_client.submit_prompt_optimization_task(
            task_id,
            payload=payload,
            priority=priority,
        )

    async def submit_ltx_t2v_task(
        self,
        task_id: str,
        *,
        task_type: str,
        prompt: str,
        negative_prompt: str | None,
        audio_prompt: str | None,
        character_sheet: str | None,
        character_description: str | None,
        character_sheets: tuple[str, ...],
        character_descriptions: tuple[str, ...],
        background_image: str | None,
        sulphur_strength: float | None,
        seed: int | None,
        width: int,
        height: int,
        length: int,
        frame_count: int,
        fps: int,
        priority: int = 0,
    ) -> str:
        return await api_client.submit_ltx_t2v(
            task_id,
            task_type=task_type,
            prompt=prompt,
            negative_prompt=negative_prompt,
            audio_prompt=audio_prompt,
            character_sheet=character_sheet,
            character_description=character_description,
            character_sheets=character_sheets,
            character_descriptions=character_descriptions,
            background_image=background_image,
            sulphur_strength=sulphur_strength,
            seed=seed,
            width=width,
            height=height,
            length=length,
            frame_count=frame_count,
            fps=fps,
            priority=priority,
        )

    async def submit_character_reference_build_task(
        self,
        task_id: str,
        *,
        prompt: str,
        image_path: str,
        priority: int = 0,
        character_view_index: int | None = None,
        character_view_type: str | None = None,
    ) -> str:
        return await api_client.submit_character_reference_build(
            task_id,
            prompt=prompt,
            image_path=image_path,
            priority=priority,
            character_view_index=character_view_index,
            character_view_type=character_view_type,
        )

    async def submit_ltx_video_task(
        self,
        task_id: str,
        prompt: str,
        image_path: str,
        negative_prompt: str | None = None,
        lora_name: str | None = None,
        lora_strength: float | None = None,
        lora_items: list[dict[str, Any]] | None = None,
        width: int = 1280,
        height: int = 704,
        length: int = 5,
        priority: int = 0,
    ) -> str:
        """Submit ltx video task"""
        return await api_client.submit_ltx_video(
            task_id,
            prompt,
            image_path,
            negative_prompt=negative_prompt,
            lora_name=lora_name,
            lora_strength=lora_strength,
            lora_items=lora_items,
            width=width,
            height=height,
            length=length,
            priority=priority,
        )

    async def submit_ltx_video_flf2v_task(
        self,
        task_id: str,
        prompt: str,
        image_path: str,
        end_image_path: str,
        negative_prompt: str | None = None,
        lora_name: str | None = None,
        lora_strength: float | None = None,
        lora_items: list[dict[str, Any]] | None = None,
        width: int = 1280,
        height: int = 704,
        length: int = 5,
        priority: int = 0,
    ) -> str:
        """Submit LTX first/last-frame video task."""
        return await api_client.submit_ltx_video_flf2v(
            task_id,
            prompt,
            image_path,
            end_image_path,
            negative_prompt=negative_prompt,
            lora_name=lora_name,
            lora_strength=lora_strength,
            lora_items=lora_items,
            width=width,
            height=height,
            length=length,
            priority=priority,
        )

    async def submit_ltx_video_v2v_audio_task(
        self,
        task_id: str,
        prompt: str,
        video_path: str,
        negative_prompt: str | None = None,
        lora_name: str | None = None,
        lora_strength: float | None = None,
        lora_items: list[dict[str, Any]] | None = None,
        width: int = 1280,
        height: int = 704,
        length: int = 5,
        priority: int = 0,
    ) -> str:
        """Submit LTX video+text model-audio task."""
        return await api_client.submit_ltx_video_v2v_audio(
            task_id,
            prompt,
            video_path,
            negative_prompt=negative_prompt,
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
        resolution_preset: str = "preview",
        wan22_model_profile: str = "",
        length: int = 5,
        priority: int = 0,
        lora_name: str | None = None,
        lora_strength: float | None = None,
        lora_items: list[dict[str, Any]] | None = None,
    ) -> str:
        return await self._submit_wan22_aio_video_task(
            execution_task_type=WAN22_AIO_EXECUTION_WAN22_VIDEO_V2,
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
            lora_name=lora_name,
            lora_strength=lora_strength,
            lora_items=lora_items,
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
        return await api_client.submit_face_video(
            task_id,
            face_image_path,
            video_path,
            resolution=resolution,
            duration=duration,
            priority=priority,
        )

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
        reference_preprocessed: bool = False,
    ) -> str:
        return await api_client.submit_scail2_video_task(
            task_id,
            task_type=task_type,
            reference_image_path=reference_image_path,
            motion_video_path=motion_video_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            length=length,
            priority=priority,
            reference_preprocessed=reference_preprocessed,
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
        return await api_client.submit_img2img(
            task_id, prompt, image_paths, negative_prompt, priority=priority
        )

    async def submit_face_swap_task(
        self,
        task_id: str,
        face_image_path: str,
        body_image_path: str,
        priority: int = 0,
        task_type: str = "face_swap",
    ) -> str:
        """Submit face swap task"""
        return await api_client.submit_face_swap(
            task_id,
            face_image_path,
            body_image_path,
            priority=priority,
            task_type=task_type,
        )

    async def submit_i2i_pro_task(
        self, task_id: str, prompt: str, image_path: str, seed: int, priority: int = 0
    ) -> str:
        """Submit i2i pro task"""
        return await api_client.submit_i2i_pro(
            task_id, prompt, image_path, seed, priority=priority
        )

    async def submit_i2i_draw_task(
        self, task_id: str, prompt: str, image_path: str, seed: int, priority: int = 0
    ) -> str:
        """Submit i2i draw task"""
        return await api_client.submit_i2i_draw(
            task_id, prompt, image_path, seed, priority=priority
        )

    async def submit_txt2img_task(
        self,
        task_id: str,
        prompt: str,
        priority: int = 0,
    ) -> str:
        """Submit txt2img task"""
        return await api_client.submit_txt2img_task(
            task_id,
            prompt,
            priority=priority,
        )

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
        return await api_client.submit_img2img_lora(
            task_id,
            prompt,
            image_paths,
            lora_name,
            negative_prompt=negative_prompt,
            priority=priority,
            lora_strength=lora_strength,
        )

    async def submit_pornmaster_flux2_edit_task(
        self,
        task_id: str,
        *,
        execution_task_type: str,
        prompt: str,
        image_paths: list[str],
        negative_prompt: str = " ",
        priority: int = 0,
    ) -> str:
        """Submit PornMaster Flux2 single/multiple image-edit task."""
        return await api_client.submit_pornmaster_flux2_edit(
            task_id,
            execution_task_type=execution_task_type,
            prompt=prompt,
            image_paths=image_paths,
            negative_prompt=negative_prompt,
            priority=priority,
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
        return await api_client.submit_perfect_video_edit(
            task_id,
            prompt,
            image_path,
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
        lora_items: list[dict[str, Any]] | None = None,
    ) -> str:
        """Submit unified image_to_video task"""
        return await self._submit_wan22_aio_video_task(
            execution_task_type=WAN22_AIO_EXECUTION_IMAGE_TO_VIDEO,
            task_id=task_id,
            prompt=prompt,
            image_path=image_path,
            lora_name=lora_name,
            end_image_path=end_image_path,
            negative_prompt=negative_prompt,
            use_end_frame=use_end_frame,
            resolution_preset=resolution_preset,
            wan22_model_profile=wan22_model_profile,
            width=width,
            height=height,
            length=length,
            extract_last_frame=extract_last_frame,
            priority=priority,
            lora_items=lora_items,
        )

    async def _submit_wan22_aio_video_task(
        self,
        *,
        execution_task_type: str,
        task_id: str,
        prompt: str,
        image_path: str,
        end_image_path: str | None = None,
        negative_prompt: str = " ",
        use_end_frame: bool = False,
        resolution_preset: str = "preview",
        wan22_model_profile: str = "",
        length: int = 5,
        priority: int = 0,
        lora_name: str | None = None,
        lora_strength: float | None = None,
        lora_items: list[dict[str, Any]] | None = None,
        width: int = 512,
        height: int = 512,
        extract_last_frame: bool = True,
    ) -> str:
        if execution_task_type == WAN22_AIO_EXECUTION_WAN22_VIDEO_V2:
            return await api_client.submit_wan22_video_v2(
                task_id,
                prompt,
                image_path,
                end_image_path=end_image_path,
                negative_prompt=negative_prompt,
                use_end_frame=use_end_frame,
                resolution_preset=resolution_preset,
                wan22_model_profile=wan22_model_profile,
                length=length,
                priority=priority,
                lora_name=lora_name,
                lora_strength=lora_strength,
                lora_items=lora_items,
            )

        return await api_client.submit_image_to_video_task(
            task_id,
            prompt,
            image_path,
            lora_name or "",
            end_image_path=end_image_path,
            negative_prompt=negative_prompt,
            use_end_frame=use_end_frame,
            resolution_preset=resolution_preset,
            wan22_model_profile=wan22_model_profile,
            width=width,
            height=height,
            length=length,
            extract_last_frame=extract_last_frame,
            priority=priority,
            lora_items=lora_items,
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
        return await api_client.submit_perfect_video_insert(
            task_id,
            prompt,
            image_path,
            width=width,
            height=height,
            length=length,
            priority=priority,
        )

    async def monitor_progress(
        self,
        task_id: str,
        is_video: bool = False,
        *,
        include_type_position: bool = True,
    ) -> AsyncGenerator[dict, None]:
        """Monitor task progress"""
        async for info in api_client.listen_for_progress(
            task_id,
            is_video,
            include_type_position=include_type_position,
        ):
            yield info

    async def download_result(self, task_id: str) -> bytes:
        """Download generated image"""
        return await api_client.download_image(task_id)

    async def download_video_result(self, task_id: str) -> bytes:
        """Download generated video"""
        return await api_client.download_video(task_id)

    async def get_queue_info(self) -> dict:
        """Get system queue info"""
        return await api_client.get_system_status()

    async def get_task_status(
        self,
        task_id: str,
        *,
        include_type_position: bool = False,
    ) -> dict[str, Any] | None:
        """Get current backend task status"""
        return await api_client.get_task_status(
            task_id,
            include_type_position=include_type_position,
        )


# Singleton instance
image_service = ImageService()
