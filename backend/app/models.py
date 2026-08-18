from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain_config.minimax_h3 import MINIMAX_H3_MAX_SEED
from src.domain_config.scail2_video import (
    SCAIL2_ACTION_TRANSFER_LONG_TASK_TYPE,
    SCAIL2_ACTION_TRANSFER_TASK_TYPE,
    SCAIL2_FACE_SWAP_V2_TASK_TYPE,
    SCAIL2_VIDEO_REPLACEMENT_TASK_TYPE,
    Scail2DurationError,
    normalize_scail2_duration_seconds,
)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    IMG2IMG = "img2img"
    IMG2IMG_LORA = "img2img_lora"
    FACE_SWAP = "face_swap"
    FACE_SWAP_V2 = "face_swap_v2"
    VIDEO_INSERT = "video_insert"
    VIDEO_EDIT = "video_edit"
    IMAGE_TO_VIDEO = "image_to_video"
    FACE_VIDEO = "face_video"
    T2I_PORNMASTER_TURBO = "t2i-pornmaster-turbo"
    I2I_PRO = "i2i_pro"
    I2I_DRAW = "i2i_draw"
    LTX_VIDEO = "ltx_video"
    LTX_VIDEO_FLF2V = "ltx_video_flf2v"
    LTX_VIDEO_V2V_AUDIO = "ltx_video_v2v_audio"
    LTX_VIDEO_V2 = "ltx_video_v2"
    LTX_VIDEO_V2_FLF2V = "ltx_video_v2_flf2v"
    PROMPT_OPTIMIZE = "prompt_optimize"
    LTX_T2V = "ltx_t2v"
    LTX_T2V_IC = "ltx_t2v_ic"
    MINIMAX_H3_T2V = "minimax_h3_t2v"
    MINIMAX_H3_I2V = "minimax_h3_i2v"
    MINIMAX_H3_FLF2V = "minimax_h3_flf2v"
    MINIMAX_H3_REF2V = "minimax_h3_ref2v"
    CHARACTER_REFERENCE_BUILD = "character_reference_build"
    WAN22_VIDEO_V2 = "wan22_video_v2"
    SCAIL2_ACTION_TRANSFER = SCAIL2_ACTION_TRANSFER_TASK_TYPE
    SCAIL2_ACTION_TRANSFER_LONG = SCAIL2_ACTION_TRANSFER_LONG_TASK_TYPE
    SCAIL2_VIDEO_REPLACEMENT = SCAIL2_VIDEO_REPLACEMENT_TASK_TYPE
    SCAIL2_FACE_SWAP_V2 = SCAIL2_FACE_SWAP_V2_TASK_TYPE
    PORNMASTER_FLUX2_SINGLE_EDIT = "pornmaster_flux2_single_edit"
    PORNMASTER_FLUX2_MULTI_EDIT = "pornmaster_flux2_multi_edit"
    PORNMASTER_FLUX2_EDIT_BF16 = "pornmaster_flux2_edit_bf16"
    PORNMASTER_FLUX2_MULTI_EDIT_BF16 = "pornmaster_flux2_multi_edit_bf16"


class TaskResponse(BaseModel):
    task_id: str


class T2ITaskResponse(BaseModel):
    task_id: str
    image_url: Optional[str] = None


class Txt2ImgRequest(BaseModel):
    task_id: str
    prompt: str
    priority: int = 0


class PromptOptimizeRequest(BaseModel):
    task_id: str
    profile_ref: str
    template_ref: str
    template_hash: str
    target_task_type: str
    prompt: str
    context: Dict[str, Any]
    media: List[Dict[str, str]]
    trusted_context: Dict[str, Any] = Field(default_factory=dict)
    prompt_config_snapshot: Optional[Dict[str, Any]] = None
    text_stream_contract: Optional[Dict[str, Any]] = None
    priority: int = 0


class TaskStatusResponse(BaseModel):
    status: TaskStatus
    queue_pos: Optional[int] = None
    queue_type_pos: Optional[int] = None
    queue_remaining: Optional[int] = None
    progress: Optional[float] = None
    error: Optional[str] = None
    result_path: Optional[str] = None  # Added for convenience
    image_url: Optional[str] = None
    task_type: Optional[str] = None
    extra_outputs: Optional[Dict[str, Any]] = None
    result_kind: Optional[str] = None
    result_text: Optional[str] = None
    result_meta: Optional[Dict[str, Any]] = None
    result_asset: Optional[Dict[str, Any]] = None
    extra_output_assets: Optional[Dict[str, Any]] = None
    cancel_requested: Optional[bool] = None
    cancel_requested_at: Optional[float] = None
    cancel_locked: Optional[bool] = None
    execution_phase: Optional[str] = None


