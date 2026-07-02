from fastapi import APIRouter

from dashboard.backend.schemas import (
    RunPodAutoscalerControlRequest,
    RunPodAutoscalerSettingsRequest,
    RunPodScaleRequest,
    RunPodWorkerActionRequest,
)
from dashboard.backend.services.runpod_autoscaler_service import (
    get_runpod_autoscaler_payload,
    set_runpod_autoscaler_control_payload,
    set_runpod_autoscaler_settings_payload,
)
from dashboard.backend.services.runpod_admin_service import (
    delete_runpod_worker_payload,
    enable_lan_aio_worker_payload,
    enable_runpod_worker_payload,
    get_locked_runpod_workers_payload,
    get_runpod_operations_payload,
    get_runpod_profiles_payload,
    lock_runpod_worker_payload,
    pause_lan_aio_worker_payload,
    pause_runpod_worker_payload,
    restart_lan_aio_worker_payload,
    restart_runpod_worker_payload,
    start_runpod_scale_payload,
    terminate_runpod_operation_payload,
    unlock_runpod_worker_payload,
)

router = APIRouter(prefix="/api/runpod", tags=["runpod"])


@router.get("/profiles")
async def get_runpod_profiles():
    return await get_runpod_profiles_payload()


@router.get("/operations")
async def get_runpod_operations():
    return await get_runpod_operations_payload()


@router.get("/workers/locks")
async def get_locked_runpod_workers():
    return await get_locked_runpod_workers_payload()


@router.get("/autoscaler")
async def get_runpod_autoscaler():
    return await get_runpod_autoscaler_payload()


@router.post("/autoscaler/control")
async def control_runpod_autoscaler(req: RunPodAutoscalerControlRequest):
    return await set_runpod_autoscaler_control_payload(
        enabled=req.enabled,
        reason=req.reason,
    )


@router.post("/autoscaler/settings")
async def update_runpod_autoscaler_settings(req: RunPodAutoscalerSettingsRequest):
    return await set_runpod_autoscaler_settings_payload(
        scale_up_wait_minutes_by_profile=req.scale_up_wait_minutes_by_profile,
        task_duration_seconds_by_type=req.task_duration_seconds_by_type,
        profile_autoscaler_paused_by_profile=(
            req.profile_autoscaler_paused_by_profile
        ),
        reason=req.reason,
    )


@router.post("/operations/{operation_id}/terminate")
async def terminate_runpod_operation(operation_id: str):
    return await terminate_runpod_operation_payload(operation_id)


@router.post("/scale")
async def start_runpod_scale(req: RunPodScaleRequest):
    return await start_runpod_scale_payload(req)


@router.post("/workers/{agent_id}/pause")
async def pause_runpod_worker(agent_id: str, req: RunPodWorkerActionRequest):
    return await pause_runpod_worker_payload(agent_id=agent_id, request=req)


@router.post("/workers/{agent_id}/enable")
async def enable_runpod_worker(agent_id: str, req: RunPodWorkerActionRequest):
    return await enable_runpod_worker_payload(agent_id=agent_id, request=req)


@router.post("/workers/{agent_id}/restart")
async def restart_runpod_worker(agent_id: str, req: RunPodWorkerActionRequest):
    return await restart_runpod_worker_payload(agent_id=agent_id, request=req)


@router.post("/workers/{agent_id}/lock")
async def lock_runpod_worker(agent_id: str, req: RunPodWorkerActionRequest):
    return await lock_runpod_worker_payload(agent_id=agent_id, request=req)


@router.post("/workers/{agent_id}/unlock")
async def unlock_runpod_worker(agent_id: str, req: RunPodWorkerActionRequest):
    return await unlock_runpod_worker_payload(agent_id=agent_id, request=req)


@router.delete("/workers/{agent_id}")
async def delete_runpod_worker(agent_id: str, req: RunPodWorkerActionRequest):
    return await delete_runpod_worker_payload(agent_id=agent_id, request=req)


@router.post("/lan-aio/workers/{agent_id}/pause")
async def pause_lan_aio_worker(agent_id: str, req: RunPodWorkerActionRequest):
    return await pause_lan_aio_worker_payload(agent_id=agent_id, request=req)


@router.post("/lan-aio/workers/{agent_id}/enable")
async def enable_lan_aio_worker(agent_id: str, req: RunPodWorkerActionRequest):
    return await enable_lan_aio_worker_payload(agent_id=agent_id, request=req)


@router.post("/lan-aio/workers/{agent_id}/restart")
async def restart_lan_aio_worker(agent_id: str, req: RunPodWorkerActionRequest):
    return await restart_lan_aio_worker_payload(agent_id=agent_id, request=req)
