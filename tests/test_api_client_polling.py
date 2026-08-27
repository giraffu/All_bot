import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src import api_client as api_client_module
from src.circuit_breaker import CircuitBreakerOpenException
from src.services import image_service as image_service_module


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "input_kwargs"),
    [
        ("submit_ltx_video", {"image_path": "start.png"}),
        (
            "submit_ltx_video_flf2v",
            {"image_path": "start.png", "end_image_path": "end.png"},
        ),
        ("submit_ltx_video_v2v_audio", {"video_path": "input.mp4"}),
    ],
)
async def test_ltx_api_client_trims_nonempty_negative_and_omits_blank(
    monkeypatch, method_name, input_kwargs
):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    request = AsyncMock(
        return_value=SimpleNamespace(json=lambda: {"task_id": "task-1"})
    )
    monkeypatch.setattr(client, "_request", request)
    method = getattr(client, method_name)

    await method("task-1", "prompt", negative_prompt="  blur  ", **input_kwargs)
    assert request.await_args.kwargs["json"]["negative_prompt"] == "blur"

    request.reset_mock()
    await method("task-2", "prompt", negative_prompt="   ", **input_kwargs)
    assert "negative_prompt" not in request.await_args.kwargs["json"]


@pytest.mark.asyncio
async def test_ltx_t2v_api_client_forwards_fixed_seed(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    request = AsyncMock(
        return_value=SimpleNamespace(json=lambda: {"task_id": "task-1"})
    )
    monkeypatch.setattr(client, "_request", request)

    await client.submit_ltx_t2v(
        "task-1",
        task_type="ltx_t2v_ic",
        prompt="scene",
        negative_prompt="blur",
        audio_prompt="waves",
        character_sheet="sheet.png",
        character_description="adult woman",
        character_sheets=(),
        character_descriptions=(),
        background_image=None,
        sulphur_strength=None,
        seed=65608997764964,
        width=768,
        height=448,
        length=5,
        frame_count=121,
        fps=24,
    )

    assert request.await_args.kwargs["json"]["seed"] == 65608997764964


@pytest.mark.asyncio
async def test_ltx_t2v_api_client_forwards_ordered_msr_inputs(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    request = AsyncMock(
        return_value=SimpleNamespace(json=lambda: {"task_id": "task-msr"})
    )
    monkeypatch.setattr(client, "_request", request)

    await client.submit_ltx_t2v(
        "task-msr",
        task_type="ltx_t2v_ic",
        prompt="图1与图2在室内交谈",
        negative_prompt=None,
        audio_prompt=None,
        character_sheet=None,
        character_description=None,
        character_sheets=("wang-panel.png", "man-panel.png"),
        character_descriptions=("adult woman Wang", "adult man"),
        background_image="room.png",
        sulphur_strength=None,
        seed=7,
        width=768,
        height=448,
        length=5,
        frame_count=121,
        fps=24,
    )

    payload = request.await_args.kwargs["json"]
    assert payload["character_sheets"] == ["wang-panel.png", "man-panel.png"]
    assert payload["character_descriptions"] == ["adult woman Wang", "adult man"]
    assert payload["background_image"] == "room.png"
    assert payload["sulphur_strength"] is None


@pytest.mark.asyncio
async def test_character_reference_api_client_forwards_selected_view(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    request = AsyncMock(
        return_value=SimpleNamespace(json=lambda: {"task_id": "task-1"})
    )
    monkeypatch.setattr(client, "_request", request)

    result = await client.submit_character_reference_build(
        "task-1",
        prompt="strict side profile",
        image_path="character.png",
        priority=4,
        character_view_index=2,
        character_view_type="face_side",
    )

    assert result == "task-1"
    assert request.await_args.kwargs["json"] == {
        "task_id": "task-1",
        "images": ["character.png"],
        "prompt": "strict side profile",
        "negative_prompt": "text, labels, collage, duplicate person",
        "priority": 4,
        "character_view_index": 2,
        "character_view_type": "face_side",
    }


@pytest.mark.asyncio
async def test_iter_poll_progress_uses_fixed_low_frequency_interval(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    payloads = iter(
        [
            {"status": "pending", "progress": 0.1, "queue_pos": 2},
            {"status": "pending", "progress": 0.1, "queue_pos": 2},
            {"status": "running", "progress": 0.5, "queue_pos": None},
            {"status": "done", "progress": 1.0, "queue_pos": None},
        ]
    )
    sleeps = []

    async def fake_fetch_progress_status(_status_url, **_kwargs):
        return next(payloads)

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(client, "_fetch_progress_status", fake_fetch_progress_status)
    monkeypatch.setattr(
        client,
        "_is_terminal_progress_payload",
        lambda payload: payload.get("status") == "done",
    )
    monkeypatch.setattr(api_client_module, "BOT_STATUS_POLL_INTERVAL", 15)
    monkeypatch.setattr(api_client_module.asyncio, "sleep", fake_sleep)

    events = [
        event
        async for event in client._iter_poll_progress(
            task_id="task-1",
            status_url="http://central/status/task-1",
        )
    ]

    assert [event["status"] for event in events] == [
        "pending",
        "pending",
        "running",
        "done",
    ]
    assert sleeps == [15, 15, 15]


class _FakePubSub:
    def __init__(self):
        self.unsubscribed = []
        self.closed = False

    async def subscribe(self, _channel):
        return None

    async def get_message(self, **_kwargs):
        raise ConnectionResetError("connection closed by server")

    async def unsubscribe(self, channel):
        self.unsubscribed.append(channel)

    async def close(self):
        self.closed = True


class _FakeRedisClient:
    def __init__(self, pubsub):
        self._pubsub = pubsub
        self.closed = False

    def pubsub(self):
        return self._pubsub

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_listen_for_progress_uses_polling_without_pubsub(
    monkeypatch,
):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    payloads = iter(
        [
            {"status": "pending", "progress": 0.1, "queue_pos": 2},
            {"status": "done", "progress": 1.0, "queue_pos": None},
        ]
    )

    async def fake_fetch_progress_status(_status_url, **_kwargs):
        return next(payloads)

    async def fail_pubsub(*_args, **_kwargs):
        raise AssertionError("Pub/Sub should not be used by listen_for_progress")

    monkeypatch.setattr(client, "_fetch_progress_status", fake_fetch_progress_status)
    monkeypatch.setattr(
        client,
        "_is_terminal_progress_payload",
        lambda payload: payload.get("status") == "done",
    )
    monkeypatch.setattr(client, "_iter_pubsub_progress", fail_pubsub)

    events = [event async for event in client.listen_for_progress("task-1")]

    assert [event["status"] for event in events] == ["pending", "done"]


@pytest.mark.asyncio
async def test_listen_for_progress_requests_type_queue_position_when_enabled(
    monkeypatch,
):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    captured = []

    async def fake_fetch_progress_status(_status_url, **kwargs):
        captured.append(kwargs)
        return {"status": "done", "progress": 1.0}

    monkeypatch.setattr(client, "_fetch_progress_status", fake_fetch_progress_status)
    monkeypatch.setattr(
        client,
        "_is_terminal_progress_payload",
        lambda payload: payload.get("status") == "done",
    )

    events = [
        event
        async for event in client.listen_for_progress(
            "task-1",
            include_type_position=True,
        )
    ]

    assert events == [{"status": "done", "progress": 1.0}]
    assert captured == [{"include_type_position": True}]


@pytest.mark.asyncio
async def test_image_service_monitor_progress_requests_type_queue_position_by_default(
    monkeypatch,
):
    captured = []

    async def fake_listen_for_progress(task_id, is_video=False, **kwargs):
        captured.append((task_id, is_video, kwargs))
        yield {"status": "done"}

    monkeypatch.setattr(
        image_service_module,
        "api_client",
        SimpleNamespace(listen_for_progress=fake_listen_for_progress),
    )

    service = image_service_module.ImageService()
    events = [
        event async for event in service.monitor_progress("task-1", is_video=True)
    ]

    assert events == [{"status": "done"}]
    assert captured == [
        ("task-1", True, {"include_type_position": True}),
    ]


@pytest.mark.asyncio
async def test_listen_for_progress_keeps_404_cancelled_semantics(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    request = httpx.Request("GET", "http://central/status/task-missing")
    response = httpx.Response(404, request=request)

    async def fake_fetch_progress_status(_status_url, **_kwargs):
        raise httpx.HTTPStatusError(
            "missing",
            request=request,
            response=response,
        )

    monkeypatch.setattr(client, "_fetch_progress_status", fake_fetch_progress_status)

    events = []
    with pytest.raises(RuntimeError, match="cancelled"):
        async for event in client.listen_for_progress("task-missing"):
            events.append(event)

    assert events == [{"status": "cancelled", "error": "Task cancelled (404)"}]


@pytest.mark.asyncio
async def test_request_uses_isolated_circuit_breaker_keys(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    calls = []

    class FakeBreaker:
        async def call(self, func):
            calls.append("breaker")
            return await func()

    class FakeHttpClient:
        async def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return httpx.Response(
                200,
                json={"ok": True},
                request=httpx.Request(method, url),
            )

    monkeypatch.setattr(
        api_client_module,
        "get_circuit_breaker",
        lambda key: calls.append(("key", key)) or FakeBreaker(),
    )
    client.headers = {}
    client.client = FakeHttpClient()

    response = await client._request(
        "GET",
        "http://central/status/task-1",
        circuit_breaker_key="status",
    )

    assert response.json() == {"ok": True}
    assert calls[0] == ("key", "status")


@pytest.mark.asyncio
async def test_request_open_status_breaker_does_not_block_submit_key(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    calls = []

    class OpenBreaker:
        async def call(self, _func):
            raise CircuitBreakerOpenException("Circuit is open")

    class ClosedBreaker:
        async def call(self, func):
            return await func()

    class FakeHttpClient:
        async def request(self, method, url, **kwargs):
            calls.append((method, url))
            return httpx.Response(
                200,
                json={"task_id": "task-1"},
                request=httpx.Request(method, url),
            )

    def fake_get_circuit_breaker(key):
        return OpenBreaker() if key == "status" else ClosedBreaker()

    monkeypatch.setattr(
        api_client_module,
        "get_circuit_breaker",
        fake_get_circuit_breaker,
    )
    client.headers = {}
    client.client = FakeHttpClient()

    with pytest.raises(CircuitBreakerOpenException):
        await client._request(
            "GET",
            "http://central/status/task-1",
            circuit_breaker_key="status",
        )

    response = await client._request(
        "POST",
        "http://central/comfy_img2img",
        circuit_breaker_key="submit",
    )

    assert response.json() == {"task_id": "task-1"}
    assert calls == [("POST", "http://central/comfy_img2img")]


@pytest.mark.parametrize("status_code", [400, 404])
def test_central_api_circuit_failure_classifier_counts_5xx_not_4xx(status_code):
    request = httpx.Request("GET", "http://central/status/task-1")
    client_error = httpx.HTTPStatusError(
        "bad request",
        request=request,
        response=httpx.Response(status_code, request=request),
    )
    server_error = httpx.HTTPStatusError(
        "service unavailable",
        request=request,
        response=httpx.Response(503, request=request),
    )

    assert (
        api_client_module.should_count_central_api_circuit_failure(client_error)
        is False
    )
    assert (
        api_client_module.should_count_central_api_circuit_failure(server_error) is True
    )
    assert (
        api_client_module.should_count_central_api_circuit_failure(
            httpx.ConnectError("connection lost")
        )
        is True
    )


@pytest.mark.asyncio
async def test_request_log_preserves_blank_transport_error_type(monkeypatch, caplog):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)

    class FailingHttpClient:
        async def request(self, method, url, **kwargs):
            raise httpx.ReadTimeout("", request=httpx.Request(method, url))

    client.headers = {}
    client.client = FailingHttpClient()

    with caplog.at_level("ERROR", logger="src.api_client"):
        with pytest.raises(httpx.ReadTimeout):
            await client._request(
                "GET",
                "http://central/status/task-1",
                use_circuit_breaker=False,
            )

    assert "ReadTimeout" in caplog.text


@pytest.mark.asyncio
async def test_expected_status_404_is_not_logged_as_request_error(caplog):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)

    class MissingHttpClient:
        async def request(self, method, url, **kwargs):
            return httpx.Response(
                404,
                request=httpx.Request(method, url),
            )

    client.headers = {}
    client.client = MissingHttpClient()

    with caplog.at_level("DEBUG", logger="src.api_client"):
        with pytest.raises(httpx.HTTPStatusError):
            await client._request(
                "GET",
                "http://central/status/task-missing",
                expected_status_codes={404},
                use_circuit_breaker=False,
            )

    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert "expected_status=404" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_type", "expected_endpoint"),
    [
        ("face_swap", api_client_module.FACE_SWAP_ENDPOINT),
        ("face_swap_v2", api_client_module.FACE_SWAP_V2_ENDPOINT),
    ],
)
async def test_submit_face_swap_selects_version_endpoint(
    monkeypatch,
    task_type,
    expected_endpoint,
):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    request = AsyncMock(
        return_value=httpx.Response(200, json={"task_id": "backend-task-id"})
    )
    monkeypatch.setattr(client, "_request", request)

    result = await client.submit_face_swap(
        "task-face",
        "face.png",
        "body.png",
        priority=3,
        task_type=task_type,
    )

    assert result == "backend-task-id"
    assert request.await_args.args[:2] == ("POST", expected_endpoint)
    assert request.await_args.kwargs["json"] == {
        "task_id": "task-face",
        "face_image": "face.png",
        "body_image": "body.png",
        "priority": 3,
    }


@pytest.mark.asyncio
async def test_submit_minimax_h3_forwards_optional_lora_strengths(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    request = AsyncMock(
        return_value=httpx.Response(200, json={"task_id": "backend-h3"})
    )
    monkeypatch.setattr(client, "_request", request)

    result = await client.submit_minimax_h3(
        "task-h3",
        task_type="minimax_h3_t2v",
        prompt="scene",
        images=(),
        reference_descriptions=(),
        duration=5,
        resolution_preset="preview",
        aspect_ratio="16:9",
        width=672,
        height=384,
        frame_count=124,
        fps=24,
        seed=123,
        lora_items=(
            {"name": "naughty_times", "strength": 0.8},
            {"name": "sex_pose", "strength": 0.45},
        ),
        priority=2,
    )

    assert result == "backend-h3"
    assert request.await_args.args[:2] == (
        "POST",
        api_client_module.MINIMAX_H3_ENDPOINTS["minimax_h3_t2v"],
    )
    assert request.await_args.kwargs["json"]["lora_items"] == [
        {"name": "naughty_times", "strength": 0.8},
        {"name": "sex_pose", "strength": 0.45},
    ]
    assert request.await_args.kwargs["json"]["main_model"] == "10eros"


@pytest.mark.asyncio
async def test_submit_scail2_face_swap_marks_reference_preprocessed(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    request = AsyncMock(
        return_value=httpx.Response(200, json={"task_id": "stage2-video"})
    )
    monkeypatch.setattr(client, "_request", request)

    result = await client.submit_scail2_video_task(
        "stage2-video",
        task_type="scail2_face_swap_v2",
        reference_image_path="swapped-frame.png",
        motion_video_path="motion.mp4",
        prompt="keep scene",
        length=5,
        priority=7,
        reference_preprocessed=True,
    )

    assert result == "stage2-video"
    assert request.await_args.kwargs["json"]["reference_preprocessed"] is True
    assert request.await_args.kwargs["json"]["priority"] == 7


@pytest.mark.asyncio
async def test_submit_pornmaster_flux2_bf16_uses_dedicated_single_image_endpoint(
    monkeypatch,
):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    request = AsyncMock(
        return_value=httpx.Response(200, json={"task_id": "backend-task-id"})
    )
    monkeypatch.setattr(client, "_request", request)

    result = await client.submit_pornmaster_flux2_edit(
        "task-bf16",
        execution_task_type="pornmaster_flux2_edit_bf16",
        prompt="high precision edit",
        image_paths=["/tmp/input.png"],
        priority=3,
    )

    assert result == "backend-task-id"
    request.assert_awaited_once()
    assert request.await_args.args[:2] == (
        "POST",
        api_client_module.PORNMASTER_FLUX2_EDIT_BF16_ENDPOINT,
    )
    assert request.await_args.kwargs["json"]["images"] == ["/tmp/input.png"]


@pytest.mark.asyncio
async def test_submit_pornmaster_flux2_multi_bf16_uses_dedicated_two_image_endpoint(
    monkeypatch,
):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    request = AsyncMock(
        return_value=httpx.Response(200, json={"task_id": "backend-task-id"})
    )
    monkeypatch.setattr(client, "_request", request)

    await client.submit_pornmaster_flux2_edit(
        "task-bf16-multi",
        execution_task_type="pornmaster_flux2_multi_edit_bf16",
        prompt="combine references",
        image_paths=["/tmp/one.png", "/tmp/two.png"],
        priority=3,
    )

    assert request.await_args.args[:2] == (
        "POST",
        api_client_module.PORNMASTER_FLUX2_MULTI_EDIT_BF16_ENDPOINT,
    )
    assert request.await_args.kwargs["json"]["images"] == [
        "/tmp/one.png",
        "/tmp/two.png",
    ]
    assert request.await_args.kwargs["json"]["image2"] == "/tmp/two.png"
