from fastapi import APIRouter

from dashboard.backend.schemas import RunPodScaleRequest, RunPodWorkerActionRequest
from dashboard.backend.services.runpod_admin_service import (
    delete_runpod_worker_payload,
    enable_lan_aio_worker_payload,
    enable_runpod_worker_payload,
    get_runpod_operations_payload,
    get_runpod_profiles_payload,
    pause_lan_aio_worker_payload,
    pause_runpod_worker_payload,
    restart_lan_aio_worker_payload,
    restart_runpod_worker_payload,
    start_runpod_scale_payload,
    terminate_runpod_operation_payload,
)

router = APIRouter(prefix="/api/runpod", tags=["runpod"])


@router.get("/profiles")
async def get_runpod_profiles():
    return await get_runpod_profiles_payload()


@router.get("/operations")
async def get_runpod_operations():
    return await get_runpod_operations_payload()


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
