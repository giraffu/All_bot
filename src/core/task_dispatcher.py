from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict

from src.constants import (
    DURATION_MULTIPLIER,
    LTX_DURATION_MULTIPLIER,
    LTX_RESOLUTION_COST,
    MODE_EDIT,
    MODE_FREE_EDIT_V2_5,
    MODE_FACE_SWAP,
    MODE_FACE_SWAP_V2,
    MODE_I2I_DRAW,
    MODE_I2I_PRO,
    MODE_IMG2IMG_LORA,
    MODE_PORNMASTER_FLUX2_EDIT_BF16,
    MODE_PORNMASTER_FLUX2_MULTI_EDIT,
    MODE_PORNMASTER_FLUX2_MULTI_EDIT_BF16,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    MODE_SCAIL2_ACTION_TRANSFER,
    MODE_SCAIL2_ACTION_TRANSFER_LONG,
    MODE_SCAIL2_FACE_SWAP_V2,
    MODE_SCAIL2_VIDEO_REPLACEMENT,
    MODE_TXT2IMG,
    MODE_WAN22_VIDEO_V2,
    RESOLUTION_COST,
    TASK_COSTS,
)
from src.core.task_core_service_providers import get_task_core_image_service
from src.core.task_core_types import CoreDomainError
from src.domain_config.scail2_video import (
    SCAIL2_FIXED_HEIGHT,
    SCAIL2_FIXED_WIDTH,
    SCAIL2_TASK_TYPES,
    Scail2DurationError,
    get_scail2_cost,
    get_scail2_frame_count,
    normalize_scail2_duration_seconds,
    normalize_scail2_negative_prompt,
    normalize_scail2_positive_prompt,
    resolve_scail2_execution_task_type,
)
from src.domain_config.task_type_registry import get_execution_task_type
from src.domain_config.wan22_aio_video import (
    build_wan22_aio_video_result_meta,
    get_wan22_video_v2_cost,
    is_legacy_wan22_image_to_video_task_type,
    normalize_wan22_video_v2_duration_seconds,
    normalize_wan22_video_v2_negative_prompt,
    normalize_wan22_video_v2_resolution_preset,
    resolve_wan22_aio_video_profile,
)
from src.lora_catalog import normalize_ltx_video_lora_items

EDIT_LIKE_TASK_TYPES = {MODE_EDIT, MODE_IMG2IMG_LORA}
PORNMASTER_FLUX2_EDIT_TASK_TYPES = {
    MODE_FREE_EDIT_V2_5,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    MODE_PORNMASTER_FLUX2_MULTI_EDIT,
    MODE_PORNMASTER_FLUX2_MULTI_EDIT_BF16,
    MODE_PORNMASTER_FLUX2_EDIT_BF16,
}
FACE_VIDEO_TASK_TYPES = {"face_video", "face_video_step1", "face_video_step2"}
LTX_VIDEO_MODE_I2V = "i2v"
LTX_VIDEO_MODE_FLF2V = "flf2v"
LTX_VIDEO_MODE_V2V_AUDIO = "v2v_audio"


@dataclass(frozen=True)
class TaskDispatcherFeatureFlags:
    free_edit_v2_enabled: bool = False


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
    negative_prompt: str | None
    mode: str
    image_path: str
    end_image_path: str | None
    video_path: str | None
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
class _Scail2SubmissionContext:
    prompt: str
    reference_image_path: str
    motion_video_path: str
    negative_prompt: str
    duration_seconds: int
    frame_count: int


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
    resolution, width, height = _resolve_video_dimensions(inputs.get("resolution", 512))
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

    saved_images = _get_saved_input_images(inputs)
    mode = _resolve_ltx_video_mode(inputs, saved_images=saved_images)
    image_path = saved_images[0] if saved_images else ""
    end_image_path = saved_images[1] if len(saved_images) > 1 else None
    video_path = image_path if mode == LTX_VIDEO_MODE_V2V_AUDIO else None

    return _LtxSubmissionContext(
        prompt=_get_input_prompt(inputs, "ltx video"),
        negative_prompt=(str(inputs.get("negative_prompt") or "").strip() or None),
        mode=mode,
        image_path=image_path,
        end_image_path=end_image_path,
        video_path=video_path,
        width=width,
        height=height,
        requested_seconds=_coerce_duration_seconds(_get_input_duration(inputs)),
        lora_items=normalize_ltx_video_lora_items(
            inputs.get("lora_items"),
            max_items=3,
        )
        or None,
    )


