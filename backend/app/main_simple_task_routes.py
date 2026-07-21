from app.models import (
    FaceSwapRequest,
    FaceVideoRequest,
    I2IDrawRequest,
    I2IProRequest,
    Img2ImgLoraRequest,
    Img2ImgRequest,
    LtxVideoFlf2VRequest,
    LtxVideoRequest,
    LtxVideoV2VAudioRequest,
    LtxT2VRequest,
    Scail2ActionTransferLongRequest,
    Scail2VideoRequest,
    TaskResponse,
    TaskType,
    Txt2ImgRequest,
    VideoEditRequest,
    VideoInsertRequest,
    VideoLoraRequest,
    Wan22VideoV2Request,
)
from app.queue_manager import TaskAdmissionConflictError
from fastapi import HTTPException

from src.domain_config.task_type_registry import get_central_task_type

SIMPLE_TASK_KEYS = (
    "img2img",
    "img2img_lora",
    "face_swap",
    "face_swap_v2",
    "video_insert",
    "video_edit",
    "image_to_video",
    "video_lora",
    "face_video",
    "i2i_pro",
    "i2i_draw",
    "txt2img",
    "ltx_video",
    "ltx_video_flf2v",
    "ltx_video_v2v_audio",
    "ltx_t2v",
    "ltx_t2v_ic",
    "character_reference_build",
    "wan22_video_v2",
    "scail2_action_transfer",
    "scail2_action_transfer_long",
    "scail2_video_replacement",
    "scail2_face_swap_v2",
    "pornmaster_flux2_single_edit",
    "pornmaster_flux2_multi_edit",
    "pornmaster_flux2_edit_bf16",
    "pornmaster_flux2_multi_edit_bf16",
)


def _resolve_simple_task_type(task_key: str) -> TaskType:
    central_task_type = get_central_task_type(task_key)
    if central_task_type is None:
        raise RuntimeError(f"missing central task type registry entry for {task_key}")
    return TaskType(central_task_type)


SIMPLE_TASK_TYPE_MAP = {
    task_key: _resolve_simple_task_type(task_key)
    for task_key in SIMPLE_TASK_KEYS
}

LEGACY_WAN22_SIMPLE_TASK_KEYS = {"video_insert", "video_edit"}
LEGACY_WAN22_MODEL_PROFILE = "legacy_image_to_video"


class _NormalizedSimpleTaskRequest:
    def __init__(self, payload):
        self._payload = payload

    def dict(self):
        return dict(self._payload)


def _request_model_to_dict(request_model):
    if hasattr(request_model, "model_dump"):
        return request_model.model_dump()
    if hasattr(request_model, "dict"):
        return request_model.dict()
    return dict(request_model)


def _legacy_video_length_to_duration_seconds(length) -> int:
    try:
        value = int(length)
    except (TypeError, ValueError):
        return 5
    if value >= 161:
        return 10
    if value >= 129:
        return 8
    if value >= 80:
        return 5
    if value >= 10:
        return 10
    if value >= 8:
        return 8
    return 5


def _legacy_video_resolution_preset(width, height) -> str:
    try:
        max_dimension = max(int(width or 0), int(height or 0))
    except (TypeError, ValueError):
        max_dimension = 0
    if max_dimension >= 1024:
        return "hd"
    if max_dimension >= 720:
        return "standard"
    if max_dimension >= 600:
        return "small"
    return "preview"


def normalize_simple_task_request_model(task_key: str, request_model):
    if task_key not in LEGACY_WAN22_SIMPLE_TASK_KEYS:
        return request_model

    payload = _request_model_to_dict(request_model)
    payload["length"] = _legacy_video_length_to_duration_seconds(
        payload.get("length")
    )
    payload["resolution_preset"] = payload.get(
        "resolution_preset"
    ) or _legacy_video_resolution_preset(payload.get("width"), payload.get("height"))
    payload.pop("width", None)
    payload.pop("height", None)
    payload.setdefault("negative_prompt", " ")
    payload.setdefault("lora_name", "")
    payload.setdefault("use_end_frame", False)
    payload.setdefault("wan22_model_profile", LEGACY_WAN22_MODEL_PROFILE)
    payload.setdefault("extract_last_frame", True)
    return _NormalizedSimpleTaskRequest(payload)

