from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class TaskCoreServiceProviders:
    get_image_service: Callable[[], Any]
    get_storage_service: Callable[[], Any]
    get_task_registry: Callable[[], Any]
    get_permission_service: Callable[[], Any]
    get_submission_outbox: Callable[[], Any]
    get_api_client: Callable[[], Any]


@dataclass(frozen=True)
class TaskCoreStorageCapabilities:
    copy_to_r2_func: Any
    prune_user_web_history_r2_cache_func: Any


@dataclass(frozen=True)
class TaskCoreTaskRegistryCapabilities:
    add_task_func: Any
    update_backend_task_id_func: Any
    mark_task_status_func: Any
    remove_task_func: Any


@dataclass(frozen=True)
class TaskCorePermissionCapabilities:
    refresh_user_group_func: Any


@dataclass(frozen=True)
class TaskCoreSubmissionOutboxCapabilities:
    add_pending_refund_func: Any


@dataclass(frozen=True)
class TaskCoreImageCapabilities:
    download_result_func: Any
    download_video_result_func: Any
    monitor_progress_func: Any


@dataclass(frozen=True)
class TaskCoreRuntimeCapabilities:
    get_active_tasks_func: Any
    get_all_user_concurrencies_func: Any
    cancel_task_func: Any
    get_task_func: Any
    find_task_by_backend_task_id_func: Any
    set_runtime_value_func: Any
    expire_runtime_value_func: Any
    delete_runtime_value_func: Any


_configured_task_core_service_providers: TaskCoreServiceProviders | None = None


def _missing_provider(name: str) -> Callable[[], Any]:
    def _raise_missing_provider() -> Any:
        raise RuntimeError(
            f"Task core service provider '{name}' 未注册，请先调用 configure_task_core_service_providers(...)。"
        )

    return _raise_missing_provider


def get_placeholder_task_core_service_providers() -> TaskCoreServiceProviders:
    return TaskCoreServiceProviders(
        get_image_service=_missing_provider("image_service"),
        get_storage_service=_missing_provider("storage"),
        get_task_registry=_missing_provider("TaskRegistry"),
        get_permission_service=_missing_provider("permission_service"),
        get_submission_outbox=_missing_provider("redis_client"),
        get_api_client=_missing_provider("api_client"),
    )


def configure_task_core_service_providers(
    providers: TaskCoreServiceProviders,
) -> TaskCoreServiceProviders:
    global _configured_task_core_service_providers
    _configured_task_core_service_providers = providers
    return providers


def get_configured_task_core_service_providers() -> TaskCoreServiceProviders | None:
    return _configured_task_core_service_providers


def build_task_core_service_providers(
    *,
    get_image_service: Callable[[], Any] | None = None,
    get_storage_service: Callable[[], Any] | None = None,
    get_task_registry: Callable[[], Any] | None = None,
    get_permission_service: Callable[[], Any] | None = None,
    get_submission_outbox: Callable[[], Any] | None = None,
    get_api_client: Callable[[], Any] | None = None,
) -> TaskCoreServiceProviders:
    default_providers = (
        get_configured_task_core_service_providers()
        or get_placeholder_task_core_service_providers()
    )
    return TaskCoreServiceProviders(
        get_image_service=get_image_service or default_providers.get_image_service,
        get_storage_service=get_storage_service or default_providers.get_storage_service,
        get_task_registry=get_task_registry or default_providers.get_task_registry,
        get_permission_service=(
            get_permission_service or default_providers.get_permission_service
        ),
        get_submission_outbox=(
            get_submission_outbox or default_providers.get_submission_outbox
        ),
        get_api_client=get_api_client or default_providers.get_api_client,
    )


def get_task_core_image_service() -> Any:
    return build_task_core_service_providers().get_image_service()


def get_task_core_storage_service() -> Any:
    return build_task_core_service_providers().get_storage_service()


def get_task_core_task_registry() -> Any:
    return build_task_core_service_providers().get_task_registry()


def get_task_core_permission_service() -> Any:
    return build_task_core_service_providers().get_permission_service()


def get_task_core_submission_outbox() -> Any:
    return build_task_core_service_providers().get_submission_outbox()


def get_task_core_api_client() -> Any:
    return build_task_core_service_providers().get_api_client()