def _resolve_ltx_video_mode(
    inputs: Dict[str, Any],
    *,
    saved_images: list[str] | None = None,
) -> str:
    raw_mode = str(
        inputs.get("ltx_mode")
        or inputs.get("generation_mode")
        or inputs.get("mode")
        or ""
    ).strip()
    if raw_mode in {
        LTX_VIDEO_MODE_I2V,
        LTX_VIDEO_MODE_FLF2V,
        LTX_VIDEO_MODE_V2V_AUDIO,
    }:
        return raw_mode

    if inputs.get("video") or inputs.get("input_video"):
        return LTX_VIDEO_MODE_V2V_AUDIO

    images = saved_images if saved_images is not None else inputs.get("images", [])
    if bool(inputs.get("use_end_frame")) or bool(inputs.get("end_image")):
        return LTX_VIDEO_MODE_FLF2V
    if isinstance(images, list) and len(images) >= 2:
        return LTX_VIDEO_MODE_FLF2V
    return LTX_VIDEO_MODE_I2V


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


def _resolve_scail2_duration_seconds(inputs: Dict[str, Any]) -> int:
    task_type = str(inputs.get("task_type") or "").strip() or None
    try:
        return normalize_scail2_duration_seconds(
            inputs.get("duration") or inputs.get("length"),
            strict=True,
            task_type=task_type,
        )
    except Scail2DurationError as exc:
        if task_type == MODE_SCAIL2_ACTION_TRANSFER_LONG:
            message = "SCAIL-2 长时间动作迁移目前只支持 10、15 或 20 秒。"
        elif task_type == MODE_SCAIL2_ACTION_TRANSFER:
            message = "SCAIL-2 动作迁移目前只支持 5、8、10、15 或 20 秒。"
        else:
            message = "SCAIL-2 目前只支持 5 秒或 8 秒。"
        raise CoreDomainError(message) from exc


