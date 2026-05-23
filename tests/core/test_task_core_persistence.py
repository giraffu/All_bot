from unittest.mock import AsyncMock, Mock

import pytest
from src.core import task_core_persistence
from src.core import task_core_persistence_flow
from src.core.task_core_types import TaskSuccessPersistenceResult


def test_build_task_core_persistence_materialization_dependencies_prefers_explicit_funcs():
    download_result = AsyncMock()
    download_video_result = AsyncMock()
    to_thread = AsyncMock()

    dependencies = (
        task_core_persistence._build_task_core_persistence_materialization_dependencies(
            download_result_func=download_result,
            download_video_result_func=download_video_result,
            to_thread_func=to_thread,
        )
    )

    assert dependencies.download_result_func is download_result
    assert dependencies.download_video_result_func is download_video_result
    assert dependencies.to_thread_func is to_thread


def test_build_task_core_persistence_materialization_dependencies_uses_image_service_getter(
    monkeypatch,
):
    download_result = AsyncMock()
    download_video_result = AsyncMock()

    monkeypatch.setattr(
        task_core_persistence,
        "_load_image_service",
        lambda: type(
            "_ImageService",
            (),
            {
                "download_result": download_result,
                "download_video_result": download_video_result,
            },
        )(),
    )

    dependencies = (
        task_core_persistence._build_task_core_persistence_materialization_dependencies()
    )

    assert dependencies.download_result_func is download_result
    assert dependencies.download_video_result_func is download_video_result


def test_build_task_core_persistence_materialization_dependencies_uses_runtime_default_to_thread_binding(
    monkeypatch,
):
    runtime_to_thread = AsyncMock()

    monkeypatch.setattr(task_core_persistence.asyncio, "to_thread", runtime_to_thread)

    dependencies = (
        task_core_persistence._build_task_core_persistence_materialization_dependencies()
    )

    assert dependencies.to_thread_func is runtime_to_thread


@pytest.mark.asyncio
async def test_persist_successful_task_result_routes_through_flow(monkeypatch):
    download_result = AsyncMock()
    download_video_result = AsyncMock()
    to_thread = AsyncMock()
    flow = AsyncMock(return_value="done")

    monkeypatch.setattr(
        task_core_persistence,
        "_build_task_core_persistence_materialization_dependencies",
        lambda **_: task_core_persistence.TaskCorePersistenceMaterializationDependencies(
            download_result_func=download_result,
            download_video_result_func=download_video_result,
            to_thread_func=to_thread,
        ),
    )

    result = await task_core_persistence.persist_successful_task_result(
        backend_task_id="backend-1",
        registry_task_id="registry-1",
        internal_user_id=123,
        username="tester",
        prompt="prompt",
        task_type="image",
        input_images=["input.png"],
        allow_contribute=True,
        is_video=False,
        billing_resolution="1024",
        requested_duration=None,
        materialize_successful_task_result_flow_func=flow,
    )

    assert result == "done"
    flow.assert_awaited_once()
    kwargs = flow.await_args.kwargs
    assert kwargs["download_result_func"] is download_result
    assert kwargs["download_video_result_func"] is download_video_result
    assert kwargs["to_thread_func"] is to_thread