SIMPLE_TASK_ROUTE_SPECS = (
    ("/comfy_img2img", Img2ImgRequest, "img2img", "create_img2img_task"),
    (
        "/comfy_img2img_lora",
        Img2ImgLoraRequest,
        "img2img_lora",
        "create_img2img_lora_task",
    ),
    ("/face_swap", FaceSwapRequest, "face_swap", "create_face_swap_task"),
    (
        "/face_swap_v2",
        FaceSwapRequest,
        "face_swap_v2",
        "create_face_swap_v2_task",
    ),
    (
        "/perfect_video_insert",
        VideoInsertRequest,
        "video_insert",
        "create_video_insert_task",
    ),
    (
        "/perfect_video_edit",
        VideoEditRequest,
        "video_edit",
        "create_video_edit_task",
    ),
    (
        "/image_to_video",
        VideoLoraRequest,
        "image_to_video",
        "create_image_to_video_task",
    ),
    (
        "/perfect_video_lora",
        VideoLoraRequest,
        "video_lora",
        "create_video_lora_task",
    ),
    ("/face_video", FaceVideoRequest, "face_video", "create_face_video_task"),
    ("/i2i_pro", I2IProRequest, "i2i_pro", "create_i2i_pro_task"),
    ("/i2i_draw", I2IDrawRequest, "i2i_draw", "create_i2i_draw_task"),
    ("/txt2img", Txt2ImgRequest, "txt2img", "create_txt2img_task"),
    ("/api/v1/ltx_video", LtxVideoRequest, "ltx_video", "create_ltx_video_task"),
    (
        "/api/v1/ltx_video_flf2v",
        LtxVideoFlf2VRequest,
        "ltx_video_flf2v",
        "create_ltx_video_flf2v_task",
    ),
    (
        "/api/v1/ltx_video_v2v_audio",
        LtxVideoV2VAudioRequest,
        "ltx_video_v2v_audio",
        "create_ltx_video_v2v_audio_task",
    ),
    ("/api/v1/ltx_t2v", LtxT2VRequest, "ltx_t2v", "create_ltx_t2v_task"),
    ("/api/v1/ltx_t2v_ic", LtxT2VRequest, "ltx_t2v_ic", "create_ltx_t2v_ic_task"),
    (
        "/api/v1/character_reference_build",
        Img2ImgRequest,
        "character_reference_build",
        "create_character_reference_build_task",
    ),
    (
        "/api/v1/wan22_video_v2",
        Wan22VideoV2Request,
        "wan22_video_v2",
        "create_wan22_video_v2_task",
    ),
    (
        "/api/v1/scail2_action_transfer",
        Scail2VideoRequest,
        "scail2_action_transfer",
        "create_scail2_action_transfer_task",
    ),
    (
        "/api/v1/scail2_action_transfer_long",
        Scail2ActionTransferLongRequest,
        "scail2_action_transfer_long",
        "create_scail2_action_transfer_long_task",
    ),
    (
        "/api/v1/scail2_video_replacement",
        Scail2VideoRequest,
        "scail2_video_replacement",
        "create_scail2_video_replacement_task",
    ),
    (
        "/api/v1/scail2_face_swap_v2",
        Scail2VideoRequest,
        "scail2_face_swap_v2",
        "create_scail2_face_swap_v2_task",
    ),
    (
        "/api/v1/pornmaster_flux2_single_edit",
        Img2ImgRequest,
        "pornmaster_flux2_single_edit",
        "create_pornmaster_flux2_single_edit_task",
    ),
    (
        "/api/v1/pornmaster_flux2_multi_edit",
        Img2ImgRequest,
        "pornmaster_flux2_multi_edit",
        "create_pornmaster_flux2_multi_edit_task",
    ),
    (
        "/api/v1/pornmaster_flux2_edit_bf16",
        Img2ImgRequest,
        "pornmaster_flux2_edit_bf16",
        "create_pornmaster_flux2_edit_bf16_task",
    ),
    (
        "/api/v1/pornmaster_flux2_multi_edit_bf16",
        Img2ImgRequest,
        "pornmaster_flux2_multi_edit_bf16",
        "create_pornmaster_flux2_multi_edit_bf16_task",
    ),
)


def split_task_request(request_model):
    params = request_model.dict()
    task_id = params.pop("task_id")
    priority = params.pop("priority", 0)
    return task_id, priority, params


async def enqueue_task_from_request(
    *,
    request_model,
    task_type: TaskType,
    queue_manager,
) -> TaskResponse:
    task_id, priority, params = split_task_request(request_model)
    try:
        await queue_manager.enqueue_task(task_type, params, priority, task_id)
    except TaskAdmissionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TaskResponse(task_id=task_id)


async def enqueue_configured_task(
    *,
    request_model,
    task_key: str,
    queue_manager,
    enqueue_task_from_request_func=None,
) -> TaskResponse:
    enqueue_task_from_request_func = (
        enqueue_task_from_request_func or enqueue_task_from_request
    )
    return await enqueue_task_from_request_func(
        request_model=normalize_simple_task_request_model(task_key, request_model),
        task_type=SIMPLE_TASK_TYPE_MAP[task_key],
        queue_manager=queue_manager,
    )


def register_simple_task_route(
    *,
    app,
    path: str,
    request_model_cls,
    task_key: str,
    handler_name: str,
    task_response_model,
    queue_manager_dep,
    auth_token_dep,
    enqueue_configured_task_func,
) -> None:
    async def endpoint(
        request: request_model_cls,
        queue_manager: queue_manager_dep,
        _token: auth_token_dep,
    ):
        return await enqueue_configured_task_func(
            request_model=request,
            task_key=task_key,
            queue_manager=queue_manager,
        )

    endpoint.__name__ = handler_name
    app.post(path, response_model=task_response_model)(endpoint)


def register_simple_task_routes(
    *,
    app,
    task_response_model,
    queue_manager_dep,
    auth_token_dep,
    enqueue_configured_task_func,
) -> None:
    for path, request_model_cls, task_key, handler_name in SIMPLE_TASK_ROUTE_SPECS:
        register_simple_task_route(
            app=app,
            path=path,
            request_model_cls=request_model_cls,
            task_key=task_key,
            handler_name=handler_name,
            task_response_model=task_response_model,
            queue_manager_dep=queue_manager_dep,
            auth_token_dep=auth_token_dep,
            enqueue_configured_task_func=enqueue_configured_task_func,
        )
