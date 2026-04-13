from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class TaskGenerateRequest(BaseModel):
    task_type: str = Field(..., description="The type of the task: face_swap, face_video, txt2img, etc.")
    inputs: Dict[str, Any] = Field(..., description="Input parameters including object keys for images/videos")
    prompt: Optional[str] = Field("", description="Positive prompt")
    negative_prompt: Optional[str] = Field("", description="Negative prompt")
    priority: int = Field(0, description="Task priority (0=normal, higher=faster)")
    
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
