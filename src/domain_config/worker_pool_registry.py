from __future__ import annotations

from dataclasses import dataclass

from src.core.task_execution_types import resolve_worker_execution_task_type


@dataclass(frozen=True)
class WorkerPoolProfile:
    name: str
    supported_task_types: tuple[str, ...]


_WORKER_POOL_PROFILES = (
    WorkerPoolProfile("img2img", ("img2img", "img2img_lora")),
    WorkerPoolProfile("image_to_video", ("image_to_video",)),
    WorkerPoolProfile("wan22_video_v2", ("wan22_video_v2",)),
    WorkerPoolProfile(
        "i2i_pro",
        ("i2i_pro", "t2i-pornmaster-turbo", "face_swap_v2", "face_swap"),
    ),
    WorkerPoolProfile(
        "scail2",
        (
            "scail2_action_transfer",
            "scail2_action_transfer_long",
            "scail2_video_replacement",
            "scail2_face_swap_v2",
        ),
    ),
    WorkerPoolProfile(
        "ltx_video",
        ("ltx_video", "ltx_video_flf2v", "ltx_video_v2v_audio"),
    ),
    WorkerPoolProfile("ltx_t2v", ("ltx_t2v", "ltx_t2v_ic")),
    WorkerPoolProfile(
        "pornmaster_flux2_edit_bf16",
        ("pornmaster_flux2_edit_bf16", "pornmaster_flux2_multi_edit_bf16"),
    ),
)

_WORKER_POOL_BY_TASK_TYPE = {
    task_type: profile
    for profile in _WORKER_POOL_PROFILES
    for task_type in profile.supported_task_types
}


def iter_worker_pool_profiles() -> tuple[WorkerPoolProfile, ...]:
    return _WORKER_POOL_PROFILES


def get_worker_pool_profile(task_type: str | None) -> WorkerPoolProfile | None:
    execution_type = resolve_worker_execution_task_type(task_type)
    return _WORKER_POOL_BY_TASK_TYPE.get(execution_type)


__all__ = [
    "WorkerPoolProfile",
    "get_worker_pool_profile",
    "iter_worker_pool_profiles",
]
