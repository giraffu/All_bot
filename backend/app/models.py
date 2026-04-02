from pydantic import BaseModel, Field
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
    T2I_PORNMASTER_TURBO = "t2i-pornmaster-turbo"

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