def _build_scail2_submission_context(
    inputs: Dict[str, Any],
    *,
    task_type: str,
) -> _Scail2SubmissionContext:
    saved_images = _get_saved_input_images(inputs)
    duration_seconds = _resolve_scail2_duration_seconds(
        {**inputs, "task_type": task_type}
    )
    return _Scail2SubmissionContext(
        prompt=normalize_scail2_positive_prompt(task_type, inputs.get("prompt")),
        reference_image_path=saved_images[0] if len(saved_images) > 0 else "",
        motion_video_path=saved_images[1] if len(saved_images) > 1 else "",
        negative_prompt=normalize_scail2_negative_prompt(inputs.get("negative_prompt")),
        duration_seconds=duration_seconds,
        frame_count=get_scail2_frame_count(
            duration_seconds,
            strict=True,
            task_type=task_type,
        ),
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


def _append_lora_metadata(
    metadata: Dict[str, Any], inputs: Dict[str, Any]
) -> Dict[str, Any]:
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


class PornmasterFlux2EditStrategy(BaseTaskStrategy):
    def __init__(
        self,
        task_type: str,
        *,
        feature_flags: TaskDispatcherFeatureFlags | None = None,
    ):
        self.task_type = task_type
        self.feature_flags = feature_flags or TaskDispatcherFeatureFlags()

    def _ensure_enabled(self) -> None:
        if not self.feature_flags.free_edit_v2_enabled:
            raise CoreDomainError(f"{self._display_name()} 当前未开放。")

    @staticmethod
    def _image_paths(inputs: Dict[str, Any]) -> list[str]:
        return _get_saved_input_images(inputs) or inputs.get("images", [])

    def _expected_image_count(self, inputs: Dict[str, Any]) -> int:
        if self.task_type == MODE_FREE_EDIT_V2_5:
            image_count = len(self._image_paths(inputs))
            if image_count not in {1, 2}:
                raise CoreDomainError("自由P图 v2.5 当前任务需要上传 1 或 2 张参考图。")
            return image_count
        return (
            2
            if self._execution_task_type(inputs)
            in {
                MODE_PORNMASTER_FLUX2_MULTI_EDIT,
                MODE_PORNMASTER_FLUX2_MULTI_EDIT_BF16,
            }
            else 1
        )

    def _execution_task_type(self, inputs: Dict[str, Any]) -> str:
        if self.task_type == MODE_FREE_EDIT_V2_5:
            return (
                MODE_PORNMASTER_FLUX2_MULTI_EDIT_BF16
                if self._expected_image_count(inputs) == 2
                else MODE_PORNMASTER_FLUX2_EDIT_BF16
            )
        return get_execution_task_type(self.task_type) or self.task_type

    def _display_name(self) -> str:
        if self.task_type == MODE_FREE_EDIT_V2_5:
            return "自由P图 v2.5"
        if self.task_type == MODE_PORNMASTER_FLUX2_EDIT_BF16:
            return "自由P图 v3"
        return "自由P图 v2"

    def get_cost(self, inputs: Dict[str, Any]) -> int:
        self._ensure_enabled()
        if self.task_type == MODE_FREE_EDIT_V2_5:
            return 7 if self._expected_image_count(inputs) == 2 else 3
        return TASK_COSTS.get(self.task_type, 2)

    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"saved_inputs": _get_saved_input_images(inputs)}

    async def submit_task(
        self, task_id: str, inputs: Dict[str, Any], priority: int
    ) -> str:
        self._ensure_enabled()
        submission = _build_default_image_submission_context(
            inputs,
            seed_provider=_generate_dispatch_seed,
        )
        expected_images = self._expected_image_count(inputs)
        if len(submission.image_paths) != expected_images:
            raise CoreDomainError(
                f"{self._display_name()} 当前任务需要上传 {expected_images} 张参考图。"
            )
        image_service = _get_dispatch_image_service()
        return await image_service.submit_pornmaster_flux2_edit_task(
            task_id,
            execution_task_type=self._execution_task_type(inputs),
            prompt=submission.prompt,
            image_paths=submission.image_paths,
            negative_prompt=submission.negative_prompt,
            priority=priority,
        )


class FaceSwapStrategy(BaseTaskStrategy):
    def __init__(self, task_type: str = MODE_FACE_SWAP):
        self.task_type = task_type

    def get_cost(self, inputs: Dict[str, Any]) -> int:
        return TASK_COSTS[self.task_type]

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
            task_type=self.task_type,
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
                lora_items=inputs.get("lora_items"),
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

        if self.profile.execution_task_type != MODE_WAN22_VIDEO_V2:
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
                **(
                    {"lora_items": inputs.get("lora_items")}
                    if inputs.get("lora_items")
                    else {}
                ),
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
            **(
                {
                    "lora_name": inputs.get("lora_name") or None,
                    "lora_strength": inputs.get("lora_strength"),
                    "lora_items": inputs.get("lora_items"),
                }
                if inputs.get("lora_items") or inputs.get("lora_name")
                else {}
            ),
        )