class WorkerInfo(BaseModel):
    agent_id: str
    types: str
    status: str
    last_seen: float
    health_reason: Optional[str] = None
    last_error: Optional[str] = None
    last_error_at: Optional[float] = None
    consecutive_failures: Optional[int] = None
    quarantined_until: Optional[float] = None
    current_task_id: Optional[str] = None
    current_task_type: Optional[str] = None
    current_task_progress: Optional[float] = None
    current_task_created_at: Optional[float] = None
    node_id: Optional[str] = None
    provider: Optional[str] = None
    gpu_index: Optional[int] = None
    runtime_profile: Optional[str] = None
    image_ref: Optional[str] = None
    model_bundle_versions: Optional[Dict[str, Any]] = None
    pool_managed: Optional[bool] = None
    control_state: Optional[str] = None
    control_reason: Optional[str] = None
    control_updated_at: Optional[float] = None


class SystemWorkersResponse(BaseModel):
    workers: List[WorkerInfo]
    count: int


class SystemStatusResponse(BaseModel):
    queue_size: int
    queue_by_type: dict[str, int] = {}
    queue_by_type_details: dict[str, dict[str, Any]] = {}
    queue_pressure_by_worker_profile: dict[str, dict[str, Any]] = {}
    active_workers: int
    healthy_workers: int = 0
    accepting_workers: int = 0
    error_workers: int = 0
    quarantined_workers: int = 0
    workers_by_status: dict[str, int] = {}
    workers_by_control_state: dict[str, int] = {}
    comfy_online: bool


class Img2ImgRequest(BaseModel):
    task_id: str
    image: Optional[str] = None
    image2: Optional[str] = None
    images: Optional[List[str]] = None
    prompt: str
    negative_prompt: Optional[str] = " "
    num_inference_steps: Optional[int] = 6
    guidance_scale: Optional[float] = 1.0
    seed: Optional[int] = None
    character_view_index: Optional[int] = Field(default=None, ge=1, le=6)
    character_view_type: Optional[str] = None
    priority: int = 0


class Img2ImgLoraRequest(BaseModel):
    task_id: str
    image: Optional[str] = None
    image2: Optional[str] = None
    images: Optional[List[str]] = None
    prompt: str
    negative_prompt: Optional[str] = " "
    num_inference_steps: Optional[int] = 6
    guidance_scale: Optional[float] = 1.0
    seed: Optional[int] = None
    priority: int = 0
    lora_name: Optional[str] = ""
    lora_strength: Optional[float] = 1.0


class FaceSwapRequest(BaseModel):
    task_id: str
    face_image: str
    body_image: str
    priority: int = 0


class VideoInsertRequest(BaseModel):
    task_id: str
    image: str
    prompt: str
    width: int = 512
    height: int = 512
    length: int = 81
    priority: int = 0


class VideoEditRequest(BaseModel):
    task_id: str
    image: str
    prompt: str
    width: int = 512
    height: int = 512
    length: int = 81
    priority: int = 0


class LoraItem(BaseModel):
    name: str
    strength: float


class VideoLoraRequest(BaseModel):
    task_id: str
    image: str
    prompt: str
    lora_name: Optional[str] = ""
    lora_strength: Optional[float] = 1.0
    lora_items: Optional[list[LoraItem]] = Field(default=None, max_length=5)
    end_image: Optional[str] = None
    negative_prompt: Optional[str] = " "
    use_end_frame: bool = False
    resolution_preset: Optional[str] = "preview"
    wan22_model_profile: Optional[str] = ""
    width: int = 512
    height: int = 512
    length: int = 5
    extract_last_frame: bool = True
    priority: int = 0


class FaceVideoRequest(BaseModel):
    task_id: str
    face_image: str
    video: str
    resolution: int = 1024
    duration: int = 121
    priority: int = 0


class I2IProRequest(BaseModel):
    task_id: str
    image: str
    prompt: str
    seed: Optional[int] = None
    priority: int = 0


class I2IDrawRequest(BaseModel):
    task_id: str
    image: str
    prompt: str
    seed: Optional[int] = None
    priority: int = 0


