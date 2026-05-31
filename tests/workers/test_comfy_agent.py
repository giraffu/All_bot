import importlib.util
import logging
import sys
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "workers" / "comfy_agent" / "agent_main.py"
MODULE_DIR = str(MODULE_PATH.parent)


def load_agent_main_module():
    if MODULE_DIR not in sys.path:
        sys.path.insert(0, MODULE_DIR)

    if "websockets" not in sys.modules:
        websocket_state = SimpleNamespace(CLOSED="CLOSED")
        sys.modules["websockets"] = SimpleNamespace(
            protocol=SimpleNamespace(State=websocket_state),
            connect=None,
        )
    if "asgi_correlation_id" not in sys.modules:
        sys.modules["asgi_correlation_id"] = SimpleNamespace(
            correlation_id=SimpleNamespace(get=lambda: None, set=lambda value: None)
        )
    if "dotenv" not in sys.modules:
        sys.modules["dotenv"] = SimpleNamespace(load_dotenv=lambda: None)
    if "minio" not in sys.modules:
        minio_module = ModuleType("minio")
        minio_module.Minio = DummyMinio
        sys.modules["minio"] = minio_module
    if "PIL" not in sys.modules:
        pil_module = ModuleType("PIL")
        image_module = ModuleType("PIL.Image")
        image_module.open = None
        imageops_module = ModuleType("PIL.ImageOps")
        imageops_module.exif_transpose = lambda image: image
        pil_module.Image = image_module
        pil_module.ImageOps = imageops_module
        pil_module.UnidentifiedImageError = RuntimeError
        sys.modules["PIL"] = pil_module
        sys.modules["PIL.Image"] = image_module
        sys.modules["PIL.ImageOps"] = imageops_module

    spec = importlib.util.spec_from_file_location("test_agent_main_module", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        self.closed = False

    async def aclose(self):
        self.closed = True


class DummyComfyClient:
    def __init__(self, *args, **kwargs):
        self.closed = False
        self.client = SimpleNamespace(get=self._unexpected_get)

    async def _unexpected_get(self, *args, **kwargs):
        raise AssertionError("Unexpected Comfy client GET during this test")

    async def close(self):
        self.closed = True


class DummyWorkflowPatcher:
    def __init__(self, *args, **kwargs):
        pass

    def load_workflow(self, task_type):
        return None

    def patch_workflow(self, task_type, workflow, params):
        return workflow


class DummyMinio:
    def __init__(self, *args, **kwargs):
        pass


class DummyFileHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def emit(self, record):
        return None


def build_agent_module(monkeypatch):
    with ExitStack() as stack:
        stack.enter_context(mock.patch("os.makedirs", return_value=None))
        stack.enter_context(mock.patch("logging.FileHandler", DummyFileHandler))
        module = load_agent_main_module()
    monkeypatch.setattr(module, "ComfyClient", DummyComfyClient)
    monkeypatch.setattr(module, "WorkflowPatcher", DummyWorkflowPatcher)
    monkeypatch.setattr(module, "Minio", DummyMinio)
    monkeypatch.setattr(module.httpx, "AsyncClient", DummyAsyncClient)
    return module


def test_agent_main_removes_debug_side_paths():
    content = MODULE_PATH.read_text(encoding="utf-8")

    assert ".dbg/wan22-video-output.env" not in content
    assert "http://127.0.0.1:7777/event" not in content
    assert 'exec(' not in content


def test_wan22_result_pick_prefers_video_over_images(monkeypatch):
    module = build_agent_module(monkeypatch)
    outputs = {
        "image_node": {"images": [{"filename": "preview.png"}]},
        "video_node": {"videos": [{"filename": "result.mp4"}]},
    }

    asset = module.pick_first_output_asset(outputs, task_type="wan22_video_v2")

    assert asset is not None
    assert asset["filename"] == "result.mp4"
    assert module.result_asset_priority(asset, task_type="wan22_video_v2") == 3


@pytest.mark.asyncio
async def test_shutdown_before_start_reports_and_closes_clients(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    reported = []

    async def fake_report_status(task_id, status, progress=None, error=None):
        reported.append((task_id, status, error))

    agent._active_execution = module.TaskExecutionContext(
        task_id="task-42", task_type="image"
    )
    agent.report_status = fake_report_status

    await agent.shutdown()

    assert reported == [
        (
            "task-42",
            "failed",
            "Agent was shut down while processing the task. Task should be retried.",
        )
    ]
    assert agent.master_client.closed is True
    assert agent.comfy_client.closed is True


@pytest.mark.asyncio
async def test_process_task_failure_resets_runtime_state(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    reported = []

    async def fake_check_task_cancelled(task_id):
        return False

    async def fake_prepare_task_inputs(*args, **kwargs):
        return None

    async def fake_report_status(task_id, status, progress=None, error=None):
        reported.append((task_id, status, error))

    agent.check_task_cancelled = fake_check_task_cancelled
    agent._prepare_task_inputs = fake_prepare_task_inputs
    agent.report_status = fake_report_status
    agent._active_execution = module.TaskExecutionContext(
        task_id="stale-task",
        task_type="stale-type",
        task_result="stale-result",
        task_error="stale-error",
    )

    await agent.process_task(
        {
            "task_id": "task-1",
            "type": "wan22_video_v2",
            "params": "{}",
        }
    )

    assert reported
    assert reported[-1][0] == "task-1"
    assert reported[-1][1] == "failed"
    assert "Workflow for wan22_video_v2 not found" in reported[-1][2]
    assert agent._active_execution is None
    assert agent.task_completed_event.is_set() is False


@pytest.mark.asyncio
async def test_report_heartbeat_uses_active_execution_context(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    requests = []

    async def fake_post(path, json):
        requests.append((path, json))
        return SimpleNamespace(status_code=200)

    agent.master_client.post = fake_post
    agent._active_execution = module.TaskExecutionContext(
        task_id="task-99",
        task_type="wan22_video_v2",
    )

    await agent.report_heartbeat()

    assert requests[0][0] == "/api/agent/task/heartbeat"
    assert requests[0][1]["status"] == "running"
    assert requests[1] == ("/api/agent/task/task_heartbeat", {"task_id": "task-99"})
