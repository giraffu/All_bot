import asyncio
import importlib.util
import io
import logging
import sys
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "workers" / "comfy_agent" / "agent_main.py"
MODULE_DIR = str(MODULE_PATH.parent)
WORKFLOW_EXECUTION_PATHS = (
    ROOT / "workers" / "comfy_agent" / "agent_workflow_execution.py",
)


def load_agent_main_module(module_path=MODULE_PATH):
    module_dir = str(module_path.parent)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

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
    if "minio" not in sys.modules and importlib.util.find_spec("minio") is None:
        minio_module = ModuleType("minio")
        minio_module.Minio = DummyMinio
        sys.modules["minio"] = minio_module
    try:
        import PIL  # noqa: F401
        import PIL.Image  # noqa: F401
        import PIL.ImageChops  # noqa: F401
        import PIL.ImageOps  # noqa: F401
        import PIL.ImageStat  # noqa: F401
    except Exception:
        pil_module = ModuleType("PIL")
        image_module = ModuleType("PIL.Image")
        image_module.open = None
        imagechops_module = ModuleType("PIL.ImageChops")
        imagestat_module = ModuleType("PIL.ImageStat")
        imageops_module = ModuleType("PIL.ImageOps")
        imageops_module.exif_transpose = lambda image: image
        pil_module.Image = image_module
        pil_module.ImageChops = imagechops_module
        pil_module.ImageStat = imagestat_module
        pil_module.ImageOps = imageops_module
        pil_module.UnidentifiedImageError = RuntimeError
        sys.modules["PIL"] = pil_module
        sys.modules["PIL.Image"] = image_module
        sys.modules["PIL.ImageChops"] = imagechops_module
        sys.modules["PIL.ImageOps"] = imageops_module
        sys.modules["PIL.ImageStat"] = imagestat_module

    module_name = (
        "test_runpod_agent_main_module"
        if "runpod_runtime" in module_path.parts
        else "test_agent_main_module"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_workflow_execution_module(module_path: Path):
    module_dir = str(module_path.parent)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
    module_name = (
        "test_runpod_agent_workflow_execution"
        if "runpod_runtime" in module_path.parts
        else "test_agent_workflow_execution"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_quality_retry_waits_for_a_free_comfy_slot(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    retry_execution = module.TaskExecutionContext(
        task_id="retry-task",
        task_type="i2i_pro",
    )
    retry_execution.phase = "delivering"
    blocker = module.TaskExecutionContext(
        task_id="gpu-task",
        task_type="i2i_pro",
    )
    blocker.phase = "queued"
    agent._executions = {
        retry_execution.task_id: retry_execution,
        blocker.task_id: blocker,
    }
    agent._pipeline_admission = module.PipelineAdmission(
        max_claimed_tasks=2,
        max_comfy_inflight=1,
    )

    reservation = asyncio.create_task(
        agent._finalizer._reserve_comfy_slot_for_retry(retry_execution)
    )
    await asyncio.sleep(0)
    assert reservation.done() is False
    assert retry_execution.phase == "delivering"

    blocker.phase = "gpu_done"
    await asyncio.wait_for(reservation, timeout=0.5)

    assert retry_execution.phase == "preparing"


@pytest.mark.asyncio
async def test_runpod_worker_promotes_reserved_claim_without_exceeding_limit(
    monkeypatch,
):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    agent._executions = {}
    agent._reserved_prefetch_task = {
        "task_id": "reserved-task",
        "type": "pornmaster_flux2_edit_bf16",
    }
    agent._pipeline_admission = module.PipelineAdmission(
        max_claimed_tasks=3,
        max_comfy_inflight=2,
    )

    task = await agent._pop_next_task(pipeline=True)

    assert task["task_id"] == "reserved-task"
    assert agent._reserved_prefetch_task is None
    assert list(agent._executions) == ["reserved-task"]
    assert agent._executions["reserved-task"].phase == "claimed"


@pytest.mark.asyncio
async def test_runpod_worker_does_not_pop_fourth_claim(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    agent._reserved_prefetch_task = None
    agent._executions = {
        task_id: module.TaskExecutionContext(
            task_id=task_id,
            task_type="pornmaster_flux2_edit_bf16",
            phase=phase,
        )
        for task_id, phase in (
            ("delivery", "delivering"),
            ("gpu-done", "gpu_done"),
            ("gpu", "running"),
        )
    }
    agent._pipeline_admission = module.PipelineAdmission(
        max_claimed_tasks=3,
        max_comfy_inflight=2,
    )
    agent.master_client = SimpleNamespace(
        get=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Central pop must not be called at the claim limit")
        )
    )

    assert await agent._pop_next_task(pipeline=True) is None


@pytest.mark.asyncio
async def test_runpod_worker_acknowledges_redelivered_active_claim_without_relaunch(
    monkeypatch,
):
    module = build_agent_module(monkeypatch)
    module.SUPPORTED_TASK_TYPES = "t2i-pornmaster-turbo"
    agent = module.ComfyAgent()
    existing = module.TaskExecutionContext(
        task_id="task-1",
        task_type="t2i-pornmaster-turbo",
        phase="running",
    )
    existing.prompt_id = "prompt-original"
    agent._executions = {"task-1": existing}
    agent._reserved_prefetch_task = None
    agent._prefetch_cache = {}
    agent._pipeline_task_types = {"t2i-pornmaster-turbo"}
    agent._pipeline_admission = module.PipelineAdmission(
        max_claimed_tasks=3,
        max_comfy_inflight=2,
    )
    agent.master_client = SimpleNamespace(
        get=mock.AsyncMock(
            return_value=SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "task": {
                        "task_id": "task-1",
                        "type": "t2i-pornmaster-turbo",
                        "params": "{}",
                    }
                },
            )
        )
    )
    agent._master_get = agent.master_client.get
    agent.report_status = mock.AsyncMock()

    task = await agent._pop_next_task(pipeline=True)

    assert task is None
    assert agent._executions == {"task-1": existing}
    assert existing.prompt_id == "prompt-original"
    agent.report_status.assert_awaited_once_with(
        "task-1",
        "running",
        execution_phase="running",
        cancel_locked=module.CANCEL_LOCK_ON_POP,
    )


@pytest.mark.asyncio
async def test_runpod_reserved_prefetch_discards_redelivered_active_claim(monkeypatch):
    module = build_agent_module(monkeypatch)
    monkeypatch.setattr(module, "PREFETCH_ENABLED", True)
    monkeypatch.setattr(module, "PREFETCH_DEPTH", 1)
    monkeypatch.setattr(module, "PREFETCH_RESERVE_TASK", True)
    monkeypatch.setattr(module, "SUPPORTED_TASK_TYPES", "t2i-pornmaster-turbo")
    agent = module.ComfyAgent()
    existing = module.TaskExecutionContext(
        task_id="task-1",
        task_type="t2i-pornmaster-turbo",
        phase="queued",
    )
    existing.prompt_id = "prompt-original"
    agent._executions = {"task-1": existing}
    agent._reserved_prefetch_task = None
    agent._prefetch_cache = {}
    agent._prefetch_task_types = {"t2i-pornmaster-turbo"}
    agent._pipeline_task_types = {"t2i-pornmaster-turbo"}
    agent._pipeline_admission = module.PipelineAdmission(
        max_claimed_tasks=3,
        max_comfy_inflight=2,
    )
    agent.master_client = SimpleNamespace(
        get=mock.AsyncMock(
            return_value=SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "task": {
                        "task_id": "task-1",
                        "type": "t2i-pornmaster-turbo",
                        "params": "{}",
                    }
                },
            )
        )
    )
    agent._master_get = agent.master_client.get
    agent.report_status = mock.AsyncMock()
    agent._prepare_task_inputs = mock.AsyncMock()

    await agent._prefetch_next_task_inputs()

    assert agent._reserved_prefetch_task is None
    assert agent._prefetch_cache == {}
    agent._prepare_task_inputs.assert_not_awaited()
    agent.report_status.assert_awaited_once_with(
        "task-1",
        "running",
        execution_phase="queued",
        cancel_locked=module.CANCEL_LOCK_ON_POP,
    )


