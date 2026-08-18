from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass
from typing import Any, Callable, Protocol


AsyncCallable = Callable[..., Awaitable[Any]]


class TaskCoreImageServiceProtocol(Protocol):
    download_result: AsyncCallable
    download_video_result: AsyncCallable
    monitor_progress: Callable[..., AsyncIterator[dict[str, Any]]]


class TaskCoreStorageServiceProtocol(Protocol):
    async_copy_to_r2: AsyncCallable
    async_prune_user_web_history_r2_cache: AsyncCallable


class TaskCoreTaskRegistryProtocol(Protocol):
    add_task: AsyncCallable
    update_backend_task_id: AsyncCallable
    mark_task_status: AsyncCallable
    remove_task: AsyncCallable
    get_task: AsyncCallable
    find_task_by_backend_task_id: AsyncCallable


class TaskCorePermissionServiceProtocol(Protocol):
    refresh_user_group: AsyncCallable


class TaskCoreSubmissionOutboxProtocol(Protocol):
    redis: Any
    add_pending_refund: AsyncCallable
    get_active_tasks: AsyncCallable
    get_all_user_concurrencies: AsyncCallable
    sync_user_concurrency: AsyncCallable


class TaskCoreApiClientProtocol(Protocol):
    cancel_task: AsyncCallable


@dataclass(frozen=True)
class TaskCoreServiceProviders:
    get_image_service: Callable[[], TaskCoreImageServiceProtocol]
    get_storage_service: Callable[[], TaskCoreStorageServiceProtocol]
    get_task_registry: Callable[[], TaskCoreTaskRegistryProtocol]
    get_permission_service: Callable[[], TaskCorePermissionServiceProtocol]
    get_submission_outbox: Callable[[], TaskCoreSubmissionOutboxProtocol]
    get_api_client: Callable[[], TaskCoreApiClientProtocol]


@dataclass(frozen=True)
class TaskCoreStorageCapabilities:
    copy_to_r2_func: AsyncCallable
    prune_user_web_history_r2_cache_func: AsyncCallable


@dataclass(frozen=True)
class TaskCoreTaskRegistryCapabilities:
    add_task_func: AsyncCallable
    update_backend_task_id_func: AsyncCallable
    mark_task_status_func: AsyncCallable
    remove_task_func: AsyncCallable


@dataclass(frozen=True)
class TaskCorePermissionCapabilities:
    refresh_user_group_func: AsyncCallable


@dataclass(frozen=True)
class TaskCoreSubmissionOutboxCapabilities:
    add_pending_refund_func: AsyncCallable


@dataclass(frozen=True)
class TaskCoreImageCapabilities:
    download_result_func: AsyncCallable
    download_video_result_func: AsyncCallable
    monitor_progress_func: Callable[..., AsyncIterator[dict[str, Any]]]


@dataclass(frozen=True)
class TaskCoreRuntimeCapabilities:
    get_active_tasks_func: AsyncCallable
    get_all_user_concurrencies_func: AsyncCallable
    cancel_task_func: AsyncCallable
    sync_user_concurrency_func: AsyncCallable
    get_task_func: AsyncCallable
    find_task_by_backend_task_id_func: AsyncCallable


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
    get_image_service: Callable[[], TaskCoreImageServiceProtocol] | None = None,
    get_storage_service: Callable[[], TaskCoreStorageServiceProtocol] | None = None,
    get_task_registry: Callable[[], TaskCoreTaskRegistryProtocol] | None = None,
    get_permission_service: Callable[[], TaskCorePermissionServiceProtocol] | None = None,
    get_submission_outbox: Callable[[], TaskCoreSubmissionOutboxProtocol] | None = None,
    get_api_client: Callable[[], TaskCoreApiClientProtocol] | None = None,
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
        sync_user_concurrency_func=submission_outbox.sync_user_concurrency,
        get_task_func=task_registry.get_task,
        find_task_by_backend_task_id_func=task_registry.find_task_by_backend_task_id,
    )
