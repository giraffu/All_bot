import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = ROOT / "workers" / "comfy_agent"
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

from agent_artifact_lifecycle import ComfyArtifactRef  # noqa: E402
from agent_finalizer import AgentFinalizer  # noqa: E402
from agent_runtime_types import TaskExecutionContext  # noqa: E402


class _DeliveryGate:
    @asynccontextmanager
    async def slot(self):
        yield


class _FakeAgent:
    def __init__(self):
        self._delivery_gate = _DeliveryGate()
        self.cleaned_artifact_batches = []
        self.cleaned_local_inputs = []
        self.statuses = []
        self.errors = []
        self.comfy_client = SimpleNamespace()
        self.minio_client = SimpleNamespace()

    async def check_task_cancelled(self, _task_id):
        return False

    async def report_status(self, task_id, status, **kwargs):
        self.statuses.append((task_id, status, kwargs))

    async def report_complete(self, *_args, **_kwargs):
        return None

    def _completion_timeout_seconds_for_task(self, _task_type):
        return 30.0

    def _record_task_success_for_health(self):
        return None

    def _record_task_failure_for_health(self, _exc):
        return None

    def _clear_task_execution(self, _execution):
        return None

    def _cleanup_input_paths(self, paths):
        self.cleaned_local_inputs.append(list(paths))

    def _cleanup_comfy_artifacts(self, artifacts):
        self.cleaned_artifact_batches.append(list(artifacts))


def _execution():
    execution = TaskExecutionContext(task_id="task-1", task_type="img2img")
    execution.prompt_id = "prompt-1"
    execution.task_result = "result.png"
    execution.downloaded_input_paths = ["/tmp/local-input.png"]
    execution.comfy_input_artifacts = [
        ComfyArtifactRef(kind="input", filename="prepared.png")
    ]
    return execution


async def _noop_async(**_kwargs):
    return None


async def _run_finalizer(agent, execution, *, report_outputs):
    output_ref = ComfyArtifactRef(kind="output", filename="result.png")
    outputs = SimpleNamespace(
        primary=SimpleNamespace(object_name="result.png"),
        extra_outputs={},
        source_artifacts=[output_ref],
    )

    async def wait_for_task_completion(**_kwargs):
        return True

    async def materialize(**_kwargs):
        return outputs

    async def assess(**_kwargs):
        return None

    async def spool(**_kwargs):
        return SimpleNamespace()

    async def upload(**_kwargs):
        return {"result_path": "staging/worker-results/task-1/primary.png"}

    await AgentFinalizer(
        agent=agent,
        logger=SimpleNamespace(
            info=lambda *_args, **_kwargs: None,
            warning=lambda *_args, **_kwargs: None,
            error=lambda *args, **_kwargs: agent.errors.append(args),
        ),
    ).finalize_execution(
        execution,
        cancel_lock_on_pop=True,
        upload_sidecar_url="http://relay",
        result_spool_dir="/tmp/spool",
        result_bucket="test",
        wan22_timeout_exit_code=75,
        quality_retry_attempts=0,
        agent_id="agent-1",
        submit_task_workflow_func=_noop_async,
        wait_for_task_completion_func=wait_for_task_completion,
        resolve_execution_result_from_history_func=_noop_async,
        materialize_task_outputs_func=materialize,
        assess_materialized_output_quality_func=assess,
        spool_materialized_outputs_func=spool,
        upload_spooled_outputs_via_sidecar_func=upload,
        upload_materialized_outputs_func=upload,
        report_materialized_outputs_func=report_outputs,
    )
    return output_ref


@pytest.mark.asyncio
async def test_finalizer_cleans_comfy_output_only_after_central_complete_confirmation():
    agent = _FakeAgent()
    execution = _execution()

    async def report_outputs(**_kwargs):
        assert agent.cleaned_artifact_batches == []

    output_ref = await _run_finalizer(agent, execution, report_outputs=report_outputs)

    assert agent.cleaned_artifact_batches == [
        [output_ref],
        execution.comfy_input_artifacts,
    ], agent.errors
    assert agent.cleaned_local_inputs == [["/tmp/local-input.png"]]


@pytest.mark.asyncio
async def test_finalizer_preserves_comfy_output_when_complete_confirmation_fails():
    agent = _FakeAgent()
    execution = _execution()

    async def report_outputs(**_kwargs):
        raise RuntimeError("Central unavailable")

    await _run_finalizer(agent, execution, report_outputs=report_outputs)

    assert agent.cleaned_artifact_batches == [execution.comfy_input_artifacts]
    assert agent.statuses[-1][1] == "failed"
