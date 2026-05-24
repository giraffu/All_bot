from app.models import (
    FaceSwapRequest,
    FaceVideoRequest,
    I2IProRequest,
    I2IDrawRequest,
    Img2ImgLoraRequest,
    Img2ImgRequest,
    LtxVideoRequest,
    TaskResponse,
    TaskType,
    VideoEditRequest,
    VideoInsertRequest,
    VideoLoraRequest,
)

SIMPLE_TASK_TYPE_MAP = {
    "img2img": TaskType.IMG2IMG,
    "img2img_lora": TaskType.IMG2IMG_LORA,
    "face_swap": TaskType.FACE_SWAP,
    "video_insert": TaskType.VIDEO_INSERT,
    "video_edit": TaskType.VIDEO_EDIT,
    "video_lora": TaskType.VIDEO_EDIT,
    "face_video": TaskType.FACE_VIDEO,
    "i2i_pro": TaskType.I2I_PRO,
    "i2i_draw": TaskType.I2I_DRAW,
    "ltx_video": TaskType.LTX_VIDEO,
}

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
        "/perfect_video_lora",
        VideoLoraRequest,
        "video_lora",
        "create_video_lora_task",
    ),
    ("/face_video", FaceVideoRequest, "face_video", "create_face_video_task"),
    ("/i2i_pro", I2IProRequest, "i2i_pro", "create_i2i_pro_task"),
    ("/i2i_draw", I2IDrawRequest, "i2i_draw", "create_i2i_draw_task"),
    ("/api/v1/ltx_video", LtxVideoRequest, "ltx_video", "create_ltx_video_task"),
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
    await queue_manager.enqueue_task(task_type, params, priority, task_id)
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
        request_model=request_model,
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
