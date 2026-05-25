from abc import ABC, abstractmethod
from typing import Any, Dict

from src.constants import (
    DURATION_MULTIPLIER,
    LTX_DURATION_MULTIPLIER,
    LTX_RESOLUTION_COST,
    MODE_EDIT,
    MODE_FACESWAP_STEP1,
    MODE_IMAGE_TO_VIDEO,
    MODE_IMG2IMG_LORA,
    MODE_I2I_PRO,
    MODE_I2I_DRAW,
    RESOLUTION_COST,
    TASK_COSTS,
)
from src.core.task_core_service_providers import get_task_core_image_service


LEGACY_TASK_TYPE_ALIASES = {
    "MODE_EDIT": MODE_EDIT,
    "MODE_IMAGE_TO_VIDEO": MODE_IMAGE_TO_VIDEO,
    "MODE_I2I_PRO": MODE_I2I_PRO,
    "MODE_I2I_DRAW": MODE_I2I_DRAW,
    "MODE_IMG2IMG_LORA": MODE_IMG2IMG_LORA,
}

EDIT_LIKE_TASK_TYPES = {MODE_EDIT, MODE_IMG2IMG_LORA}
FACE_VIDEO_TASK_TYPES = {"face_video", "face_video_step1", "face_video_step2"}


def _normalize_task_type(task_type: str) -> str:
    return LEGACY_TASK_TYPE_ALIASES.get(task_type, task_type)


def _get_saved_input_images(inputs: Dict[str, Any]) -> list[str]:
    return inputs.get("saved_input_images", [])


def _get_primary_saved_input(inputs: Dict[str, Any]) -> str:
    saved_images = _get_saved_input_images(inputs)
    return saved_images[0] if saved_images else ""


def _resolve_video_frame_length(duration: Any) -> int:
    if isinstance(duration, str):
        duration = int(duration.replace("s", ""))

    if duration >= 10:
        return 161
    if duration >= 8:
        return 129
    return 81


def _resolve_video_dimensions(resolution: Any) -> tuple[int, int, int]:
    width = height = 512
    resolved_resolution = resolution if resolution is not None else 512
    if isinstance(resolved_resolution, str):
        res_str = resolved_resolution.replace("p", "")
        if "x" in res_str:
            try:
                width, height = map(int, res_str.split("x"))
                resolved_resolution = max(width, height)
            except ValueError:
                resolved_resolution = 512
                width = height = 512
        else:
            try:
                resolved_resolution = int(res_str)
                width = height = resolved_resolution
            except ValueError:
                resolved_resolution = 512
                width = height = 512
    else:
        width = height = resolved_resolution

    return resolved_resolution, width, height


def _get_dispatch_image_service():
    return get_task_core_image_service()


