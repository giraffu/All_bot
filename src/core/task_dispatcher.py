from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict

from src.constants import (
    DURATION_MULTIPLIER,
    LTX_DURATION_MULTIPLIER,
    LTX_RESOLUTION_COST,
    MODE_CUSTOM_VIDEO,
    MODE_EDIT,
    MODE_FACESWAP_STEP1,
    MODE_IMAGE_TO_VIDEO,
    MODE_IMG2IMG_LORA,
    MODE_I2I_PRO,
    MODE_I2I_DRAW,
    MODE_WAN22_VIDEO_V2,
    RESOLUTION_COST,
    TASK_COSTS,
    MODE_TXT2IMG,
)
from src.core.task_core_service_providers import get_task_core_image_service
from src.domain_config.wan22_aio_video import (
    build_wan22_aio_video_result_meta,
    get_wan22_video_v2_cost,
    normalize_wan22_video_v2_duration_seconds,
    normalize_wan22_video_v2_negative_prompt,
    normalize_wan22_video_v2_resolution_preset,
    resolve_wan22_aio_video_profile,
)
from src.lora_catalog import normalize_ltx_video_lora_items


EDIT_LIKE_TASK_TYPES = {MODE_EDIT, MODE_IMG2IMG_LORA}
FACE_VIDEO_TASK_TYPES = {"face_video", "face_video_step1", "face_video_step2"}


def _get_saved_input_images(inputs: Dict[str, Any]) -> list[str]:
    return inputs.get("saved_input_images", [])


def _get_primary_saved_input(inputs: Dict[str, Any]) -> str:
    saved_images = _get_saved_input_images(inputs)
    return saved_images[0] if saved_images else ""


def _get_input_prompt(inputs: Dict[str, Any], default: str) -> str:
    return inputs.get("prompt", default)


def _get_input_duration(inputs: Dict[str, Any], default: Any = 5) -> Any:
    return inputs.get("duration", default)


def _coerce_duration_seconds(duration: Any, default: int = 5) -> int:
    try:
        return int(str(duration).replace("s", ""))
    except (TypeError, ValueError):
        return default


def _resolve_face_video_saved_inputs(saved_images: list[str]) -> tuple[str, str]:
    face_image_path = saved_images[0] if len(saved_images) > 0 else ""
    target_video_path = saved_images[1] if len(saved_images) > 1 else ""
    return face_image_path, target_video_path


def _resolve_wan22_end_frame(saved_images: list[str]) -> tuple[bool, str | None]:
    use_end_frame = len(saved_images) > 1
    end_image_path = saved_images[1] if use_end_frame else None
    return use_end_frame, end_image_path


@dataclass(frozen=True)
class _VideoSubmissionContext:
    prompt: str
    duration: Any
    requested_duration_seconds: int
    resolution: int
    width: int
    height: int
    frame_length: int
    saved_images: list[str]
    image_path: str


@dataclass(frozen=True)
class _LtxSubmissionContext:
    prompt: str
    image_path: str
    width: int
    height: int
    requested_seconds: int
    lora_items: list[dict[str, Any]] | None


@dataclass(frozen=True)
class _Wan22SubmissionContext:
    prompt: str
    image_path: str
    end_image_path: str | None
    use_end_frame: bool
    negative_prompt: str
    resolution_preset: str
    model_profile: str


@dataclass(frozen=True)
class _DefaultImageSubmissionContext:
    prompt: Any
    image_path: str
    image_paths: list[str]
    negative_prompt: str
    lora_name: str
    lora_strength: float
    seed: int


def _build_video_submission_context(
    inputs: Dict[str, Any],
    *,
    default_prompt: str = "video",
) -> _VideoSubmissionContext:
    duration = _get_input_duration(inputs)
    resolution, width, height = _resolve_video_dimensions(
        inputs.get("resolution", 512)
    )
    saved_images = _get_saved_input_images(inputs)
    return _VideoSubmissionContext(
        prompt=_get_input_prompt(inputs, default_prompt),
        duration=duration,
        requested_duration_seconds=_coerce_duration_seconds(duration),
        resolution=resolution,
        width=width,
        height=height,
        frame_length=_resolve_video_frame_length(duration),
        saved_images=saved_images,
        image_path=_get_primary_saved_input(inputs),
    )


def _build_ltx_submission_context(inputs: Dict[str, Any]) -> _LtxSubmissionContext:
    resolution = inputs.get("resolution", 512)
    res_str = str(resolution)
    try:
        width, height = map(int, res_str.split("x"))
    except Exception:
        width, height = 1280, 704

    return _LtxSubmissionContext(
        prompt=_get_input_prompt(inputs, "ltx video"),
        image_path=_get_primary_saved_input(inputs),
        width=width,
        height=height,
        requested_seconds=_coerce_duration_seconds(_get_input_duration(inputs)),
        lora_items=normalize_ltx_video_lora_items(
            inputs.get("lora_items"),
            max_items=3,
        )
        or None,
    )


