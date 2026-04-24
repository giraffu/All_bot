from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.services.prompt_optimizer_service import PromptOptimizerService

router = APIRouter()

class OptimizeRequest(BaseModel):
    prompt: str
    image_base64: str

@router.post("/optimize-prompt")
async def api_optimize_prompt(request: OptimizeRequest):
    try:
        optimized = await PromptOptimizerService.optimize_video_prompt(
            request.prompt, request.image_base64
        )
        return {"optimized_prompt": optimized}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