class BaseTaskStrategy(ABC):
    @abstractmethod
    def get_cost(self, inputs: Dict[str, Any]) -> int:
        pass

    @abstractmethod
    def build_payload(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_file_paths_to_upload(self, inputs: Dict[str, Any]) -> list[str]:
        """返回需要上传到 MinIO 的文件路径列表"""
        pass

    @abstractmethod
    async def submit_task(
        self, task_id: str, inputs: Dict[str, Any], priority: int
    ) -> str:
        """Responsible for sending the task to backend via image_service"""
        pass


class DefaultImageStrategy(BaseTaskStrategy):
    def __init__(self, mode: str):
        self.mode = _normalize_task_type(mode)

    def get_cost(self, inputs: Dict[str, Any]) -> int:
        if self.mode in EDIT_LIKE_TASK_TYPES:
            return 6 if len(inputs.get("images", [])) >= 2 else 2
        return TASK_COSTS.get(self.mode, 2)

    def build_payload(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return inputs

    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"saved_inputs": inputs.get("saved_input_images", [])}

    def get_file_paths_to_upload(self, inputs: Dict[str, Any]) -> list[str]:
        return inputs.get("images", [])

    async def submit_task(
        self, task_id: str, inputs: Dict[str, Any], priority: int
    ) -> str:
        image_service = _get_dispatch_image_service()
        if self.mode == MODE_I2I_PRO:
            import random

            seed = random.randint(1, 9007199254740991)
            return await image_service.submit_i2i_pro_task(
                task_id,
                prompt=inputs.get("prompt"),
                image_path=_get_primary_saved_input(inputs),
                seed=seed,
                priority=priority,
            )
        elif self.mode == MODE_I2I_DRAW:
            import random

            seed = random.randint(1, 9007199254740991)
            return await image_service.submit_i2i_draw_task(
                task_id,
                prompt=inputs.get("prompt"),
                image_path=_get_primary_saved_input(inputs),
                seed=seed,
                priority=priority,
            )
        elif self.mode == MODE_IMG2IMG_LORA:
            return await image_service.submit_img2img_lora_task(
                task_id,
                prompt=inputs.get("prompt"),
                image_paths=_get_saved_input_images(inputs),
                lora_name=inputs.get("lora_name", ""),
                negative_prompt=inputs.get("negative_prompt", " "),
                priority=priority,
                lora_strength=inputs.get("lora_strength", 1.0),
            )
        else:
            return await image_service.submit_task(
                task_id,
                prompt=inputs.get("prompt"),
                image_paths=_get_saved_input_images(inputs),
                negative_prompt=inputs.get("negative_prompt", " "),
                priority=priority,
            )


class FaceSwapStrategy(BaseTaskStrategy):
    def get_cost(self, inputs: Dict[str, Any]) -> int:
        return TASK_COSTS.get(MODE_FACESWAP_STEP1, 6)

    def build_payload(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return inputs

    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"saved_inputs": _get_saved_input_images(inputs)}

    def get_file_paths_to_upload(self, inputs: Dict[str, Any]) -> list[str]:
        # 按照原来的逻辑：先是 body_img (target_image)，再是 face_img (face_image)
        if "images" in inputs and len(inputs.get("images", [])) >= 2:
            return inputs["images"]
        return [inputs.get("target_image"), inputs.get("face_image")]

    async def submit_task(
        self, task_id: str, inputs: Dict[str, Any], priority: int
    ) -> str:
        image_service = _get_dispatch_image_service()
        saved_images = _get_saved_input_images(inputs)
        return await image_service.submit_face_swap_task(
            task_id,
            face_image_path=saved_images[1] if len(saved_images) > 1 else "",
            body_image_path=saved_images[0] if len(saved_images) > 0 else "",
            priority=priority,
        )


class BaseVideoStrategy(BaseTaskStrategy):
    IMAGE_TO_VIDEO_LORA_ENDPOINT_COMPAT_TASK_TYPES = {
        MODE_IMAGE_TO_VIDEO,
        "custom_video",
        "video_edit",
        "perfect_video_edit",
    }

    def __init__(self, mode: str):
        self.mode = _normalize_task_type(mode)

    def _should_use_image_to_video_lora_endpoint(self, inputs: Dict[str, Any]) -> bool:
        return self.mode in self.IMAGE_TO_VIDEO_LORA_ENDPOINT_COMPAT_TASK_TYPES and bool(
            inputs.get("lora_name")
        )

    def get_cost(self, inputs: Dict[str, Any]) -> int:
        resolution = inputs.get("resolution", 512)
        duration = inputs.get("duration", 5)

        res_str = f"{resolution}p" if isinstance(resolution, int) else str(resolution)
        if not res_str.endswith("p"):
            res_str += "p"
        dur_str = f"{duration}s" if isinstance(duration, int) else str(duration)
        if not dur_str.endswith("s"):
            dur_str += "s"

        base_cost = RESOLUTION_COST.get(res_str, TASK_COSTS.get(self.mode, 6))
        multiplier = DURATION_MULTIPLIER.get(dur_str, 1.0)
        return int(base_cost * multiplier)

    def build_payload(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return inputs

    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"saved_inputs": _get_saved_input_images(inputs)}

    def get_file_paths_to_upload(self, inputs: Dict[str, Any]) -> list[str]:
        if self.mode in FACE_VIDEO_TASK_TYPES:
            if "images" in inputs and len(inputs.get("images", [])) >= 2:
                return inputs["images"]
            return [inputs.get("face_image"), inputs.get("target_video")]
        elif "images" in inputs:
            return inputs.get("images", [])
        return []

    async def submit_task(
        self, task_id: str, inputs: Dict[str, Any], priority: int
    ) -> str:
        image_service = _get_dispatch_image_service()
        duration = inputs.get("duration", 5)
        frame_length = _resolve_video_frame_length(duration)
        resolution, width, height = _resolve_video_dimensions(
            inputs.get("resolution", 512)
        )
        prompt = inputs.get("prompt", "video")
        saved_images = _get_saved_input_images(inputs)
        image_path = _get_primary_saved_input(inputs)

        if self.mode == "doggy_style":
            return await image_service.submit_perfect_video_insert_task(
                task_id,
                prompt=prompt,
                image_path=image_path,
                width=width,
                height=height,
                length=frame_length,
                priority=priority,
            )
        elif self._should_use_image_to_video_lora_endpoint(inputs):
            return await image_service.submit_image_to_video_task(
                task_id,
                prompt=prompt,
                image_path=image_path,
                lora_name=inputs.get("lora_name"),
                priority=priority,
                width=width,
                height=height,
                length=frame_length,
            )
        elif self.mode in FACE_VIDEO_TASK_TYPES:
            face_img = saved_images[0] if len(saved_images) > 0 else ""
            video_path = saved_images[1] if len(saved_images) > 1 else ""
            requested_duration = (
                int(str(duration).replace("s", ""))
                if isinstance(duration, str)
                else duration
            )
            dur_frames = 161 if requested_duration >= 10 else 121
            return await image_service.submit_face_video(
                task_id,
                face_image_path=face_img,
                video_path=video_path,
                resolution=resolution,
                duration=dur_frames,
                priority=priority,
            )
        else:
            return await image_service.submit_perfect_video_edit(
                task_id,
                prompt=prompt,
                image_path=image_path,
                priority=priority,
                width=width,
                height=height,
                length=frame_length,
            )


class LtxVideoStrategy(BaseTaskStrategy):
    def get_cost(self, inputs: Dict[str, Any]) -> int:
        resolution = inputs.get("resolution", 512)
        duration = inputs.get("duration", 5)

        res_str = str(resolution)
        dur_str = f"{duration}s" if isinstance(duration, int) else str(duration)
        if not dur_str.endswith("s"):
            dur_str += "s"
        base_cost = LTX_RESOLUTION_COST.get(res_str, 10)
        multiplier = LTX_DURATION_MULTIPLIER.get(dur_str, 1.0)
        return int(base_cost * multiplier)

    def build_payload(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return inputs

    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"saved_inputs": _get_saved_input_images(inputs)}

    def get_file_paths_to_upload(self, inputs: Dict[str, Any]) -> list[str]:
        return inputs.get("images", [])

    async def submit_task(
        self, task_id: str, inputs: Dict[str, Any], priority: int
    ) -> str:
        image_service = _get_dispatch_image_service()
        resolution = inputs.get("resolution", 512)
        duration = inputs.get("duration", 5)

        res_str = str(resolution)
        try:
            width, height = map(int, res_str.split("x"))
        except Exception:
            width, height = 1280, 704

        # The LTX workflow expects `length` to be seconds on the mxSlider node,
        # then converts it to frames internally via `a * 24 + 1`.
        try:
            requested_seconds = int(str(duration).replace("s", ""))
        except (TypeError, ValueError):
            requested_seconds = 5

        image_path = _get_primary_saved_input(inputs)
        return await image_service.submit_ltx_video_task(
            task_id,
            prompt=inputs.get("prompt", "ltx video"),
            image_path=image_path,
            width=width,
            height=height,
            length=requested_seconds,
            priority=priority,
        )


class StrategyFactory:
    @staticmethod
    def get_strategy(task_type: str) -> BaseTaskStrategy:
        from src.constants import VIDEO_TASK_TYPES

        task_type = _normalize_task_type(task_type)

        if task_type == "face_swap":
            return FaceSwapStrategy()
        elif task_type == "ltx_video":
            return LtxVideoStrategy()
        elif task_type in VIDEO_TASK_TYPES:
            return BaseVideoStrategy(task_type)
        elif task_type in [MODE_I2I_PRO, MODE_I2I_DRAW]:
            return DefaultImageStrategy(task_type)
        else:
            return DefaultImageStrategy(task_type)


async def dispatch_to_worker(
    task_id: str, task_type: str, inputs: Dict[str, Any], priority: int
) -> str:
    """统一的请求发送口"""
    strategy = StrategyFactory.get_strategy(task_type)
    return await strategy.submit_task(task_id, inputs, priority)