def _build_wan22_submission_context(inputs: Dict[str, Any]) -> _Wan22SubmissionContext:
    saved_images = _get_saved_input_images(inputs)
    inferred_use_end_frame, end_image_path = _resolve_wan22_end_frame(saved_images)
    use_end_frame = bool(inputs.get("use_end_frame")) and bool(end_image_path)
    return _Wan22SubmissionContext(
        prompt=_get_input_prompt(inputs, "wan22 video"),
        image_path=saved_images[0] if saved_images else "",
        end_image_path=end_image_path,
        use_end_frame=use_end_frame or inferred_use_end_frame,
        negative_prompt=inputs.get("negative_prompt", " "),
        resolution_preset=inputs.get("resolution_preset")
        or inputs.get("wan22_resolution_preset")
        or inputs.get("resolution")
        or "preview",
        model_profile=str(inputs.get("wan22_model_profile") or "").strip(),
    )


def _generate_dispatch_seed() -> int:
    import random

    return random.randint(1, 9007199254740991)


def _build_default_image_submission_context(
    inputs: Dict[str, Any],
    *,
    seed_provider: Callable[[], int],
) -> _DefaultImageSubmissionContext:
    return _DefaultImageSubmissionContext(
        prompt=inputs.get("prompt"),
        image_path=_get_primary_saved_input(inputs),
        image_paths=_get_saved_input_images(inputs),
        negative_prompt=inputs.get("negative_prompt", " "),
        lora_name=inputs.get("lora_name", ""),
        lora_strength=inputs.get("lora_strength", 1.0),
        seed=seed_provider(),
    )


