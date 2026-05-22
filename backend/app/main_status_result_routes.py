TASK_STATUS_ROUTE_SPECS = (
    ("/api/v1/tasks/{task_id}", True, False, "get_task_status_v1"),
    ("/status/{task_id}", False, True, "get_task_status"),
)

TASK_RESULT_ROUTE_SPECS = (
    ("/image/{task_id}", "Image not ready", "get_task_image"),
    ("/video/{task_id}", "Video not ready", "get_task_video"),
)


def register_task_status_route(
    *,
    app,
    path: str,
    include_image_url: bool,
    include_task_type: bool,
    handler_name: str,
    task_status_response_model,
    queue_manager_dep,
    build_task_status_response_func,
) -> None:
    async def endpoint(task_id: str, queue_manager: queue_manager_dep):
        return await build_task_status_response_func(
            task_id=task_id,
            queue_manager=queue_manager,
            include_image_url=include_image_url,
            include_task_type=include_task_type,
        )

    endpoint.__name__ = handler_name
    app.get(path, response_model=task_status_response_model)(endpoint)


def register_task_result_route(
    *,
    app,
    path: str,
    ready_error_detail: str,
    handler_name: str,
    queue_manager_dep,
    minio_client_dep,
    serve_task_result_file_func,
) -> None:
    async def endpoint(
        task_id: str,
        queue_manager: queue_manager_dep,
        minio_client: minio_client_dep,
    ):
        return await serve_task_result_file_func(
            task_id=task_id,
            ready_error_detail=ready_error_detail,
            queue_manager=queue_manager,
            minio_client=minio_client,
        )

    endpoint.__name__ = handler_name
    app.get(path)(endpoint)


def register_task_status_routes(
    *,
    app,
    task_status_response_model,
    queue_manager_dep,
    build_task_status_response_func,
) -> None:
    for path, include_image_url, include_task_type, handler_name in TASK_STATUS_ROUTE_SPECS:
        register_task_status_route(
            app=app,
            path=path,
            include_image_url=include_image_url,
            include_task_type=include_task_type,
            handler_name=handler_name,
            task_status_response_model=task_status_response_model,
            queue_manager_dep=queue_manager_dep,
            build_task_status_response_func=build_task_status_response_func,
        )


def register_task_result_routes(
    *,
    app,
    queue_manager_dep,
    minio_client_dep,
    serve_task_result_file_func,
) -> None:
    for path, ready_error_detail, handler_name in TASK_RESULT_ROUTE_SPECS:
        register_task_result_route(
            app=app,
            path=path,
            ready_error_detail=ready_error_detail,
            handler_name=handler_name,
            queue_manager_dep=queue_manager_dep,
            minio_client_dep=minio_client_dep,
            serve_task_result_file_func=serve_task_result_file_func,
        )
