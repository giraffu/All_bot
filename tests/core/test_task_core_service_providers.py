from src.core import task_core_service_providers as providers


def test_build_task_core_service_providers_accepts_explicit_overrides():
    image_service = object()
    api_client = object()

    built = providers.build_task_core_service_providers(
        get_image_service=lambda: image_service,
        get_api_client=lambda: api_client,
    )

    assert built.get_image_service() is image_service
    assert built.get_api_client() is api_client
    assert callable(built.get_storage_service)
    assert callable(built.get_task_registry)


def test_resolve_task_core_service_uses_provider_registry(monkeypatch):
    custom = providers.TaskCoreServiceProviders(
        get_image_service=lambda: "image",
        get_storage_service=lambda: "storage",
        get_task_registry=lambda: "registry",
        get_permission_service=lambda: "permission",
        get_submission_outbox=lambda: "redis",
        get_api_client=lambda: "api",
    )
    monkeypatch.setattr(
        providers,
        "build_task_core_service_providers",
        lambda **_kwargs: custom,
    )

    assert providers.resolve_task_core_service("image_service") == "image"
    assert providers.resolve_task_core_service("storage") == "storage"
    assert providers.resolve_task_core_service("TaskRegistry") == "registry"
    assert providers.resolve_task_core_service("permission_service") == "permission"
    assert providers.resolve_task_core_service("redis_client") == "redis"
    assert providers.resolve_task_core_service("api_client") == "api"
