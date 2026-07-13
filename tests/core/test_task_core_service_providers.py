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