class BaseVideoStrategy(BaseTaskStrategy):
    def __init__(self, mode: str):
        self.mode = mode

    def _is_wan22_image_to_video_task(self) -> bool:
        return is_legacy_wan22_image_to_video_task_type(self.mode)

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

        if self._is_wan22_image_to_video_task():
            return await self._wan22_delegate().submit_task(task_id, inputs, priority)

        submission = _build_video_submission_context(inputs)
        if self.mode in FACE_VIDEO_TASK_TYPES:
            face_img, video_path = _resolve_face_video_saved_inputs(
                submission.saved_images
            )
            dur_frames = 161 if submission.requested_duration_seconds >= 10 else 121
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

    def get_file_paths_to_upload(self, inputs: Dict[str, Any]) -> list[str]:
        mode = _resolve_ltx_video_mode(inputs)
        if mode == LTX_VIDEO_MODE_V2V_AUDIO:
            raise CoreDomainError("LTX 视频配音暂未开放。")

        images = inputs.get("images", [])
        if isinstance(images, list) and images:
            return images[:2] if mode == LTX_VIDEO_MODE_FLF2V else images[:1]

        if mode == LTX_VIDEO_MODE_FLF2V:
            return [inputs.get("image"), inputs.get("end_image")]
        return [inputs.get("image")] if inputs.get("image") else []

    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        saved_images = _get_saved_input_images(inputs)
        submission = _build_ltx_submission_context(inputs)
        metadata = {
            "saved_inputs": saved_images,
            "requested_duration": submission.requested_seconds,
            "ltx_mode": submission.mode,
            "ltx_width": submission.width,
            "ltx_height": submission.height,
            "extract_last_frame": submission.mode != LTX_VIDEO_MODE_I2V
            or bool(inputs.get("extract_last_frame")),
        }
        prev_task_id = str(inputs.get("ltx_prev_task_id") or "").strip()
        if prev_task_id:
            metadata["ltx_prev_task_id"] = prev_task_id
        chain_task_ids = inputs.get("ltx_chain_task_ids")
        if isinstance(chain_task_ids, list) and chain_task_ids:
            metadata["ltx_chain_task_ids"] = chain_task_ids
        return _append_lora_metadata(metadata, inputs)

    async def submit_task(
        self, task_id: str, inputs: Dict[str, Any], priority: int
    ) -> str:
        submission = _build_ltx_submission_context(inputs)
        if submission.mode == LTX_VIDEO_MODE_V2V_AUDIO:
            raise CoreDomainError("LTX 视频配音暂未开放。")

        image_service = _get_dispatch_image_service()
        if submission.mode == LTX_VIDEO_MODE_FLF2V:
            if not submission.image_path or not submission.end_image_path:
                raise CoreDomainError("LTX 首尾帧生成需要同时上传起始帧和终止帧。")
            optional_negative = (
                {"negative_prompt": submission.negative_prompt}
                if submission.negative_prompt
                else {}
            )
            return await image_service.submit_ltx_video_flf2v_task(
                task_id,
                prompt=submission.prompt,
                image_path=submission.image_path,
                end_image_path=submission.end_image_path,
                lora_name=inputs.get("lora_name"),
                lora_strength=inputs.get("lora_strength"),
                lora_items=submission.lora_items,
                width=submission.width,
                height=submission.height,
                length=submission.requested_seconds,
                priority=priority,
                **optional_negative,
            )

        if not submission.image_path:
            raise CoreDomainError("LTX 图生视频需要上传起始图片。")
        optional_negative = (
            {"negative_prompt": submission.negative_prompt}
            if submission.negative_prompt
            else {}
        )
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
            **optional_negative,
        )


class Wan22VideoV2Strategy(Wan22AioVideoStrategy):
    def __init__(self):
        super().__init__(MODE_WAN22_VIDEO_V2)