def _append_lora_metadata(metadata: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    lora_items = inputs.get("lora_items")
    if isinstance(lora_items, list) and lora_items:
        metadata["lora_items"] = lora_items
    lora_name = inputs.get("lora_name")
    if lora_name:
        metadata["lora_name"] = lora_name
    if inputs.get("lora_strength") is not None:
        metadata["lora_strength"] = inputs.get("lora_strength")
    return metadata


def _resolve_video_frame_length(duration: Any) -> int:
    duration = _coerce_duration_seconds(duration)

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

    def build_payload(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return inputs

    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return _append_lora_metadata(
            {"saved_inputs": _get_saved_input_images(inputs)},
            inputs,
        )

    def get_file_paths_to_upload(self, inputs: Dict[str, Any]) -> list[str]:
        """返回需要上传到 MinIO 的文件路径列表"""
        return inputs.get("images", [])

    @abstractmethod
    async def submit_task(
        self, task_id: str, inputs: Dict[str, Any], priority: int
    ) -> str:
        """Responsible for sending the task to backend via image_service"""
        pass


class DefaultImageStrategy(BaseTaskStrategy):
    def __init__(
        self,
        mode: str,
        *,
        seed_provider: Callable[[], int] = _generate_dispatch_seed,
    ):
        self.mode = mode
        self.seed_provider = seed_provider

    def get_cost(self, inputs: Dict[str, Any]) -> int:
        if self.mode in EDIT_LIKE_TASK_TYPES:
            return 6 if len(inputs.get("images", [])) >= 2 else 2
        return TASK_COSTS.get(self.mode, 2)

    async def submit_task(
        self, task_id: str, inputs: Dict[str, Any], priority: int
    ) -> str:
        image_service = _get_dispatch_image_service()
        submission = _build_default_image_submission_context(
            inputs,
            seed_provider=self.seed_provider,
        )
        if self.mode == MODE_I2I_PRO:
            return await image_service.submit_i2i_pro_task(
                task_id,
                prompt=submission.prompt,
                image_path=submission.image_path,
                seed=submission.seed,
                priority=priority,
            )
        elif self.mode == MODE_I2I_DRAW:
            return await image_service.submit_i2i_draw_task(
                task_id,
                prompt=submission.prompt,
                image_path=submission.image_path,
                seed=submission.seed,
                priority=priority,
            )
        elif self.mode == MODE_IMG2IMG_LORA:
            return await image_service.submit_img2img_lora_task(
                task_id,
                prompt=submission.prompt,
                image_paths=submission.image_paths,
                lora_name=submission.lora_name,
                negative_prompt=submission.negative_prompt,
                priority=priority,
                lora_strength=submission.lora_strength,
            )
        elif self.mode == MODE_TXT2IMG:
            return await image_service.submit_txt2img_task(
                task_id,
                prompt=submission.prompt,
                priority=priority,
            )
        else:
            return await image_service.submit_task(
                task_id,
                prompt=submission.prompt,
                image_paths=submission.image_paths,
                negative_prompt=submission.negative_prompt,
                priority=priority,
            )


class FaceSwapStrategy(BaseTaskStrategy):
    def get_cost(self, inputs: Dict[str, Any]) -> int:
        return TASK_COSTS.get(MODE_FACESWAP_STEP1, 6)

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


class Wan22AioVideoStrategy(BaseTaskStrategy):
    def __init__(self, task_type: str):
        self.task_type = task_type
        self.profile = resolve_wan22_aio_video_profile(task_type)

    def _resolve_resolution_preset(self, inputs: Dict[str, Any]) -> str:
        return normalize_wan22_video_v2_resolution_preset(
            inputs.get("resolution_preset")
            or inputs.get("wan22_resolution_preset")
            or inputs.get("resolution")
        )

    def _resolve_duration_seconds(self, inputs: Dict[str, Any]) -> int:
        return normalize_wan22_video_v2_duration_seconds(
            inputs.get("duration")
            or inputs.get("length")
            or inputs.get("requested_duration")
            or self.profile.default_duration_seconds
        )

    def get_cost(self, inputs: Dict[str, Any]) -> int:
        return get_wan22_video_v2_cost(
            self._resolve_resolution_preset(inputs),
            self._resolve_duration_seconds(inputs),
        )

    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        saved_images = _get_saved_input_images(inputs)
        resolution_preset = self._resolve_resolution_preset(inputs)
        duration_seconds = self._resolve_duration_seconds(inputs)
        use_end_frame = bool(inputs.get("use_end_frame")) and len(saved_images) > 1
        metadata = {
            "saved_inputs": saved_images,
            "requested_duration": duration_seconds,
            "resolution_preset": resolution_preset,
        }
        metadata.update(
            build_wan22_aio_video_result_meta(
                profile=self.profile,
                resolution_preset=resolution_preset,
                duration_seconds=duration_seconds,
                negative_prompt=inputs.get("negative_prompt"),
                use_end_frame=use_end_frame,
                prev_task_id=inputs.get("wan22_prev_task_id"),
                chain_task_ids=inputs.get("wan22_chain_task_ids"),
                lora_name=inputs.get("lora_name"),
                lora_strength=inputs.get("lora_strength"),
            )
        )
        if not metadata.get("wan22_chain_task_ids"):
            metadata.pop("wan22_chain_task_ids", None)
        if self.profile.allow_lora:
            metadata = _append_lora_metadata(metadata, inputs)
        return metadata

    async def submit_task(
        self, task_id: str, inputs: Dict[str, Any], priority: int
    ) -> str:
        image_service = _get_dispatch_image_service()
        submission = _build_wan22_submission_context(inputs)
        resolution_preset = self._resolve_resolution_preset(inputs)
        duration_seconds = self._resolve_duration_seconds(inputs)

        if self.profile.allow_lora:
            return await image_service.submit_image_to_video_task(
                task_id,
                prompt=submission.prompt,
                image_path=submission.image_path,
                lora_name=inputs.get("lora_name") or "",
                end_image_path=submission.end_image_path,
                negative_prompt=normalize_wan22_video_v2_negative_prompt(
                    submission.negative_prompt
                ),
                use_end_frame=submission.use_end_frame,
                resolution_preset=resolution_preset,
                wan22_model_profile=self.profile.model_profile,
                priority=priority,
                width=512,
                height=512,
                length=duration_seconds,
                extract_last_frame=True,
            )

        return await image_service.submit_wan22_video_v2_task(
            task_id,
            prompt=submission.prompt,
            image_path=submission.image_path,
            end_image_path=submission.end_image_path,
            negative_prompt=submission.negative_prompt,
            use_end_frame=submission.use_end_frame,
            resolution_preset=resolution_preset,
            wan22_model_profile=self.profile.model_profile,
            length=duration_seconds,
            priority=priority,
        )


class BaseVideoStrategy(BaseTaskStrategy):
    WAN22_IMAGE_TO_VIDEO_TASK_TYPES = {MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO}

    def __init__(self, mode: str):
        self.mode = mode

    def _is_wan22_image_to_video_task(self) -> bool:
        return self.mode in self.WAN22_IMAGE_TO_VIDEO_TASK_TYPES

    def _wan22_delegate(self) -> Wan22AioVideoStrategy:
        return Wan22AioVideoStrategy(self.mode)

    def _resolve_wan22_resolution_preset(self, inputs: Dict[str, Any]) -> str:
        return normalize_wan22_video_v2_resolution_preset(
            inputs.get("resolution_preset")
            or inputs.get("wan22_resolution_preset")
            or inputs.get("resolution")
        )

    def get_cost(self, inputs: Dict[str, Any]) -> int:
        if self._is_wan22_image_to_video_task():
            return self._wan22_delegate().get_cost(inputs)

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

    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        if not self._is_wan22_image_to_video_task():
            return super().get_metadata(inputs)

        return self._wan22_delegate().get_metadata(inputs)

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
        submission = _build_video_submission_context(inputs)

        if self.mode == "doggy_style":
            return await image_service.submit_perfect_video_insert_task(
                task_id,
                prompt=submission.prompt,
                image_path=submission.image_path,
                width=submission.width,
                height=submission.height,
                length=submission.frame_length,
                priority=priority,
            )
        elif self._is_wan22_image_to_video_task():
            return await self._wan22_delegate().submit_task(task_id, inputs, priority)
        elif self.mode in FACE_VIDEO_TASK_TYPES:
            face_img, video_path = _resolve_face_video_saved_inputs(
                submission.saved_images
            )
            dur_frames = (
                161 if submission.requested_duration_seconds >= 10 else 121
            )
            return await image_service.submit_face_video(
                task_id,
                face_image_path=face_img,
                video_path=video_path,
                resolution=submission.resolution,
                duration=dur_frames,
                priority=priority,
            )
        else:
            return await image_service.submit_perfect_video_edit(
                task_id,
                prompt=submission.prompt,
                image_path=submission.image_path,
                priority=priority,
                width=submission.width,
                height=submission.height,
                length=submission.frame_length,
            )


class LtxVideoStrategy(BaseTaskStrategy):
    def get_cost(self, inputs: Dict[str, Any]) -> int:
        resolution = inputs.get("resolution", 512)
        duration = _get_input_duration(inputs)

        res_str = str(resolution)
        dur_str = f"{duration}s" if isinstance(duration, int) else str(duration)
        if not dur_str.endswith("s"):
            dur_str += "s"
        base_cost = LTX_RESOLUTION_COST.get(res_str, 10)
        multiplier = LTX_DURATION_MULTIPLIER.get(dur_str, 1.0)
        return int(base_cost * multiplier)

    async def submit_task(
        self, task_id: str, inputs: Dict[str, Any], priority: int
    ) -> str:
        image_service = _get_dispatch_image_service()
        submission = _build_ltx_submission_context(inputs)
        return await image_service.submit_ltx_video_task(
            task_id,
            prompt=submission.prompt,
            image_path=submission.image_path,
            lora_name=inputs.get("lora_name"),
            lora_strength=inputs.get("lora_strength"),
            lora_items=submission.lora_items,
            width=submission.width,
            height=submission.height,
            length=submission.requested_seconds,
            priority=priority,
        )


class Wan22VideoV2Strategy(Wan22AioVideoStrategy):
    def __init__(self):
        super().__init__(MODE_WAN22_VIDEO_V2)


def _build_default_image_strategy(task_type: str) -> BaseTaskStrategy:
    return DefaultImageStrategy(task_type)


def _build_video_strategy(task_type: str) -> BaseTaskStrategy:
    if task_type in {MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO}:
        return Wan22AioVideoStrategy(task_type)
    return BaseVideoStrategy(task_type)


STRATEGY_BUILDERS: dict[str, callable] = {
    "face_swap": lambda _task_type: FaceSwapStrategy(),
    "ltx_video": lambda _task_type: LtxVideoStrategy(),
    MODE_WAN22_VIDEO_V2: lambda _task_type: Wan22VideoV2Strategy(),
    MODE_I2I_PRO: _build_default_image_strategy,
    MODE_I2I_DRAW: _build_default_image_strategy,
}


class StrategyFactory:
    @staticmethod
    def get_strategy(task_type: str) -> BaseTaskStrategy:
        from src.constants import VIDEO_TASK_TYPES

        builder = STRATEGY_BUILDERS.get(task_type)
        if builder is not None:
            return builder(task_type)
        if task_type in VIDEO_TASK_TYPES:
            return _build_video_strategy(task_type)
        return _build_default_image_strategy(task_type)


async def dispatch_to_worker(
    task_id: str, task_type: str, inputs: Dict[str, Any], priority: int
) -> str:
    """统一的请求发送口"""
    strategy = StrategyFactory.get_strategy(task_type)
    return await strategy.submit_task(task_id, inputs, priority)
