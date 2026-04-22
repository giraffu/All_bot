from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"

class TaskType(str, Enum):
    IMG2IMG = "img2img"
    FACE_SWAP = "face_swap"
    VIDEO_INSERT = "video_insert"
    VIDEO_EDIT = "video_edit"
    FACE_VIDEO = "face_video"
    T2I_PORNMASTER_TURBO = "t2i-pornmaster-turbo"
    I2I_PRO = "i2i_pro"
    LTX_VIDEO = "ltx_video"

class TaskResponse(BaseModel):
    task_id: str

class T2ITaskResponse(BaseModel):
    task_id: str
    image_url: Optional[str] = None

class TaskStatusResponse(BaseModel):
    status: TaskStatus
    queue_pos: Optional[int] = None
    queue_remaining: Optional[int] = None
    progress: Optional[float] = None
    error: Optional[str] = None
    result_path: Optional[str] = None # Added for convenience
    image_url: Optional[str] = None

class WorkerInfo(BaseModel):
    agent_id: str
    types: str
    status: str
    last_seen: float
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
    comfy_online: bool

class Img2ImgRequest(BaseModel):
    image: Optional[str] = None
    image2: Optional[str] = None
    images: Optional[List[str]] = None
    prompt: str
    negative_prompt: Optional[str] = " "
    num_inference_steps: Optional[int] = 6
    guidance_scale: Optional[float] = 1.0
    seed: Optional[int] = None
    priority: int = 0

class FaceSwapRequest(BaseModel):
    face_image: str
    body_image: str
    priority: int = 0

class VideoInsertRequest(BaseModel):
    image: str
    prompt: str
    width: int = 512
    height: int = 512
    length: int = 81
    priority: int = 0

class VideoEditRequest(BaseModel):
    image: str
    prompt: str
    width: int = 512
    height: int = 512
    length: int = 81
    priority: int = 0

class VideoLoraRequest(BaseModel):
    image: str
    prompt: str
    lora_name: str
    width: int = 512
    height: int = 512
    length: int = 81
    priority: int = 0

class FaceVideoRequest(BaseModel):
    face_image: str
    video: str
    resolution: int = 1024
    duration: int = 121
    priority: int = 0

class I2IProRequest(BaseModel):
    image: str
    prompt: str
    seed: Optional[int] = None
    priority: int = 0

class LtxVideoRequest(BaseModel):
    image: str
    prompt: str
    length: int = 5
    width: int = 704
    height: int = 1280
    priority: int = 0