@pytest.mark.asyncio
async def test_persist_successful_task_result_uses_runtime_default_flow_binding(
    monkeypatch,
):
    flow = AsyncMock(return_value="runtime-bound")
    runtime_user_logger_factory = Mock()
    runtime_extract_from_bytes = AsyncMock()
    runtime_extract_from_storage = AsyncMock()

    monkeypatch.setattr(
        task_core_persistence,
        "_persist_successful_task_result_flow_impl",
        flow,
    )
    monkeypatch.setattr(
        task_core_persistence,
        "UserLogger",
        runtime_user_logger_factory,
    )
    monkeypatch.setattr(
        task_core_persistence,
        "extract_media_metadata_from_bytes_best_effort",
        runtime_extract_from_bytes,
    )
    monkeypatch.setattr(
        task_core_persistence,
        "extract_media_metadata_from_storage_best_effort",
        runtime_extract_from_storage,
    )

    result = await task_core_persistence.persist_successful_task_result(
        backend_task_id="backend-2",
        registry_task_id="registry-2",
        internal_user_id=123,
        username="tester",
        prompt="prompt",
        task_type="image",
        input_images=["input.png"],
        allow_contribute=True,
        is_video=False,
        billing_resolution="1024",
        requested_duration=None,
    )

    assert result == "runtime-bound"
    flow.assert_awaited_once()
    flow_kwargs = flow.await_args.kwargs
    assert flow_kwargs["user_logger_factory"] is runtime_user_logger_factory
    assert (
        flow_kwargs["extract_media_metadata_from_bytes_best_effort_func"]
        is runtime_extract_from_bytes
    )
    assert (
        flow_kwargs["extract_media_metadata_from_storage_best_effort_func"]
        is runtime_extract_from_storage
    )


@pytest.mark.asyncio
async def test_persist_successful_task_result_flow_materializes_then_postprocesses():
    user_logger = object()
    persistence_result = TaskSuccessPersistenceResult(
        media_bytes=b"bytes",
        output_file="output.png",
        width=1024,
        height=1024,
        duration=None,
    )
    user_logger_factory = lambda internal_user_id, username: user_logger
    materialize = AsyncMock(return_value=persistence_result)
    postprocess = AsyncMock()
    download_result = AsyncMock()
    download_video_result = AsyncMock()
    extract_from_bytes = AsyncMock()
    extract_from_storage = AsyncMock()

    result = await task_core_persistence_flow.persist_successful_task_result_flow(
        backend_task_id="backend-1",
        registry_task_id="registry-1",
        internal_user_id=123,
        username="tester",
        prompt="prompt",
        task_type="image",
        input_images=["input.png"],
        allow_contribute=True,
        is_video=False,
        billing_resolution="1024",
        requested_duration=None,
        user_logger_factory=user_logger_factory,
        download_result_func=download_result,
        download_video_result_func=download_video_result,
        extract_media_metadata_from_bytes_best_effort_func=extract_from_bytes,
        extract_media_metadata_from_storage_best_effort_func=extract_from_storage,
        materialize_successful_task_output_func=materialize,
        postprocess_successful_task_persistence_func=postprocess,
    )

    assert result is persistence_result
    materialize.assert_awaited_once()
    postprocess.assert_awaited_once()
    materialize_kwargs = materialize.await_args.kwargs
    assert materialize_kwargs["user_logger"] is user_logger
    assert materialize_kwargs["download_result_func"] is download_result
    assert materialize_kwargs["download_video_result_func"] is download_video_result
    postprocess_kwargs = postprocess.await_args.kwargs
    assert postprocess_kwargs["persistence_result"] is persistence_result
    assert postprocess_kwargs["media_type"] == "image"


@pytest.mark.asyncio
async def test_persist_successful_task_result_flow_uses_runtime_default_bindings(
    monkeypatch,
):
    persistence_result = TaskSuccessPersistenceResult(
        media_bytes=b"bytes",
        output_file="output.png",
        width=256,
        height=256,
        duration=None,
    )
    materialize = AsyncMock(return_value=persistence_result)
    postprocess = AsyncMock()

    monkeypatch.setattr(
        task_core_persistence_flow,
        "_materialize_successful_task_output_impl",
        materialize,
    )
    monkeypatch.setattr(
        task_core_persistence_flow,
        "_postprocess_successful_task_persistence_impl",
        postprocess,
    )

    result = await task_core_persistence_flow.persist_successful_task_result_flow(
        backend_task_id="backend-3",
        registry_task_id="registry-3",
        internal_user_id=123,
        username="tester",
        prompt="prompt",
        task_type="image",
        input_images=["input.png"],
        allow_contribute=True,
        is_video=False,
        billing_resolution="1024",
        requested_duration=None,
        user_logger_factory=lambda *_args, **_kwargs: object(),
        download_result_func=AsyncMock(),
        download_video_result_func=AsyncMock(),
    )

    assert result is persistence_result
    materialize.assert_awaited_once()
    postprocess.assert_awaited_once()
    assert materialize.await_args.kwargs["to_thread_func"] is task_core_persistence_flow.asyncio.to_thread


