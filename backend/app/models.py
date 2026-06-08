from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


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
    VIDEO_INSERT = "video_insert"
    VIDEO_EDIT = "video_edit"
    IMAGE_TO_VIDEO = "image_to_video"
    FACE_VIDEO = "face_video"
    T2I_PORNMASTER_TURBO = "t2i-pornmaster-turbo"
    I2I_PRO = "i2i_pro"
    I2I_DRAW = "i2i_draw"
    LTX_VIDEO = "ltx_video"
    WAN22_VIDEO_V2 = "wan22_video_v2"


class TaskResponse(BaseModel):
    task_id: str


class T2ITaskResponse(BaseModel):
    task_id: str
    image_url: Optional[str] = None


class Txt2ImgRequest(BaseModel):
    task_id: str
    prompt: str
    priority: int = 0


class TaskStatusResponse(BaseModel):
    status: TaskStatus
    queue_pos: Optional[int] = None
    queue_remaining: Optional[int] = None
    progress: Optional[float] = None
    error: Optional[str] = None
    result_path: Optional[str] = None  # Added for convenience
    image_url: Optional[str] = None
    task_type: Optional[str] = None
    extra_outputs: Optional[Dict[str, Any]] = None
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


class SystemWorkersResponse(BaseModel):
    workers: List[WorkerInfo]
    count: int


class SystemStatusResponse(BaseModel):
    queue_size: int
    queue_by_type: dict[str, int] = {}
    active_workers: int
    healthy_workers: int = 0
    error_workers: int = 0
    quarantined_workers: int = 0
    workers_by_status: dict[str, int] = {}
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


class VideoLoraRequest(BaseModel):
    task_id: str
    image: str
    prompt: str
    lora_name: Optional[str] = ""
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


class LoraItem(BaseModel):
    name: str
    strength: float


class LtxVideoRequest(BaseModel):
    task_id: str
    image: str
    prompt: str
    lora_name: Optional[str] = ""
    lora_strength: Optional[float] = None
    lora_items: Optional[list[LoraItem]] = None
    length: int = 5
    width: int = 704
    height: int = 1280
    priority: int = 0


class Wan22VideoV2Request(BaseModel):
    task_id: str
    image: str
    prompt: str
    end_image: Optional[str] = None
    negative_prompt: Optional[str] = " "
    use_end_frame: bool = False
    resolution_preset: Optional[str] = "standard"
    wan22_model_profile: Optional[str] = ""
    upscale: bool = False
    extract_last_frame: bool = True
    length: int = 5
    priority: int = 0
