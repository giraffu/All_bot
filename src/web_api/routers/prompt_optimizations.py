import os

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.task_core import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
    QueueCapacityError,
)
from src.database.models import User
from src.quota import QuotaManager
from src.web_api.dependencies import get_current_user
from src.web_api.schemas.prompt_optimization_schema import (
    PromptOptimizationTaskRequest,
    PromptOptimizationTaskResponse,
)
from src.web_api.services.prompt_optimization_service import (
    build_prompt_capability_payload,
    submit_prompt_optimization,
)

router = APIRouter()
quota_manager = QuotaManager()
_ENABLED_VALUES = {"1", "true", "yes", "on"}


def _require_enabled(target_task_type: str) -> None:
    flag = (
        "LTX_T2V_BACKEND_ENABLED"
        if target_task_type in {"ltx_t2v", "ltx_t2v_ic"}
        else "ENABLE_LTX_VIDEO_V2"
    )
    if os.getenv(flag, "false").strip().lower() not in _ENABLED_VALUES:
        raise HTTPException(status_code=404, detail="Not found")
    if (
        target_task_type == "ltx_t2v_ic"
        and os.getenv("LTX_T2V_MSR_ENABLED", "false").strip().lower()
        not in _ENABLED_VALUES
    ):
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/capabilities")
async def get_capabilities(
    target_task_type: str = Query(...),
    _current_user: User = Depends(get_current_user),
):
    _require_enabled(target_task_type)
    try:
        return build_prompt_capability_payload(target_task_type)
    except CoreDomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks", response_model=PromptOptimizationTaskResponse)
async def create_prompt_optimization_task(
    request: PromptOptimizationTaskRequest,
    current_user: User = Depends(get_current_user),
):
    _require_enabled(request.target_task_type)
    try:
        return await submit_prompt_optimization(
            request=request,
            current_user=current_user,
            get_balance=quota_manager.get_credits,
        )
    except QueueCapacityError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ConcurrencyLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except CoreDomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