@pytest.mark.asyncio
async def test_standard_worker_reserved_prefetch_discards_active_task(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    execution = module.TaskExecutionContext(
        task_id="task-1",
        task_type="img2img",
        phase="running",
    )
    execution.prompt_id = "prompt-original"
    agent._executions = {"task-1": execution}
    agent._prefetch_task_types = {"img2img"}
    agent._pipeline_task_types = {"all"}
    agent._master_get = mock.AsyncMock(
        return_value=SimpleNamespace(
            status_code=200,
            json=lambda: {
                "task": {
                    "task_id": "task-1",
                    "type": "img2img",
                    "params": "{}",
                }
            },
        )
    )
    agent._acknowledge_redelivered_task = mock.AsyncMock()
    agent._prepare_task_inputs = mock.AsyncMock()

    await agent._prefetch_manager.prefetch_next_task_inputs(
        prefetch_enabled=True,
        prefetch_depth=1,
        cache_dir="/tmp/prefetch",
        reserve_task=True,
    )

    assert agent._reserved_prefetch_task is None
    assert agent._prefetch_cache == {}
    agent._prepare_task_inputs.assert_not_awaited()
    agent._acknowledge_redelivered_task.assert_awaited_once_with("task-1")


@pytest.mark.parametrize(
    "module_path",
    (
        ROOT / "workers" / "comfy_agent" / "agent_main.py",
    ),
)
def test_worker_rejects_duplicate_execution_start_without_overwriting_prompt(
    module_path, monkeypatch
):
    with ExitStack() as stack:
        stack.enter_context(mock.patch("os.makedirs", return_value=None))
        stack.enter_context(mock.patch("logging.FileHandler", DummyFileHandler))
        module = load_agent_main_module(module_path)
    agent = module.ComfyAgent.__new__(module.ComfyAgent)
    existing = module.TaskExecutionContext(
        task_id="task-1",
        task_type="t2i-pornmaster-turbo",
        phase="running",
    )
    existing.prompt_id = "prompt-original"
    agent._executions = {"task-1": existing}
    agent._active_execution = existing

    with pytest.raises(RuntimeError, match="already has an active execution"):
        agent._start_task_execution(
            task_id="task-1",
            task_type="t2i-pornmaster-turbo",
        )

    assert agent._executions == {"task-1": existing}
    assert existing.prompt_id == "prompt-original"


class DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        self.closed = False

    async def post(self, *args, **kwargs):
        return SimpleNamespace(status_code=200)

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

    async def interrupt(self):
        return True


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


def _png_bytes(
    color: tuple[int, int, int], *, size: tuple[int, int] = (32, 32)
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


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
    assert "exec(" not in content


def test_normalize_mislabeled_jpeg_preserves_compact_jpeg(tmp_path):
    with ExitStack() as stack:
        stack.enter_context(mock.patch("os.makedirs", return_value=None))
        stack.enter_context(mock.patch("logging.FileHandler", DummyFileHandler))
        module = load_agent_main_module()

    source_path = tmp_path / "telegram-upload.png"
    Image.new("RGB", (713, 1280), (90, 120, 150)).save(
        source_path,
        format="JPEG",
        quality=85,
    )
    source_bytes = source_path.read_bytes()

    normalized_path = Path(
        module.ComfyAgent._normalize_input_image_for_comfy(str(source_path))
    )

    assert normalized_path.suffix == ".jpg"
    assert normalized_path.read_bytes() == source_bytes
    with Image.open(normalized_path) as normalized:
        assert normalized.format == "JPEG"
        assert normalized.mode == "RGB"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module_path",
    (
        ROOT / "workers" / "comfy_agent" / "agent_main.py",
    ),
)
async def test_all_profile_releases_comfy_memory_before_each_submission(
    monkeypatch,
    module_path: Path,
):
    with ExitStack() as stack:
        stack.enter_context(mock.patch("os.makedirs", return_value=None))
        stack.enter_context(mock.patch("logging.FileHandler", DummyFileHandler))
        module = load_agent_main_module(module_path)
    calls = []

    class RecordingComfyClient:
        async def free_memory(self):
            calls.append("free_memory")

    agent = module.ComfyAgent.__new__(module.ComfyAgent)
    agent.comfy_client = RecordingComfyClient()
    monkeypatch.setattr(module, "POOL_RUNTIME_PROFILE", "all")

    await agent._reset_comfy_memory_before_task()

    assert calls == ["free_memory"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module_path",
    (
        ROOT / "workers" / "comfy_agent" / "agent_main.py",
    ),
)
async def test_explicit_multi_model_profile_releases_comfy_memory(
    monkeypatch,
    module_path: Path,
):
    with ExitStack() as stack:
        stack.enter_context(mock.patch("os.makedirs", return_value=None))
        stack.enter_context(mock.patch("logging.FileHandler", DummyFileHandler))
        module = load_agent_main_module(module_path)
    calls = []

    class RecordingComfyClient:
        async def free_memory(self):
            calls.append("free_memory")

    agent = module.ComfyAgent.__new__(module.ComfyAgent)
    agent.comfy_client = RecordingComfyClient()
    monkeypatch.setattr(module, "POOL_RUNTIME_PROFILE", "scail2_flex")
    monkeypatch.setattr(module, "RESET_COMFY_MEMORY_BEFORE_TASK", True)

    await agent._reset_comfy_memory_before_task()

    assert calls == ["free_memory"]


@pytest.mark.asyncio
async def test_non_all_profile_keeps_resident_comfy_models(monkeypatch):
    with ExitStack() as stack:
        stack.enter_context(mock.patch("os.makedirs", return_value=None))
        stack.enter_context(mock.patch("logging.FileHandler", DummyFileHandler))
        module = load_agent_main_module()

    class UnexpectedComfyClient:
        async def free_memory(self):
            raise AssertionError("non-all worker must preserve its resident model cache")

    agent = module.ComfyAgent.__new__(module.ComfyAgent)
    agent.comfy_client = UnexpectedComfyClient()
    monkeypatch.setattr(module, "POOL_RUNTIME_PROFILE", "image_to_video")
    monkeypatch.setattr(module, "RESET_COMFY_MEMORY_BEFORE_TASK", False)

    await agent._reset_comfy_memory_before_task()


@pytest.mark.asyncio
@pytest.mark.parametrize("module_path", WORKFLOW_EXECUTION_PATHS)
async def test_scail2_face_swap_worker_rejects_unprepared_reference_before_comfy(
    module_path,
):
    module = load_workflow_execution_module(module_path)

    class UnexpectedPatcher:
        def load_workflow(self, _task_type):
            raise AssertionError("workflow must not load before stage-one completion")

    class UnexpectedComfyClient:
        async def queue_prompt(self, *_args, **_kwargs):
            raise AssertionError("ComfyUI must not receive an unprepared SCAIL task")

    async def unexpected_async_call(*_args, **_kwargs):
        raise AssertionError("execution must fail before contacting ComfyUI")

    with pytest.raises(ValueError, match="reference_preprocessed=true"):
        await module.submit_task_workflow(
            task_id="stage2-task",
            task_type="scail2_face_swap_v2",
            params={
                "image": "raw-reference.png",
                "video": "motion.mp4",
            },
            execution=SimpleNamespace(prompt_id=None),
            patcher=UnexpectedPatcher(),
            comfy_client=UnexpectedComfyClient(),
            wait_for_comfy_ready_func=unexpected_async_call,
            report_status_func=unexpected_async_call,
            agent_id="scail-worker",
            logger=logging.getLogger("test"),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("module_path", WORKFLOW_EXECUTION_PATHS)
async def test_scail2_face_swap_worker_accepts_only_preprocessed_stage_two(
    module_path,
):
    module = load_workflow_execution_module(module_path)
    calls = []

    class Patcher:
        def load_workflow(self, task_type):
            calls.append(("load", task_type))
            return {"node": {"inputs": {}}}

        def patch_workflow(self, task_type, workflow, params):
            calls.append(("patch", task_type, params["reference_preprocessed"]))
            return workflow

    class ComfyClient:
        async def queue_prompt(self, _workflow, client_id):
            calls.append(("queue", client_id))
            return "prompt-1"

    async def wait_for_comfy_ready(*, operation):
        calls.append(("ready", operation))

    async def report_status(task_id, status):
        calls.append(("status", task_id, status))

    execution = SimpleNamespace(prompt_id=None)
    await module.submit_task_workflow(
        task_id="stage2-task",
        task_type="scail2_face_swap_v2",
        params={
            "image": "swapped-first-frame.png",
            "video": "motion.mp4",
            "reference_preprocessed": True,
        },
        execution=execution,
        patcher=Patcher(),
        comfy_client=ComfyClient(),
        wait_for_comfy_ready_func=wait_for_comfy_ready,
        report_status_func=report_status,
        agent_id="scail-worker",
        logger=logging.getLogger("test"),
    )

    assert execution.prompt_id == "prompt-1"
    assert calls == [
        ("load", "scail2_face_swap_v2"),
        ("patch", "scail2_face_swap_v2", True),
        ("ready", "submitting task stage2-task"),
        ("queue", "agent_scail-worker"),
        ("status", "stage2-task", "running"),
    ]


@pytest.mark.asyncio
async def test_reserved_prefetch_considers_all_eligible_worker_types(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    calls = []
    task = {
        "task_id": "task-next",
        "type": "face_swap",
        "params": '{"image": "remote.png"}',
    }

    async def fake_master_get(path, *, params=None):
        calls.append((path, params))
        return SimpleNamespace(status_code=200, json=lambda: {"task": task})

    async def fake_prepare_task_inputs(
        *, params, downloaded_input_paths, comfy_input_dir
    ):
        params["image"] = "prefetched.png"
        downloaded_input_paths.append("/tmp/prefetched.png")

    agent._master_get = fake_master_get
    agent._prepare_task_inputs = fake_prepare_task_inputs
    agent._prefetch_task_types = {"face_swap", "img2img", "unsupported"}

    agent._prefetch_manager.schedule_prefetch(
        current_task_type="face_swap",
        prefetch_enabled=True,
        prefetch_depth=1,
        cache_dir="/tmp/prefetch",
        reserve_task=True,
    )
    await agent._prefetch_task

    assert calls == [
        (
            "/api/agent/task/pop",
            {
                "agent_id": module.AGENT_ID,
                "types": "face_swap,img2img",
                "cancel_lock": "true",
            },
        )
    ]
    assert agent._reserved_prefetch_task == task
    assert agent._prefetch_cache["task-next"]["params"]["image"] == "prefetched.png"

    reused = await agent._pop_next_task(pipeline=True)

    assert reused == task
    assert agent._reserved_prefetch_task is None
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_runpod_reserved_prefetch_considers_all_eligible_worker_types(
    monkeypatch,
):
    module = build_agent_module(monkeypatch)
    monkeypatch.setattr(module, "PREFETCH_ENABLED", True)
    monkeypatch.setattr(module, "PREFETCH_DEPTH", 1)
    monkeypatch.setattr(module, "PREFETCH_RESERVE_TASK", True)
    agent = module.ComfyAgent()
    agent._executions = {}
    agent._reserved_prefetch_task = None
    agent._prefetch_cache = {}
    agent._prefetch_task = None
    agent._prefetch_task_types = {"face_swap", "img2img", "unsupported"}
    agent._pipeline_task_types = {"all"}
    agent._pipeline_admission = module.PipelineAdmission(
        max_claimed_tasks=2,
        max_comfy_inflight=1,
    )
    calls = []
    task = {"task_id": "task-next", "type": "img2img", "params": "{}"}

    async def fake_master_get(path, *, params=None):
        calls.append((path, params))
        return SimpleNamespace(status_code=200, json=lambda: {"task": task})

    async def fake_prepare_task_inputs(**_kwargs):
        return None

    agent.master_client = SimpleNamespace(get=fake_master_get)
    agent._master_get = fake_master_get
    agent._prepare_task_inputs = fake_prepare_task_inputs

    agent._schedule_prefetch(current_task_type="face_swap")
    await agent._prefetch_task

    assert calls == [
        (
            "/api/agent/task/pop",
            {
                "agent_id": module.AGENT_ID,
                "types": "face_swap,img2img",
                "cancel_lock": "true",
            },
        )
    ]
    assert agent._reserved_prefetch_task == task


@pytest.mark.asyncio
async def test_prefetch_skips_central_when_no_worker_type_is_eligible(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    agent._prefetch_task_types = {"unsupported"}

    async def unexpected_master_get(*_args, **_kwargs):
        raise AssertionError("Central must not be called without an eligible type")

    agent._master_get = unexpected_master_get

    await agent._prefetch_manager.prefetch_next_task_inputs(
        prefetch_enabled=True,
        prefetch_depth=1,
        cache_dir="/tmp/prefetch",
        reserve_task=True,
    )

    assert agent._reserved_prefetch_task is None


@pytest.mark.asyncio
async def test_reserved_prefetch_download_failure_keeps_task_for_normal_preparation(
    monkeypatch,
):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    task = {"task_id": "task-next", "type": "face_swap", "params": "{}"}

    async def fake_master_get(_path, *, params=None):
        return SimpleNamespace(status_code=200, json=lambda: {"task": task})

    async def failed_prepare(**_kwargs):
        raise RuntimeError("temporary download failure")

    agent._master_get = fake_master_get
    agent._prepare_task_inputs = failed_prepare
    agent._prefetch_task_types = {"face_swap"}

    await agent._prefetch_manager.prefetch_next_task_inputs(
        prefetch_enabled=True,
        prefetch_depth=1,
        cache_dir="/tmp/prefetch",
        reserve_task=True,
    )

    assert agent._prefetch_cache == {}
    assert await agent._pop_next_task(pipeline=True) == task


@pytest.mark.asyncio
async def test_reserved_prefetch_heartbeat_does_not_replace_current_task(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    reported = []
    agent._reserved_prefetch_task = {
        "task_id": "task-next",
        "type": "wan22_video_v2",
    }

    async def fake_report_status(task_id, status, **kwargs):
        reported.append((task_id, status, kwargs))

    agent.report_status = fake_report_status

    await agent._heartbeat_reserved_prefetch_task()

    assert reported == [
        (
            "task-next",
            "running",
            {
                "execution_phase": "prefetching",
                "cancel_locked": True,
                "set_current": False,
            },
        )
    ]


def test_download_input_prefers_s3_client(monkeypatch, tmp_path):
    module = build_agent_module(monkeypatch)
    downloads = []

    class FakeS3Client:
        def download_file(self, bucket_name, object_name, local_path, **kwargs):
            downloads.append((bucket_name, object_name, local_path, kwargs))
            Path(local_path).write_bytes(b"video")

    class FakeBoto3:
        @staticmethod
        def client(*_args, **_kwargs):
            return FakeS3Client()

    class FakeBotoConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeTransferConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(module, "boto3", FakeBoto3)
    monkeypatch.setattr(module, "BotoConfig", FakeBotoConfig)
    monkeypatch.setattr(module, "TransferConfig", FakeTransferConfig)
    monkeypatch.setattr(module, "MINIO_INPUT_BUCKET", "user-data-prod")

    agent = module.ComfyAgent()
    agent.minio_client = SimpleNamespace(
        fget_object=mock.Mock(side_effect=AssertionError("unexpected MinIO download"))
    )

    target = tmp_path / "input.mp4"
    agent.download_input_from_minio("user-data-prod/web_uploads/input.mp4", str(target))

    assert target.read_bytes() == b"video"
    assert downloads
    bucket_name, object_name, local_path, kwargs = downloads[0]
    assert bucket_name == "user-data-prod"
    assert object_name == "web_uploads/input.mp4"
    assert local_path == str(target)
    assert "Config" in kwargs


def test_download_input_falls_back_to_minio_without_s3(monkeypatch, tmp_path):
    module = build_agent_module(monkeypatch)
    calls = []

    monkeypatch.setattr(module, "boto3", None)
    monkeypatch.setattr(module, "BotoConfig", None)
    monkeypatch.setattr(module, "TransferConfig", None)
    monkeypatch.setattr(module, "MINIO_TEMPLATE_BUCKET", "templates")

    agent = module.ComfyAgent()
    agent.s3_download_client = None
    agent.minio_client = SimpleNamespace(
        fget_object=lambda bucket_name, object_name, local_path: calls.append(
            (bucket_name, object_name, local_path)
        )
    )

    target = tmp_path / "input.png"
    agent.download_input_from_minio("template:quick_face/input.png", str(target))

    assert calls == [("templates", "quick_face/input.png", str(target))]


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


@pytest.mark.parametrize("task_type", ["ltx_video_v2", "ltx_video_v2_flf2v"])
def test_ltx_v2_result_pick_prefers_video_over_last_frame(monkeypatch, task_type):
    module = build_agent_module(monkeypatch)
    outputs = {
        "last_frame_node": {
            "images": [{"filename": f"{task_type}_42_last_frame_00001.png"}]
        },
        "video_node": {"videos": [{"filename": "result.mp4"}]},
    }

    asset = module.pick_first_output_asset(outputs, task_type=task_type)

    assert asset is not None
    assert asset["filename"] == "result.mp4"
    assert module.result_asset_priority(asset, task_type=task_type) == 3


@pytest.mark.parametrize(
    "task_type",
    [
        "minimax_h3_t2v",
        "minimax_h3_i2v",
        "minimax_h3_flf2v",
        "minimax_h3_ref2v",
    ],
)
def test_minimax_h3_result_pick_prefers_video_over_last_frame(
    monkeypatch, task_type
):
    module = build_agent_module(monkeypatch)
    outputs = {
        "last_frame_node": {
            "images": [{"filename": f"{task_type}_42_last_frame_00001.png"}]
        },
        "video_node": {
            "gifs": [{"filename": f"{task_type}_42_video_00001.mp4"}]
        },
    }

    asset = module.pick_first_output_asset(outputs, task_type=task_type)

    assert asset is not None
    assert asset["filename"] == f"{task_type}_42_video_00001.mp4"
    assert module.result_asset_priority(asset, task_type=task_type) == 2


@pytest.mark.parametrize(
    "task_type",
    [
        "scail2_action_transfer",
        "scail2_action_transfer_long",
        "scail2_video_replacement",
        "scail2_face_swap_v2",
    ],
)
def test_scail2_result_pick_prefers_video_over_temp_images(monkeypatch, task_type):
    module = build_agent_module(monkeypatch)
    outputs = {
        "preview_node": {
            "images": [
                {
                    "filename": "ComfyUI_temp_czhcu_00003_.png",
                    "subfolder": "",
                    "type": "temp",
                }
            ]
        },
        "video_node": {
            "gifs": [
                {
                    "filename": "scail2_action_transfer_42_video_00001.mp4",
                    "subfolder": "",
                    "type": "output",
                }
            ]
        },
    }

    asset = module.pick_first_output_asset(outputs, task_type=task_type)

    assert asset is not None
    assert asset["filename"] == "scail2_action_transfer_42_video_00001.mp4"
    assert asset["_asset_key"] == "gifs"
    assert module.result_asset_priority(asset, task_type=task_type) == 2


@pytest.mark.asyncio
async def test_shutdown_before_start_reports_and_closes_clients(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    reported = []

    async def fake_report_status(task_id, status, progress=None, error=None, **kwargs):
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

    async def fake_report_status(task_id, status, progress=None, error=None, **kwargs):
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
async def test_process_task_uses_prefetched_inputs_without_repreparing(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    submitted_params = {}
    completed = []
    memory_events = []

    async def fake_check_task_cancelled(task_id):
        return False

    async def unexpected_prepare_task_inputs(*args, **kwargs):
        raise AssertionError("prefetch hit should skip input preparation")

    async def fake_free_memory():
        memory_events.append("free_memory")

    async def fake_submit_task_workflow(**kwargs):
        submitted_params.update(kwargs["params"])
        kwargs["execution"].prompt_id = "prompt-1"
        kwargs["execution"].task_result = "result.png"

    async def fake_wait_for_task_completion(**kwargs):
        return True

    async def fake_resolve_execution_result_from_history(**kwargs):
        return {}

    async def fake_materialize_task_outputs(**kwargs):
        return SimpleNamespace(
            primary=SimpleNamespace(object_name="result.png"), extra_outputs={}
        )

    async def fake_upload_materialized_outputs(**kwargs):
        return {}

    async def fake_report_materialized_outputs(**kwargs):
        completed.append(kwargs["task_id"])

    agent.check_task_cancelled = fake_check_task_cancelled
    agent._prepare_task_inputs = unexpected_prepare_task_inputs
    agent.comfy_client.free_memory = fake_free_memory
    agent._prefetch_cache["task-1"] = {
        "task_id": "task-1",
        "task_type": "img2img",
        "params": {"image": "prepared.png", "prompt": "cached"},
        "downloaded_input_paths": ["/tmp/not-real-prefetch.png"],
    }
    monkeypatch.setattr(module, "submit_task_workflow", fake_submit_task_workflow)
    monkeypatch.setattr(module, "POOL_RUNTIME_PROFILE", "all")
    monkeypatch.setattr(
        module, "wait_for_task_completion", fake_wait_for_task_completion
    )
    monkeypatch.setattr(
        module,
        "resolve_execution_result_from_history",
        fake_resolve_execution_result_from_history,
    )
    monkeypatch.setattr(
        module, "materialize_task_outputs", fake_materialize_task_outputs
    )
    monkeypatch.setattr(
        module, "upload_materialized_outputs", fake_upload_materialized_outputs
    )
    monkeypatch.setattr(
        module, "report_materialized_outputs", fake_report_materialized_outputs
    )

    await agent.process_task(
        {
            "task_id": "task-1",
            "type": "img2img",
            "params": '{"image": "remote.png", "prompt": "original"}',
        }
    )

    assert submitted_params == {"image": "prepared.png", "prompt": "cached"}
    assert memory_events == ["free_memory"]
    assert completed == ["task-1"]
    assert agent._prefetch_cache == {}


@pytest.mark.asyncio
async def test_process_task_sidecar_upload_failure_reports_failed_without_complete(
    monkeypatch,
):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    reported = []
    completed = []

    async def fake_check_task_cancelled(task_id):
        return False

    async def fake_prepare_task_inputs(*args, **kwargs):
        return None

    async def fake_submit_task_workflow(**kwargs):
        kwargs["execution"].prompt_id = "prompt-1"
        kwargs["execution"].task_result = "result.png"

    async def fake_wait_for_task_completion(**kwargs):
        return True

    async def fake_resolve_execution_result_from_history(**kwargs):
        return {}

    async def fake_materialize_task_outputs(**kwargs):
        return SimpleNamespace(
            primary=SimpleNamespace(object_name="result.png"), extra_outputs={}
        )

    async def fake_spool_materialized_outputs(**kwargs):
        return "spooled"

    async def fake_upload_spooled_outputs_via_sidecar(**kwargs):
        raise RuntimeError("sidecar upload failed")

    async def fake_report_materialized_outputs(**kwargs):
        completed.append(kwargs["task_id"])

    async def fake_report_status(task_id, status, progress=0.0, error="", **kwargs):
        reported.append((task_id, status, error))

    agent.check_task_cancelled = fake_check_task_cancelled
    agent._prepare_task_inputs = fake_prepare_task_inputs
    agent.report_status = fake_report_status
    monkeypatch.setattr(module, "UPLOAD_SIDECAR_URL", "http://127.0.0.1:8013")
    monkeypatch.setattr(module, "submit_task_workflow", fake_submit_task_workflow)
    monkeypatch.setattr(
        module, "wait_for_task_completion", fake_wait_for_task_completion
    )
    monkeypatch.setattr(
        module,
        "resolve_execution_result_from_history",
        fake_resolve_execution_result_from_history,
    )
    monkeypatch.setattr(
        module, "materialize_task_outputs", fake_materialize_task_outputs
    )
    monkeypatch.setattr(
        module, "spool_materialized_outputs", fake_spool_materialized_outputs
    )
    monkeypatch.setattr(
        module,
        "upload_spooled_outputs_via_sidecar",
        fake_upload_spooled_outputs_via_sidecar,
    )
    monkeypatch.setattr(
        module, "report_materialized_outputs", fake_report_materialized_outputs
    )

    await agent.process_task(
        {
            "task_id": "task-1",
            "type": "img2img",
            "params": "{}",
        }
    )

    assert completed == []
    assert reported[-1][0] == "task-1"
    assert reported[-1][1] == "failed"
    assert "Result processing failed" in reported[-1][2]


@pytest.mark.asyncio
async def test_wan22_timeout_interrupts_comfy_and_exits_after_failed_report(
    monkeypatch,
):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    reported = []
    interrupted = []
    exit_codes = []

    async def fake_prepare_task_inputs(*args, **kwargs):
        return None

    async def fake_submit_task_workflow(**kwargs):
        kwargs["execution"].prompt_id = "prompt-timeout"

    async def fake_wait_for_task_completion(**kwargs):
        raise module.TaskExecutionTimeoutError("wan22 timeout")

    async def fake_interrupt():
        interrupted.append(agent._active_execution.prompt_id)
        return True

    async def fake_report_status(task_id, status, progress=0.0, error="", **kwargs):
        reported.append((task_id, status, error))

    def fake_exit(code):
        exit_codes.append(code)
        raise SystemExit(code)

    agent._prepare_task_inputs = fake_prepare_task_inputs
    agent.comfy_client.interrupt = fake_interrupt
    agent.report_status = fake_report_status
    monkeypatch.setattr(module, "WAN22_VIDEO_V2_EXIT_ON_TIMEOUT", True)
    monkeypatch.setattr(module, "WAN22_VIDEO_V2_TIMEOUT_EXIT_CODE", 75)
    monkeypatch.setattr(module.os, "_exit", fake_exit)
    monkeypatch.setattr(module, "submit_task_workflow", fake_submit_task_workflow)
    monkeypatch.setattr(
        module, "wait_for_task_completion", fake_wait_for_task_completion
    )

    with pytest.raises(SystemExit):
        await agent.process_task(
            {
                "task_id": "task-timeout",
                "type": "wan22_video_v2",
                "params": "{}",
            }
        )

    assert interrupted == ["prompt-timeout"]
    assert reported[-1] == ("task-timeout", "failed", "wan22 timeout")
    assert exit_codes == [75]
    assert agent._active_execution is None
    assert agent._executions == {}


@pytest.mark.asyncio
async def test_i2i_pro_quality_issue_requeues_once_before_complete(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    submit_calls = []
    completed = []
    materialize_count = 0

    async def fake_check_task_cancelled(task_id):
        return False

    async def fake_prepare_task_inputs(*, params, downloaded_input_paths, **kwargs):
        params["image"] = "prepared-reference.png"

    async def fake_get_view(filename, subfolder="", type="output"):
        assert filename == "prepared-reference.png"
        assert type == "input"
        return _png_bytes((40, 50, 60))

    async def fake_submit_task_workflow(**kwargs):
        submit_calls.append(dict(kwargs["params"]))
        kwargs["execution"].prompt_id = f"prompt-{len(submit_calls)}"

    async def fake_wait_for_task_completion(**kwargs):
        return True

    async def fake_resolve_execution_result_from_history(**kwargs):
        execution = kwargs["execution"]
        execution.task_result = f"{execution.task_id}__{execution.prompt_id}.png"

    async def fake_materialize_task_outputs(**kwargs):
        nonlocal materialize_count
        materialize_count += 1
        file_data = (
            _png_bytes((0, 0, 0))
            if materialize_count == 1
            else _png_bytes((220, 210, 200))
        )
        return SimpleNamespace(
            primary=SimpleNamespace(
                object_name=kwargs["execution"].task_result,
                content_type="image/png",
                file_data=file_data,
            ),
            extra_outputs={},
        )

    async def fake_upload_materialized_outputs(**kwargs):
        return {}

    async def fake_report_materialized_outputs(**kwargs):
        completed.append(kwargs["result_path"])

    agent.comfy_client.get_view = fake_get_view
    agent.check_task_cancelled = fake_check_task_cancelled
    agent._prepare_task_inputs = fake_prepare_task_inputs
    monkeypatch.setattr(module, "I2I_PRO_QUALITY_RETRY_ATTEMPTS", 1)
    monkeypatch.setattr(module, "submit_task_workflow", fake_submit_task_workflow)
    monkeypatch.setattr(
        module, "wait_for_task_completion", fake_wait_for_task_completion
    )
    monkeypatch.setattr(
        module,
        "resolve_execution_result_from_history",
        fake_resolve_execution_result_from_history,
    )
    monkeypatch.setattr(
        module, "materialize_task_outputs", fake_materialize_task_outputs
    )
    monkeypatch.setattr(
        module, "upload_materialized_outputs", fake_upload_materialized_outputs
    )
    monkeypatch.setattr(
        module, "report_materialized_outputs", fake_report_materialized_outputs
    )

    await agent.process_task(
        {
            "task_id": "task-1",
            "type": "i2i_pro",
            "params": '{"image": "remote.png", "prompt": "demo"}',
        }
    )

    assert len(submit_calls) == 2
    assert submit_calls[0]["image"] == "prepared-reference.png"
    assert submit_calls[1]["image"] == "prepared-reference.png"
    assert submit_calls[1]["seed"] != submit_calls[0].get("seed")
    assert completed == ["task-1__prompt-2.png"]


@pytest.mark.asyncio
async def test_pipeline_launch_schedules_background_finalizer(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    finalizer_started = module.asyncio.Event()
    release_finalizer = module.asyncio.Event()
    completed = []
    submitted = []

    async def fake_prepare_task_inputs(*args, **kwargs):
        return None

    async def fake_submit_task_workflow(**kwargs):
        submitted.append(kwargs["task_id"])
        kwargs["execution"].prompt_id = "prompt-1"
        kwargs["execution"].task_result = "result.png"

    async def fake_wait_for_task_completion(**kwargs):
        finalizer_started.set()
        await release_finalizer.wait()
        return True

    async def fake_resolve_execution_result_from_history(**kwargs):
        return {}

    async def fake_materialize_task_outputs(**kwargs):
        return SimpleNamespace(
            primary=SimpleNamespace(object_name="result.png"), extra_outputs={}
        )

    async def fake_upload_materialized_outputs(**kwargs):
        return {}

    async def fake_report_materialized_outputs(**kwargs):
        completed.append(kwargs["task_id"])

    agent._prepare_task_inputs = fake_prepare_task_inputs
    monkeypatch.setattr(module, "submit_task_workflow", fake_submit_task_workflow)
    monkeypatch.setattr(
        module, "wait_for_task_completion", fake_wait_for_task_completion
    )
    monkeypatch.setattr(
        module,
        "resolve_execution_result_from_history",
        fake_resolve_execution_result_from_history,
    )
    monkeypatch.setattr(
        module, "materialize_task_outputs", fake_materialize_task_outputs
    )
    monkeypatch.setattr(
        module, "upload_materialized_outputs", fake_upload_materialized_outputs
    )
    monkeypatch.setattr(
        module, "report_materialized_outputs", fake_report_materialized_outputs
    )

    await agent._launch_pipeline_task(
        {
            "task_id": "task-1",
            "type": "img2img",
            "params": "{}",
        }
    )

    await module.asyncio.wait_for(finalizer_started.wait(), timeout=1)
    await agent._launch_pipeline_task(
        {
            "task_id": "task-1",
            "type": "img2img",
            "params": "{}",
        }
    )
    assert completed == []
    assert submitted == ["task-1"]
    assert "task-1" in agent._executions
    assert len(agent._execution_tasks) == 1

    background_tasks = list(agent._execution_tasks)
    release_finalizer.set()
    await module.asyncio.gather(*background_tasks)

    assert completed == ["task-1"]
    assert agent._executions == {}


@pytest.mark.asyncio
async def test_ws_events_route_by_prompt_id_without_cross_talk(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    reported = []

    async def fake_report_status(task_id, status, progress=0.0, error="", **kwargs):
        reported.append((task_id, status, progress, kwargs))

    agent.report_status = fake_report_status
    execution_a = agent._start_task_execution(task_id="task-a", task_type="img2img")
    execution_a.prompt_id = "prompt-a"
    agent._register_prompt_execution(execution_a)
    execution_b = agent._start_task_execution(task_id="task-b", task_type="img2img")
    execution_b.prompt_id = "prompt-b"
    agent._register_prompt_execution(execution_b)

    await agent._route_ws_event(
        {
            "type": "executed",
            "data": {
                "prompt_id": "prompt-b",
                "output": {
                    "save": {
                        "images": [
                            {
                                "filename": "result-b.png",
                                "subfolder": "",
                                "type": "output",
                            }
                        ]
                    }
                },
            },
        }
    )
    await agent._route_ws_event(
        {
            "type": "execution_success",
            "data": {"prompt_id": "prompt-b"},
        }
    )

    assert execution_a.task_result is None
    assert execution_a.completed_event.is_set() is False
    assert execution_b.task_result == "task-b__result-b.png"
    assert execution_b.completed_event.is_set() is True
    assert reported == []


@pytest.mark.asyncio
async def test_report_heartbeat_uses_active_execution_context(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    requests = []

    async def fake_post(path, json):
        requests.append((path, json))
        return SimpleNamespace(status_code=200)

    agent.master_client.post = fake_post
    agent._runtime_manifest = {
        "git_sha": "abc123",
        "runtime_package_sha256": "a" * 64,
        "workflow_mapping_sha256": "b" * 64,
    }
    agent._active_execution = module.TaskExecutionContext(
        task_id="task-99",
        task_type="wan22_video_v2",
    )

    await agent.report_heartbeat()

    assert requests[0][0] == "/api/agent/task/heartbeat"
    assert requests[0][1]["status"] == "running"
    assert requests[0][1]["runtime_manifest"]["git_sha"] == "abc123"
    assert requests[1] == (
        "/api/agent/task/task_heartbeat",
        {"task_id": "task-99", "agent_id": module.AGENT_ID},
    )


@pytest.mark.asyncio
async def test_report_heartbeat_sends_error_health_fields(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    requests = []

    async def fake_post(path, json):
        requests.append((path, json))
        return SimpleNamespace(status_code=200)

    agent.master_client.post = fake_post
    agent.is_error_state = True
    agent.consecutive_failures = 3
    agent.health_reason = "comfy_probe_failed"
    agent.last_error = "ComfyUI /system_stats probe failed"
    agent.last_error_at = 123.0

    await agent.report_heartbeat()

    payload = requests[0][1]
    assert payload["status"] == "error"
    assert payload["health_reason"] == "comfy_probe_failed"
    assert payload["last_error"] == "ComfyUI /system_stats probe failed"
    assert payload["last_error_at"] == 123.0
    assert payload["consecutive_failures"] == 3


@pytest.mark.asyncio
async def test_report_heartbeat_sends_null_numeric_health_fields_when_idle(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    requests = []

    async def fake_post(path, json):
        requests.append((path, json))
        return SimpleNamespace(status_code=200)

    agent.master_client.post = fake_post

    await agent.report_heartbeat()

    payload = requests[0][1]
    assert payload["status"] == "idle"
    assert payload["last_error_at"] is None
    assert payload["quarantined_until"] is None


def test_build_pop_params_includes_agent_id_for_drain_control(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()

    params = agent._build_pop_params()

    assert params["agent_id"] == module.AGENT_ID
    assert params["types"] == module.SUPPORTED_TASK_TYPES
    assert "preferred_types" not in params


def test_build_pop_params_includes_configured_preferred_types(monkeypatch):
    monkeypatch.setenv(
        "SUPPORTED_TASK_TYPES",
        "img2img,scail2_face_swap_v2",
    )
    monkeypatch.setenv("PREFERRED_TASK_TYPES", "scail2_face_swap_v2")
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()

    params = agent._build_pop_params()

    assert params["preferred_types"] == "scail2_face_swap_v2"


def test_pipeline_pop_params_omit_preferred_types_outside_pipeline_subset(monkeypatch):
    monkeypatch.setenv(
        "SUPPORTED_TASK_TYPES",
        "img2img,scail2_face_swap_v2",
    )
    monkeypatch.setenv("PREFERRED_TASK_TYPES", "scail2_face_swap_v2")
    monkeypatch.setenv("PIPELINE_TASK_TYPES", "img2img")
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()

    params = agent._build_pop_params(pipeline=True)

    assert params["types"] == "img2img"
    assert "preferred_types" not in params


@pytest.mark.parametrize(
    "module_path",
    (
        ROOT / "workers" / "comfy_agent" / "agent_main.py",
    ),
)
def test_agent_rejects_preferred_types_outside_supported_set(monkeypatch, module_path):
    monkeypatch.setenv("SUPPORTED_TASK_TYPES", "img2img")
    monkeypatch.setenv("PREFERRED_TASK_TYPES", "scail2_face_swap_v2")

    with mock.patch("os.makedirs", return_value=None):
        with pytest.raises(ValueError, match="PREFERRED_TASK_TYPES"):
            load_agent_main_module(module_path)


@pytest.mark.asyncio
async def test_report_heartbeat_includes_pool_metadata(monkeypatch):
    monkeypatch.setenv("POOL_NODE_ID", "gpu-252")
    monkeypatch.setenv("POOL_PROVIDER", "lan_ssh")
    monkeypatch.setenv("POOL_GPU_INDEX", "1")
    monkeypatch.setenv("POOL_RUNTIME_PROFILE", "wan22_video_v2")
    monkeypatch.setenv(
        "POOL_IMAGE_REF", "192.168.1.115:5000/allbot/comfy-cu128-wan22:baseline"
    )
    monkeypatch.setenv(
        "POOL_MODEL_BUNDLE_VERSIONS",
        '{"wan22_video_v2_baseline":"2026-06-10"}',
    )
    monkeypatch.setenv("POOL_MANAGED", "true")
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    requests = []

    async def fake_post(path, json):
        requests.append((path, json))
        return SimpleNamespace(status_code=200)

    agent.master_client.post = fake_post

    await agent.report_heartbeat()

    payload = requests[0][1]
    assert payload["node_id"] == "gpu-252"
    assert payload["provider"] == "lan_ssh"
    assert payload["gpu_index"] == "1"
    assert payload["runtime_profile"] == "wan22_video_v2"
    assert payload["pool_managed"] == "true"


@pytest.mark.asyncio
async def test_report_status_retries_transient_disconnect(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    attempts = []
    sleep_calls = []

    async def fake_post(path, json):
        attempts.append((path, json))
        if len(attempts) < 3:
            raise RuntimeError("server disconnected")
        return SimpleNamespace(status_code=200)

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    agent.master_client.post = fake_post
    monkeypatch.setattr(module, "STATUS_REPORT_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(module, "STATUS_REPORT_RETRY_BASE_SECONDS", 0.25)
    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    await agent.report_status("task-1", "running", progress=0.5)

    assert len(attempts) == 3
    assert attempts[-1] == (
        "/api/agent/task/status",
        {
            "task_id": "task-1",
            "agent_id": module.AGENT_ID,
            "status": "running",
            "progress": 0.5,
            "error": "",
        },
    )
    assert sleep_calls == [0.25, 0.5]


@pytest.mark.asyncio
async def test_report_status_logs_and_swallows_retry_exhaustion(monkeypatch, caplog):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    attempts = []

    async def fake_post(path, json):
        attempts.append((path, json))
        return SimpleNamespace(status_code=503)

    async def fake_sleep(_seconds):
        return None

    agent.master_client.post = fake_post
    monkeypatch.setattr(module, "STATUS_REPORT_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    with caplog.at_level(logging.ERROR):
        await agent.report_status("task-1", "running")

    assert len(attempts) == 2
    assert "Failed to report status for task task-1 after 2 attempts" in caplog.text
    assert agent.control_plane_failures == 2


@pytest.mark.asyncio
async def test_report_complete_retries_transient_disconnect(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    attempts = []
    sleep_calls = []

    async def fake_post(path, json):
        attempts.append((path, json))
        if len(attempts) < 3:
            raise RuntimeError("server disconnected")
        return SimpleNamespace(status_code=200)

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    agent.master_client.post = fake_post
    monkeypatch.setattr(module, "COMPLETE_REPORT_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(module, "COMPLETE_REPORT_RETRY_BASE_SECONDS", 0.25)
    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    await agent.report_complete(
        "task-1",
        "task-1__result.png",
        extra_outputs={"mask": {"path": "mask.png"}},
    )

    assert len(attempts) == 3
    assert attempts[-1] == (
        "/api/agent/task/complete",
        {
            "task_id": "task-1",
            "agent_id": module.AGENT_ID,
            "result": "task-1__result.png",
            "extra_outputs": {"mask": {"path": "mask.png"}},
        },
    )
    assert sleep_calls == [0.25, 0.5]


@pytest.mark.asyncio
async def test_report_complete_raises_after_retry_exhaustion(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    attempts = []

    async def fake_post(path, json):
        attempts.append((path, json))
        return SimpleNamespace(status_code=503)

    async def fake_sleep(_seconds):
        return None

    agent.master_client.post = fake_post
    monkeypatch.setattr(module, "COMPLETE_REPORT_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    with pytest.raises(RuntimeError, match="Failed to report completion"):
        await agent.report_complete("task-1", "task-1__result.png")

    assert len(attempts) == 2
    assert agent.control_plane_failures == 2


@pytest.mark.asyncio
async def test_poll_loop_marks_error_and_does_not_pop_when_comfy_unhealthy(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    agent.running = True
    sleep_calls = []
    master_get_called = False

    async def fake_probe():
        return False

    async def fake_get(*args, **kwargs):
        nonlocal master_get_called
        master_get_called = True
        return SimpleNamespace(status_code=404)

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= module.COMFY_HEALTH_FAILURE_THRESHOLD:
            agent.running = False

    agent._probe_comfy_ready = fake_probe
    agent.master_client.get = fake_get
    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    await agent.poll_loop()

    assert agent.is_error_state is True
    assert agent.consecutive_failures == module.COMFY_HEALTH_FAILURE_THRESHOLD
    assert master_get_called is False
    assert sleep_calls[-1] == module.COMFY_ERROR_POLL_SECONDS


@pytest.mark.asyncio
async def test_poll_loop_recovers_after_required_successful_probes(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    agent.running = True
    probes = [False, False, False, True, True]
    master_get_called = False

    async def fake_probe():
        return probes.pop(0) if probes else True

    async def fake_get(*args, **kwargs):
        nonlocal master_get_called
        master_get_called = True
        agent.running = False
        return SimpleNamespace(status_code=404)

    async def fake_sleep(_seconds):
        return None

    agent._probe_comfy_ready = fake_probe
    agent.master_client.get = fake_get
    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    await agent.poll_loop()

    assert master_get_called is True
    assert agent.is_error_state is False
    assert agent.consecutive_failures == 0


def test_task_infra_failures_enter_and_clear_quarantine(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()

    for _ in range(module.COMFY_TASK_INFRA_FAILURE_THRESHOLD):
        agent._record_task_failure_for_health(RuntimeError("ComfyUI upload timeout"))

    assert agent._worker_status() == "quarantined"
    assert agent.health_reason == "task_infra_failures"
    assert agent.last_error == "ComfyUI upload timeout"

    agent.quarantined_until = agent._now() - 1
    agent._clear_expired_quarantine()

    assert agent._worker_status() == "idle"
    assert agent.task_infra_failures == 0
    assert agent.last_error == ""


def test_control_plane_success_resets_failure_window(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()

    agent._record_control_plane_failure("relay failed")
    assert agent.control_plane_failures == 1
    assert agent.control_plane_last_error == "relay failed"

    agent._record_control_plane_success()

    assert agent.control_plane_failures == 0
    assert agent.control_plane_failure_started_at is None
    assert agent.control_plane_last_error == ""


def test_control_plane_failures_request_process_recovery(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()

    monkeypatch.setattr(module, "AGENT_CONTROL_PLANE_RECOVERY_MIN_FAILURES", 2)
    monkeypatch.setattr(module, "AGENT_CONTROL_PLANE_RECOVERY_SECONDS", 0)

    agent._record_control_plane_failure("first failure")
    with pytest.raises(module.ControlPlaneRecoveryExit):
        agent._record_control_plane_failure("second failure")

    assert agent.control_plane_recovery_requested is True
    assert agent.running is False
    assert agent.control_plane_failures == 2


def test_user_input_failure_does_not_count_toward_quarantine(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()

    agent._record_task_failure_for_health(
        RuntimeError("Downloaded file is not a valid image: /tmp/bad.txt")
    )

    assert agent.task_infra_failures == 0
    assert agent._worker_status() == "idle"


@pytest.mark.asyncio
async def test_ws_disconnect_fails_active_task_when_http_probe_fails(monkeypatch):
    module = build_agent_module(monkeypatch)
    agent = module.ComfyAgent()
    execution = module.TaskExecutionContext(
        task_id="task-ws",
        task_type="img2img",
        prompt_id="prompt-ws",
    )
    agent._active_execution = execution

    async def fake_probe():
        return False

    async def fake_sleep(_seconds):
        return None

    agent._probe_comfy_ready = fake_probe
    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)

    await agent._handle_ws_connection_error("lost")

    assert execution.completed_event.is_set() is True
    assert "ComfyUI service lost during execution" in execution.task_error
    assert agent.health_reason == "comfy_ws_lost"


@pytest.mark.asyncio
async def test_wait_for_task_completion_finishes_from_history_probe(monkeypatch):
    module = build_agent_module(monkeypatch)
    execution = module.TaskExecutionContext(
        task_id="task-1",
        task_type="img2img",
        prompt_id="prompt-1",
    )

    class FakeComfyClient:
        async def get_history(self, prompt_id):
            return {
                prompt_id: {
                    "outputs": {
                        "save": {
                            "images": [
                                {
                                    "filename": "result.png",
                                    "subfolder": "",
                                    "type": "output",
                                }
                            ]
                        }
                    }
                }
            }

    async def fake_check_task_cancelled(task_id):
        return False

    completed = await module.wait_for_task_completion(
        task_id="task-1",
        execution=execution,
        check_task_cancelled_func=fake_check_task_cancelled,
        logger=logging.getLogger("test"),
        comfy_client=FakeComfyClient(),
        task_type="img2img",
        history_probe_start_seconds=0,
        history_probe_interval_seconds=0.01,
        timeout_seconds=1,
    )

    assert completed is True
    assert execution.completed_event.is_set() is True
    assert execution.task_result == "task-1__result.png"


@pytest.mark.asyncio
async def test_wait_for_task_completion_cancel_stops_before_history_probe(monkeypatch):
    module = build_agent_module(monkeypatch)
    execution = module.TaskExecutionContext(
        task_id="task-1",
        task_type="img2img",
        prompt_id="prompt-1",
    )

    class UnexpectedComfyClient:
        async def get_history(self, prompt_id):
            raise AssertionError("history should not be probed after cancellation")

    async def fake_check_task_cancelled(task_id):
        return True

    completed = await module.wait_for_task_completion(
        task_id="task-1",
        execution=execution,
        check_task_cancelled_func=fake_check_task_cancelled,
        logger=logging.getLogger("test"),
        comfy_client=UnexpectedComfyClient(),
        task_type="img2img",
        history_probe_start_seconds=0,
        history_probe_interval_seconds=0.01,
        timeout_seconds=1,
    )

    assert completed is False
    assert execution.completed_event.is_set() is False


@pytest.mark.asyncio
async def test_wait_for_task_completion_timeout_raises_after_final_history_probe(
    monkeypatch,
):
    module = build_agent_module(monkeypatch)
    execution = module.TaskExecutionContext(
        task_id="task-1",
        task_type="wan22_video_v2",
        prompt_id="prompt-1",
    )
    history_calls = []

    class EmptyHistoryComfyClient:
        async def get_history(self, prompt_id):
            history_calls.append(prompt_id)
            return {}

    async def fake_check_task_cancelled(task_id):
        return False

    with pytest.raises(module.TaskExecutionTimeoutError) as exc:
        await module.wait_for_task_completion(
            task_id="task-1",
            execution=execution,
            check_task_cancelled_func=fake_check_task_cancelled,
            logger=logging.getLogger("test"),
            comfy_client=EmptyHistoryComfyClient(),
            task_type="wan22_video_v2",
            history_probe_start_seconds=999,
            history_probe_interval_seconds=0.01,
            timeout_seconds=0.01,
        )

    assert "without ComfyUI history result" in str(exc.value)
    assert history_calls == ["prompt-1"]
    assert execution.completed_event.is_set() is False