class LtxVideoRequest(BaseModel):
    task_id: str
    image: str
    prompt: str
    negative_prompt: Optional[str] = None
    lora_name: Optional[str] = ""
    lora_strength: Optional[float] = None
    lora_items: Optional[list[LoraItem]] = None
    length: int = 5
    width: int = 704
    height: int = 1280
    priority: int = 0


class LtxVideoFlf2VRequest(LtxVideoRequest):
    end_image: str
    use_end_frame: bool = True
    extract_last_frame: bool = True


class LtxVideoV2VAudioRequest(BaseModel):
    task_id: str
    video: str
    prompt: str
    negative_prompt: Optional[str] = None
    lora_name: Optional[str] = ""
    lora_strength: Optional[float] = None
    lora_items: Optional[list[LoraItem]] = None
    length: int = 5
    width: int = 704
    height: int = 1280
    extract_last_frame: bool = True
    priority: int = 0


class LtxT2VRequest(BaseModel):
    task_id: str
    prompt: str
    negative_prompt: Optional[str] = None
    audio_prompt: Optional[str] = None
    length: int = 5
    width: int = 1280
    height: int = 704
    frame_count: int = 121
    fps: int = 24
    character_sheet: Optional[str] = None
    character_description: Optional[str] = None
    character_sheets: list[str] = Field(default_factory=list, max_length=4)
    character_descriptions: list[str] = Field(default_factory=list, max_length=4)
    background_image: Optional[str] = None
    sulphur_strength: Optional[float] = Field(default=None, ge=0, le=1)
    seed: Optional[int] = Field(default=None, ge=0, le=18446744073709551615)
    priority: int = 0


class MiniMaxH3Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    prompt: str
    images: list[str] = Field(default_factory=list, max_length=4)
    reference_descriptions: list[str] = Field(default_factory=list, max_length=4)
    duration: int = Field(default=5)
    resolution_preset: str = "preview"
    aspect_ratio: str = "16:9"
    # Source-ratio I2V/FLF2V requests use the workflow calculator, represented
    # by zero here; fixed-aspect T2V/REF2V continue to send concrete Div32 sizes.
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    frame_count: int = Field(ge=5)
    fps: int = Field(default=24)
    seed: Optional[int] = Field(default=None, ge=0, le=MINIMAX_H3_MAX_SEED)
    lora_name: Optional[str] = ""
    lora_strength: Optional[float] = None
    lora_items: Optional[list[LoraItem]] = Field(default=None, max_length=6)
    extract_last_frame: bool = True
    priority: int = 0


class Wan22VideoV2Request(BaseModel):
    task_id: str
    image: str
    prompt: str
    lora_name: Optional[str] = ""
    lora_strength: Optional[float] = 1.0
    lora_items: Optional[list[LoraItem]] = Field(default=None, max_length=5)
    end_image: Optional[str] = None
    negative_prompt: Optional[str] = " "
    use_end_frame: bool = False
    resolution_preset: Optional[str] = "standard"
    wan22_model_profile: Optional[str] = ""
    upscale: bool = False
    extract_last_frame: bool = True
    length: int = 5
    priority: int = 0


class _Scail2VideoRequestBase(BaseModel):
    task_id: str
    image: str
    video: str
    prompt: str
    negative_prompt: Optional[str] = " "
    length: int = 5
    priority: int = 0


class Scail2VideoRequest(_Scail2VideoRequestBase):
    @field_validator("length")
    @classmethod
    def validate_length(cls, value: int) -> int:
        try:
            return normalize_scail2_duration_seconds(value, strict=True)
        except Scail2DurationError as exc:
            raise ValueError("SCAIL-2 only supports 5s or 8s duration.") from exc


class Scail2FaceSwapRequest(Scail2VideoRequest):
    reference_preprocessed: bool

    @field_validator("reference_preprocessed")
    @classmethod
    def validate_reference_preprocessed(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError(
                "SCAIL-2 face swap requires a preprocessed reference frame."
            )
        return value


class Scail2ActionTransferLongRequest(_Scail2VideoRequestBase):
    @field_validator("length")
    @classmethod
    def validate_length(cls, value: int) -> int:
        try:
            return normalize_scail2_duration_seconds(
                value,
                strict=True,
                task_type=SCAIL2_ACTION_TRANSFER_LONG_TASK_TYPE,
            )
        except Scail2DurationError as exc:
            raise ValueError(
                "SCAIL-2 long action transfer only supports 10s, 15s or 20s duration."
            ) from exc