def build_task_core_storage_capabilities() -> TaskCoreStorageCapabilities:
    storage_service = get_task_core_storage_service()
    return TaskCoreStorageCapabilities(
        copy_to_r2_func=storage_service.async_copy_to_r2,
        prune_user_web_history_r2_cache_func=(
            storage_service.async_prune_user_web_history_r2_cache
        ),
    )


def build_task_core_task_registry_capabilities() -> TaskCoreTaskRegistryCapabilities:
    task_registry = get_task_core_task_registry()
    return TaskCoreTaskRegistryCapabilities(
        add_task_func=task_registry.add_task,
        update_backend_task_id_func=task_registry.update_backend_task_id,
        mark_task_status_func=task_registry.mark_task_status,
        remove_task_func=task_registry.remove_task,
    )


def build_task_core_permission_capabilities() -> TaskCorePermissionCapabilities:
    permission_service = get_task_core_permission_service()
    return TaskCorePermissionCapabilities(
        refresh_user_group_func=permission_service.refresh_user_group
    )


def build_task_core_submission_outbox_capabilities() -> TaskCoreSubmissionOutboxCapabilities:
    submission_outbox = get_task_core_submission_outbox()
    return TaskCoreSubmissionOutboxCapabilities(
        add_pending_refund_func=submission_outbox.add_pending_refund
    )


def build_task_core_image_capabilities() -> TaskCoreImageCapabilities:
    image_service = get_task_core_image_service()
    return TaskCoreImageCapabilities(
        download_result_func=image_service.download_result,
        download_video_result_func=image_service.download_video_result,
        monitor_progress_func=image_service.monitor_progress,
    )


def build_task_core_runtime_capabilities() -> TaskCoreRuntimeCapabilities:
    task_registry = get_task_core_task_registry()
    submission_outbox = get_task_core_submission_outbox()
    api_client = get_task_core_api_client()
    return TaskCoreRuntimeCapabilities(
        get_active_tasks_func=submission_outbox.get_active_tasks,
        get_all_user_concurrencies_func=submission_outbox.get_all_user_concurrencies,
        cancel_task_func=api_client.cancel_task,
        get_task_func=task_registry.get_task,
        find_task_by_backend_task_id_func=task_registry.find_task_by_backend_task_id,
        set_runtime_value_func=submission_outbox.redis.set,
        expire_runtime_value_func=submission_outbox.redis.expire,
        delete_runtime_value_func=submission_outbox.redis.delete,
    )


def get_task_core_storage_copy_to_r2() -> Any:
    return build_task_core_storage_capabilities().copy_to_r2_func


def get_task_core_storage_prune_user_web_history_r2_cache() -> Any:
    return build_task_core_storage_capabilities().prune_user_web_history_r2_cache_func


def get_task_core_task_registry_add_task() -> Any:
    return build_task_core_task_registry_capabilities().add_task_func


def get_task_core_task_registry_update_backend_task_id() -> Any:
    return build_task_core_task_registry_capabilities().update_backend_task_id_func


def get_task_core_task_registry_mark_task_status() -> Any:
    return build_task_core_task_registry_capabilities().mark_task_status_func


def get_task_core_task_registry_remove_task() -> Any:
    return build_task_core_task_registry_capabilities().remove_task_func


def get_task_core_permission_refresh_user_group() -> Any:
    return build_task_core_permission_capabilities().refresh_user_group_func


def get_task_core_submission_outbox_add_pending_refund() -> Any:
    return build_task_core_submission_outbox_capabilities().add_pending_refund_func


def get_task_core_image_download_result() -> Any:
    return build_task_core_image_capabilities().download_result_func


def get_task_core_image_download_video_result() -> Any:
    return build_task_core_image_capabilities().download_video_result_func


def get_task_core_image_monitor_progress() -> Any:
    return build_task_core_image_capabilities().monitor_progress_func


def resolve_task_core_service(name: str) -> Any:
    service_getters = {
        "image_service": get_task_core_image_service,
        "storage": get_task_core_storage_service,
        "TaskRegistry": get_task_core_task_registry,
        "permission_service": get_task_core_permission_service,
        "redis_client": get_task_core_submission_outbox,
        "api_client": get_task_core_api_client,
    }
    try:
        return service_getters[name]()
    except KeyError as exc:
        raise AttributeError(name) from exc