@pytest.mark.asyncio
async def test_persist_successful_task_result_flow_uses_runtime_default_to_thread_binding(
    monkeypatch,
):
    persistence_result = TaskSuccessPersistenceResult(
        media_bytes=b"bytes",
        output_file="output.png",
        width=256,
        height=256,
        duration=None,
    )
    runtime_to_thread = AsyncMock()
    materialize = AsyncMock(return_value=persistence_result)
    postprocess = AsyncMock()

    monkeypatch.setattr(task_core_persistence_flow.asyncio, "to_thread", runtime_to_thread)
    monkeypatch.setattr(
        task_core_persistence_flow,
        "_materialize_successful_task_output_impl",
        materialize,
    )
    monkeypatch.setattr(
        task_core_persistence_flow,
        "_postprocess_successful_task_persistence_impl",
        postprocess,
    )

    await task_core_persistence_flow.persist_successful_task_result_flow(
        backend_task_id="backend-4",
        registry_task_id="registry-4",
        internal_user_id=123,
        username="tester",
        prompt="prompt",
        task_type="image",
        input_images=["input.png"],
        allow_contribute=True,
        is_video=False,
        billing_resolution="1024",
        requested_duration=None,
        user_logger_factory=lambda *_args, **_kwargs: object(),
        download_result_func=AsyncMock(),
        download_video_result_func=AsyncMock(),
    )

    assert materialize.await_args.kwargs["to_thread_func"] is runtime_to_thread


@pytest.mark.asyncio
async def test_persist_successful_task_result_flow_uses_runtime_default_logger_and_extract_bindings(
    monkeypatch,
):
    user_logger = object()
    persistence_result = TaskSuccessPersistenceResult(
        media_bytes=b"bytes",
        output_file="output.png",
        width=256,
        height=256,
        duration=None,
    )
    runtime_user_logger_factory = Mock(return_value=user_logger)
    runtime_extract_from_bytes = AsyncMock()
    runtime_extract_from_storage = AsyncMock()
    materialize = AsyncMock(return_value=persistence_result)
    postprocess = AsyncMock()

    monkeypatch.setattr(
        task_core_persistence_flow,
        "UserLogger",
        runtime_user_logger_factory,
    )
    monkeypatch.setattr(
        task_core_persistence_flow,
        "extract_media_metadata_from_bytes_best_effort",
        runtime_extract_from_bytes,
    )
    monkeypatch.setattr(
        task_core_persistence_flow,
        "extract_media_metadata_from_storage_best_effort",
        runtime_extract_from_storage,
    )
    monkeypatch.setattr(
        task_core_persistence_flow,
        "_materialize_successful_task_output_impl",
        materialize,
    )
    monkeypatch.setattr(
        task_core_persistence_flow,
        "_postprocess_successful_task_persistence_impl",
        postprocess,
    )

    await task_core_persistence_flow.persist_successful_task_result_flow(
        backend_task_id="backend-5",
        registry_task_id="registry-5",
        internal_user_id=123,
        username="tester",
        prompt="prompt",
        task_type="image",
        input_images=["input.png"],
        allow_contribute=True,
        is_video=False,
        billing_resolution="1024",
        requested_duration=None,
        download_result_func=AsyncMock(),
        download_video_result_func=AsyncMock(),
    )

    runtime_user_logger_factory.assert_called_once_with(123, "tester")
    materialize_kwargs = materialize.await_args.kwargs
    assert materialize_kwargs["user_logger"] is user_logger
    assert (
        materialize_kwargs["extract_media_metadata_from_bytes_best_effort_func"]
        is runtime_extract_from_bytes
    )
    assert (
        materialize_kwargs["extract_media_metadata_from_storage_best_effort_func"]
        is runtime_extract_from_storage
    )