class Scail2VideoStrategy(BaseTaskStrategy):
    def __init__(self, task_type: str):
        self.task_type = task_type

    def _replacement_mode(self) -> bool:
        return self.task_type in {
            MODE_SCAIL2_VIDEO_REPLACEMENT,
            MODE_SCAIL2_FACE_SWAP_V2,
        }

    def _resolve_duration_seconds(self, inputs: Dict[str, Any]) -> int:
        return _resolve_scail2_duration_seconds({**inputs, "task_type": self.task_type})

    def get_cost(self, inputs: Dict[str, Any]) -> int:
        return get_scail2_cost(
            self._resolve_duration_seconds(inputs),
            strict=True,
            task_type=self.task_type,
        )

    def get_file_paths_to_upload(self, inputs: Dict[str, Any]) -> list[str]:
        if "images" in inputs and isinstance(inputs.get("images"), list):
            return inputs["images"][:2]
        return [inputs.get("image"), inputs.get("video")]

    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        saved_images = _get_saved_input_images(inputs)
        submission = _build_scail2_submission_context(inputs, task_type=self.task_type)
        duration_seconds = submission.duration_seconds
        return {
            "saved_inputs": saved_images,
            "requested_duration": duration_seconds,
            "scail2_duration_seconds": duration_seconds,
            "scail2_frame_count": get_scail2_frame_count(
                duration_seconds,
                strict=True,
                task_type=self.task_type,
            ),
            "scail2_width": SCAIL2_FIXED_WIDTH,
            "scail2_height": SCAIL2_FIXED_HEIGHT,
            "scail2_replacement_mode": self._replacement_mode(),
            "scail2_negative_prompt": submission.negative_prompt,
        }

    async def submit_task(
        self, task_id: str, inputs: Dict[str, Any], priority: int
    ) -> str:
        image_service = _get_dispatch_image_service()
        submission = _build_scail2_submission_context(inputs, task_type=self.task_type)

        if not submission.reference_image_path or not submission.motion_video_path:
            raise CoreDomainError("SCAIL-2 任务需要同时上传参考图片和驱动视频。")

        execution_task_type = resolve_scail2_execution_task_type(
            self.task_type,
            submission.duration_seconds,
        )
        return await image_service.submit_scail2_video_task(
            task_id,
            task_type=execution_task_type,
            reference_image_path=submission.reference_image_path,
            motion_video_path=submission.motion_video_path,
            prompt=submission.prompt,
            negative_prompt=submission.negative_prompt,
            length=submission.duration_seconds,
            priority=priority,
        )


def _build_default_image_strategy(
    task_type: str,
    _feature_flags: TaskDispatcherFeatureFlags | None = None,
) -> BaseTaskStrategy:
    return DefaultImageStrategy(task_type)


def _build_video_strategy(
    task_type: str,
    _feature_flags: TaskDispatcherFeatureFlags | None = None,
) -> BaseTaskStrategy:
    if is_legacy_wan22_image_to_video_task_type(task_type):
        return Wan22AioVideoStrategy(task_type)
    return BaseVideoStrategy(task_type)


STRATEGY_BUILDERS: dict[str, callable] = {
    MODE_FACE_SWAP: lambda task_type, _feature_flags: FaceSwapStrategy(task_type),
    MODE_FACE_SWAP_V2: lambda task_type, _feature_flags: FaceSwapStrategy(task_type),
    "ltx_video": lambda _task_type, _feature_flags: LtxVideoStrategy(),
    MODE_WAN22_VIDEO_V2: lambda _task_type, _feature_flags: Wan22VideoV2Strategy(),
    **dict.fromkeys(
        SCAIL2_TASK_TYPES,
        lambda task_type, _feature_flags: Scail2VideoStrategy(task_type),
    ),
    **dict.fromkeys(
        PORNMASTER_FLUX2_EDIT_TASK_TYPES,
        lambda task_type, feature_flags: PornmasterFlux2EditStrategy(
            task_type,
            feature_flags=feature_flags,
        ),
    ),
    MODE_I2I_PRO: _build_default_image_strategy,
    MODE_I2I_DRAW: _build_default_image_strategy,
}


class StrategyFactory:
    @staticmethod
    def get_strategy(
        task_type: str,
        *,
        feature_flags: TaskDispatcherFeatureFlags | None = None,
    ) -> BaseTaskStrategy:
        from src.constants import VIDEO_TASK_TYPES

        resolved_feature_flags = feature_flags or TaskDispatcherFeatureFlags()
        builder = STRATEGY_BUILDERS.get(task_type)
        if builder is not None:
            return builder(task_type, resolved_feature_flags)
        if task_type in VIDEO_TASK_TYPES:
            return _build_video_strategy(task_type, resolved_feature_flags)
        return _build_default_image_strategy(task_type, resolved_feature_flags)


async def dispatch_to_worker(
    task_id: str,
    task_type: str,
    inputs: Dict[str, Any],
    priority: int,
    *,
    feature_flags: TaskDispatcherFeatureFlags | None = None,
) -> str:
    """统一的请求发送口"""
    strategy = StrategyFactory.get_strategy(task_type, feature_flags=feature_flags)
    return await strategy.submit_task(task_id, inputs, priority)
