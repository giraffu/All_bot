from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class TaskGenerateRequest(BaseModel):
    task_type: str = Field(..., description="The type of the task: face_swap, face_video, txt2img, etc.")
    inputs: Dict[str, Any] = Field(..., description="Input parameters including object keys for images/videos")
    prompt: Optional[str] = Field("", description="Positive prompt")
    negative_prompt: Optional[str] = Field("", description="Negative prompt")
    priority: int = Field(0, description="Task priority (0=normal, higher=faster)")
    is_template: bool = Field(False, description="If this task is generated from a gallery template")
    source_post_id: Optional[int] = Field(None, description="The ID of the gallery post being applied")
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_type": "face_swap",
                "inputs": {
                    "face_image": "bot-data/web_uploads/...",
                    "target_image": "bot-data/web_uploads/..."
                }
            }
        }

class TaskGenerateResponse(BaseModel):
    task_id: str
    status: str
    message: str
    cost: int
    balance_remaining: int
