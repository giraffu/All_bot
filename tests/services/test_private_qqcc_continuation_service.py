import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import private_qqcc_continuation_service as continuation_service
from src.services.private_bot_update_admission import (
    PrivateBotUpdateAdmissionScope,
    activate_private_bot_update_scope,
    next_private_bot_submission_key,
)
from src.services.private_qqcc_continuation_service import (
    PrivateQqccContinuationCheckpoint,
    PrivateQqccContinuationConflict,
    PrivateQqccContinuationTaskRef,
    PrivateQqccContinuationUnavailable,
    RedisPrivateQqccContinuationStore,
    activate_private_qqcc_continuation_task,
    build_private_qqcc_continuation_registry_metadata,
    create_private_qqcc_continuation,
    execute_private_qqcc_continuation_stage_default,
    list_private_qqcc_continuations_for_recovery,
    normalize_private_qqcc_continuation_task_ref,
    persist_private_qqcc_continuation_input,
    private_bot_has_nonterminal_continuations,
    resume_private_qqcc_continuation,
)


@pytest.mark.asyncio
async def test_private_continuation_ltx_executor_resumes_with_original_and_current_frame():
    checkpoint = SimpleNamespace(
        original_input_ref="durable/original.png",
        current_output_ref="durable/tail.png",
        chat_id=456,
        telegram_user_id=123,
        username="tester",
        status_message_id=77,
    )
    stage = {
        "executor": "ltx_video",
        "input_mode": "original_current",
        "task_kwargs": {
            "prompt": "camera orbit",
            "negative_prompt": "blur",
            "ltx_mode": "flf2v",
            "duration": "10s",
            "send_result": True,
        },
    }
    ref = PrivateQqccContinuationTaskRef(
        chain_id="chain-1",
        stage_index=1,
        submission_sequence=2,
        registry_task_id="task-ltx",
        executor_token="token",
    )
    ltx_task = AsyncMock(return_value=(b"video", "results/video.mp4"))

    context = SimpleNamespace()
    result = await execute_private_qqcc_continuation_stage_default(
        checkpoint,
        stage,
        ref,
        context,
        process_ltx_video_task_func=ltx_task,
    )

    assert result == (b"video", "results/video.mp4")
    assert ltx_task.await_args.kwargs == {
        "context": context,
        "chat_id": 456,
        "user_id": 123,
        "username": "tester",
        "image_path": "durable/original.png",
        "end_image_path": "durable/tail.png",
        "status_msg_id": 77,
        "prompt": "camera orbit",
        "negative_prompt": "blur",
        "ltx_mode": "flf2v",
        "duration": "10s",
        "send_result": True,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("executor", ["generation", "legacy_video"])
async def test_private_video_executor_restores_aspect_policy_without_leaking_internal_kwarg(
    executor,
):
    checkpoint = SimpleNamespace(
        original_input_ref="durable/original.png",
        current_output_ref="durable/tail.png",
        chat_id=456,
        telegram_user_id=123,
        username="tester",
        status_message_id=77,
    )
    stage = {
        "executor": executor,
        "input_mode": "original_current",
        "task_kwargs": {
            "task_type": "wan22_video_v2",
            "_qqcc_aspect_ratio": "9:16",
            "cleanup": True,
        },
    }
    ref = PrivateQqccContinuationTaskRef(
        chain_id="chain-video",
        stage_index=1,
        submission_sequence=2,
        registry_task_id="task-video",
        executor_token="token",
    )
    generation_task = AsyncMock(return_value=(b"video", "results/video.mp4"))
    legacy_task = AsyncMock(return_value=(b"video", "results/video.mp4"))
    cleanup_calls = []

    async def download_frame(*, output_file, suffix, name_hint):
        del suffix, name_hint
        return f"/tmp/{output_file.rsplit('/', 1)[-1]}"

    def adapt_frame(path, *, aspect_ratio):
        assert aspect_ratio == "9:16"
        return path.replace(".png", "-portrait.png")

    await execute_private_qqcc_continuation_stage_default(
        checkpoint,
        stage,
        ref,
        SimpleNamespace(),
        process_generation_task_func=generation_task,
        process_video_task_template_func=legacy_task,
        download_video_frame_to_fsm_temp_func=download_frame,
        adapt_video_frame_file_func=adapt_frame,
        cleanup_temp_files_func=lambda paths: cleanup_calls.extend(paths),
    )

    task = generation_task if executor == "generation" else legacy_task
    kwargs = task.await_args.kwargs
    assert "_qqcc_aspect_ratio" not in kwargs
    if executor == "generation":
        assert kwargs["images"] == [
            "/tmp/original-portrait.png",
            "/tmp/tail-portrait.png",
        ]
    else:
        assert kwargs["image_path"] == "/tmp/original-portrait.png"
        assert kwargs["end_image_path"] == "/tmp/tail-portrait.png"
    assert cleanup_calls == ["/tmp/original.png", "/tmp/tail.png"]


class MemoryContinuationStore:
    def __init__(self):
        self.items: dict[str, PrivateQqccContinuationCheckpoint] = {}
        self.locked: set[str] = set()
        self.renew_count = 0
        self.renew_ok = True
        self.events: list[str] = []

    async def create(self, checkpoint):
        existing = self.items.get(checkpoint.chain_id)
        if existing is not None:
            if existing.plan_sha256 != checkpoint.plan_sha256:
                raise PrivateQqccContinuationConflict("plan changed")
            return existing
        self.items[checkpoint.chain_id] = checkpoint
        return checkpoint

    async def get(self, chain_id):
        return self.items.get(chain_id)

    async def list_all(self, *, tolerate_corrupt=False):
        del tolerate_corrupt
        return list(self.items.values())

    async def mark_running(
        self,
        *,
        chain_id,
        stage_index,
        submission_sequence,
        registry_task_id,
        executor_token,
    ):
        checkpoint = self.items[chain_id]
        if (
            checkpoint.status != "ready"
            or checkpoint.next_stage_index != stage_index
            or checkpoint.next_submission_sequence != submission_sequence
        ):
            raise PrivateQqccContinuationConflict("stage not ready")
        checkpoint = replace(
            checkpoint,
            status="running",
            current_stage_index=stage_index,
            current_submission_sequence=submission_sequence,
            current_registry_task_id=registry_task_id,
            current_executor_token=executor_token,
            next_submission_sequence=submission_sequence + 1,
        )
        self.items[chain_id] = checkpoint
        return checkpoint

    async def record_completed_stage(
        self,
        *,
        ref,
        output_file,
        saved_inputs,
        last_frame_output_file=None,
    ):
        self.events.append(f"result:{ref.stage_index}")
        checkpoint = self.items[ref.chain_id]
        if checkpoint.next_stage_index > ref.stage_index:
            return checkpoint
        if (
            checkpoint.status != "running"
            or checkpoint.current_stage_index != ref.stage_index
            or checkpoint.current_registry_task_id != ref.registry_task_id
            or checkpoint.current_executor_token != ref.executor_token
        ):
            raise PrivateQqccContinuationConflict("stage mismatch")
        next_stage = ref.stage_index + 1
        delivery_required = bool(
            checkpoint.stages[ref.stage_index].get("delivery_required")
        )
        is_video_segment = bool(
            checkpoint.stages[ref.stage_index].get("qqcc_video_segment")
        )
        if is_video_segment and not last_frame_output_file:
            raise PrivateQqccContinuationConflict("video segment needs last frame")
        video_outputs = checkpoint.video_segment_output_refs
        if is_video_segment:
            video_outputs = (*video_outputs, str(output_file))
        current_output = str(output_file)
        if is_video_segment and not delivery_required:
            current_output = str(last_frame_output_file)
        checkpoint = replace(
            checkpoint,
            status=(
                "delivery_pending"
                if delivery_required
                else (
                    "completed"
                    if next_stage >= len(checkpoint.stages)
                    else "ready"
                )
            ),
            next_stage_index=(
                checkpoint.next_stage_index if delivery_required else next_stage
            ),
            original_input_ref=(
                str(saved_inputs[0])
                if ref.stage_index == 0 and saved_inputs
                else checkpoint.original_input_ref
            ),
            original_input_durable=(
                True
                if ref.stage_index == 0 and saved_inputs
                else checkpoint.original_input_durable
            ),
            current_output_ref=current_output,
            current_segment_start_ref=(
                str(last_frame_output_file)
                if is_video_segment
                else checkpoint.current_segment_start_ref
            ),
            video_segment_output_refs=video_outputs,
            current_stage_index=(None if not delivery_required else ref.stage_index),
            current_submission_sequence=(
                None if not delivery_required else ref.submission_sequence
            ),
            current_registry_task_id=(
                None if not delivery_required else ref.registry_task_id
            ),
            current_executor_token=None,
        )
        self.items[ref.chain_id] = checkpoint
        return checkpoint

    async def claim_delivery(
        self,
        *,
        chain_id,
        stage_index,
        registry_task_id,
        executor_token,
    ):
        checkpoint = self.items[chain_id]
        if (
            checkpoint.status not in {"delivery_pending", "partial_delivery_pending"}
            or checkpoint.current_stage_index != stage_index
            or checkpoint.current_registry_task_id != registry_task_id
            or chain_id not in self.locked
        ):
            raise PrivateQqccContinuationConflict("delivery not claimable")
        checkpoint = replace(
            checkpoint,
            current_executor_token=executor_token,
        )
        self.items[chain_id] = checkpoint
        return checkpoint

    async def mark_delivered(self, *, ref):
        self.events.append(f"delivered:{ref.stage_index}")
        checkpoint = self.items[ref.chain_id]
        if (
            checkpoint.status not in {"delivery_pending", "partial_delivery_pending"}
            or checkpoint.current_stage_index != ref.stage_index
            or checkpoint.current_registry_task_id != ref.registry_task_id
            or checkpoint.current_executor_token != ref.executor_token
        ):
            raise PrivateQqccContinuationConflict("delivery mismatch")
        next_stage = (
            len(checkpoint.stages)
            if checkpoint.status == "partial_delivery_pending"
            else ref.stage_index + 1
        )
        checkpoint = replace(
            checkpoint,
            status=(
                "completed" if next_stage >= len(checkpoint.stages) else "ready"
            ),
            next_stage_index=next_stage,
            current_stage_index=None,
            current_submission_sequence=None,
            current_registry_task_id=None,
            current_executor_token=None,
        )
        self.items[ref.chain_id] = checkpoint
        return checkpoint

    async def rewind_orphaned_stage(self, *, chain_id):
        checkpoint = self.items[chain_id]
        if checkpoint.status != "running":
            return checkpoint
        checkpoint = replace(
            checkpoint,
            status="ready",
            next_stage_index=checkpoint.current_stage_index,
            next_submission_sequence=checkpoint.current_submission_sequence,
            current_stage_index=None,
            current_submission_sequence=None,
            current_registry_task_id=None,
            current_executor_token=None,
        )
        self.items[chain_id] = checkpoint
        return checkpoint

    async def mark_failed(self, *, ref, error_code):
        checkpoint = self.items[ref.chain_id]
        if (
            checkpoint.status != "running"
            or checkpoint.current_stage_index != ref.stage_index
            or checkpoint.current_registry_task_id != ref.registry_task_id
            or checkpoint.current_executor_token != ref.executor_token
        ):
            raise PrivateQqccContinuationConflict("failure fence mismatch")
        checkpoint = replace(
            checkpoint,
            status="failed",
            error_code=error_code,
        )
        self.items[ref.chain_id] = checkpoint
        return checkpoint

    async def mark_partial_delivery_pending(self, *, ref, error_code):
        checkpoint = self.items[ref.chain_id]
        if (
            checkpoint.status != "running"
            or checkpoint.current_stage_index != ref.stage_index
            or checkpoint.current_registry_task_id != ref.registry_task_id
            or checkpoint.current_executor_token != ref.executor_token
            or not checkpoint.video_segment_output_refs
        ):
            raise PrivateQqccContinuationConflict("partial delivery fence mismatch")
        checkpoint = replace(
            checkpoint,
            status="partial_delivery_pending",
            error_code=error_code,
            current_output_ref=checkpoint.video_segment_output_refs[-1],
            current_executor_token=None,
        )
        self.items[ref.chain_id] = checkpoint
        return checkpoint

    async def acquire_lock(self, chain_id):
        if chain_id in self.locked:
            return None
        self.locked.add(chain_id)
        return "lock-token"

    async def renew_lock(self, chain_id, token):
        self.renew_count += 1
        return (
            self.renew_ok
            and chain_id in self.locked
            and token == "lock-token"
        )

    async def release_lock(self, chain_id, token):
        if token:
            self.locked.discard(chain_id)


class ScanRedis:
    def __init__(self, values):
        self.values = values

    async def scan_iter(self, *, match, count):
        del match, count
        for key in self.values:
            yield key

    async def get(self, key):
        return self.values.get(key)


def _stages():
    return [
        {
            "executor": "generation",
            "input_mode": "current",
            "task_kwargs": {"task_type": "edit", "send_result": False},
        },
        {
            "executor": "generation",
            "input_mode": "current_original",
            "task_kwargs": {"task_type": "face_swap_v2", "send_result": True},
        },
    ]


@pytest.mark.asyncio
async def test_legacy_private_qqcc_face_swap_stage_resumes_as_v2():
    checkpoint = SimpleNamespace(
        original_input_ref="durable/original.png",
        current_output_ref="durable/body.png",
        chat_id=456,
        telegram_user_id=123,
        username="tester",
        status_message_id=77,
    )
    stage = {
        "executor": "generation",
        "input_mode": "current_original",
        "task_kwargs": {"task_type": "face_swap", "send_result": True},
    }
    ref = PrivateQqccContinuationTaskRef(
        chain_id="chain-legacy",
        stage_index=1,
        submission_sequence=2,
        registry_task_id="task-face",
        executor_token="token",
    )
    process_task = AsyncMock(return_value=(b"image", "results/face.png"))

    await execute_private_qqcc_continuation_stage_default(
        checkpoint,
        stage,
        ref,
        SimpleNamespace(),
        process_generation_task_func=process_task,
    )

    assert process_task.await_args.kwargs["task_type"] == "face_swap_v2"


def test_continuation_task_ref_round_trips_through_registry_metadata():
    ref = PrivateQqccContinuationTaskRef(
        chain_id="chain-1",
        stage_index=2,
        submission_sequence=4,
        registry_task_id="registry-1",
        executor_token="executor-1",
    )
    with activate_private_qqcc_continuation_task(ref):
        metadata = build_private_qqcc_continuation_registry_metadata()

    assert normalize_private_qqcc_continuation_task_ref(metadata) == ref
    assert build_private_qqcc_continuation_registry_metadata() == {}


def test_continuation_checkpoint_round_trip_preserves_queue_presentation_policy():
    checkpoint = PrivateQqccContinuationCheckpoint(
        version=continuation_service.PRIVATE_QQCC_CONTINUATION_VERSION,
        chain_id="chain-presentation",
        plan_sha256="sha256",
        stages=(
            {
                "executor": "generation",
                "input_mode": "current",
                "task_kwargs": {"show_queue_status": True},
            },
            {
                "executor": "ltx_video",
                "input_mode": "original_current",
                "task_kwargs": {"show_queue_status": False},
            },
        ),
        original_input_ref="inputs/original.png",
        original_input_durable=True,
        current_output_ref=None,
        private_bot_id=7,
        update_id=100,
        chat_id=200,
        telegram_user_id=300,
        username="visitor",
        language_code="zh",
        status_message_id=400,
        status="ready",
        next_stage_index=0,
        next_submission_sequence=0,
        current_stage_index=None,
        current_submission_sequence=None,
        current_registry_task_id=None,
        current_executor_token=None,
        error_code=None,
    )

    restored = continuation_service._checkpoint_from_json(
        continuation_service._checkpoint_to_json(checkpoint)
    )

    assert restored.stages[0]["task_kwargs"]["show_queue_status"] is True
    assert restored.stages[1]["task_kwargs"]["show_queue_status"] is False


@pytest.mark.asyncio
async def test_continuation_checkpoint_rejects_cross_tenant_application_context():
    store = MemoryContinuationStore()
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=100)
    with activate_private_bot_update_scope(scope):
        with pytest.raises(
            PrivateQqccContinuationConflict,
            match="does not match checkpoint",
        ):
            await create_private_qqcc_continuation(
                stages=[_stages()[0]],
                original_input_ref="inputs/original.png",
                original_input_durable=True,
                context=SimpleNamespace(
                    lang="zh",
                    bot_data={"private_qqcc_bot_id": 8},
                ),
                chat_id=200,
                telegram_user_id=300,
                username="visitor",
                status_message_id=None,
                store=store,
            )

    assert store.items == {}


@pytest.mark.asyncio
async def test_two_stage_continuation_advances_durably_with_deterministic_sequences():
    store = MemoryContinuationStore()
    context = SimpleNamespace(lang="zh")
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=101)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=_stages(),
            original_input_ref="/tmp/original.png",
            context=context,
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=400,
            store=store,
        )

        calls = []

        async def execute_stage(checkpoint_value, stage, ref, _context):
            assert next_private_bot_submission_key() == (
                f"private_bot_update:7:101:{ref.submission_sequence}"
            )
            calls.append(
                {
                    "stage": ref.stage_index,
                    "sequence": ref.submission_sequence,
                    "registry_task_id": ref.registry_task_id,
                    "original": checkpoint_value.original_input_ref,
                    "current": checkpoint_value.current_output_ref,
                    "input_mode": stage["input_mode"],
                }
            )
            output = f"outputs/stage-{ref.stage_index}.png"
            await store.record_completed_stage(
                ref=ref,
                output_file=output,
                saved_inputs=(
                    ["inputs/original.png"] if ref.stage_index == 0 else []
                ),
            )
            return b"image", output

        async def deliver_result(_checkpoint, _stage, ref, _context, media_bytes):
            assert media_bytes == b"image"
            store.events.append(f"send:{ref.stage_index}")

        completed = await resume_private_qqcc_continuation(
            chain_id=checkpoint.chain_id,
            context=context,
            store=store,
            execute_stage_func=execute_stage,
            deliver_result_func=deliver_result,
        )

    assert completed.status == "completed"
    assert completed.next_stage_index == 2
    assert completed.original_input_ref == "inputs/original.png"
    assert completed.current_output_ref == "outputs/stage-1.png"
    assert [(item["stage"], item["sequence"]) for item in calls] == [(0, 0), (1, 1)]
    assert calls[1]["original"] == "inputs/original.png"
    assert calls[1]["current"] == "outputs/stage-0.png"
    assert scope._task_sequence == 2
    assert store.events == ["result:0", "result:1", "send:1", "delivered:1"]


@pytest.mark.asyncio
async def test_delivery_pending_recovery_sends_persisted_result_without_rerunning_stage(
    monkeypatch,
):
    store = MemoryContinuationStore()
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=105)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=[_stages()[1]],
            original_input_ref="inputs/original.png",
            original_input_durable=True,
            context=SimpleNamespace(lang="zh"),
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=None,
            store=store,
        )
    running = await store.mark_running(
        chain_id=checkpoint.chain_id,
        stage_index=0,
        submission_sequence=0,
        registry_task_id="registry-final",
        executor_token="old-executor",
    )
    await store.record_completed_stage(
        ref=PrivateQqccContinuationTaskRef(
            chain_id=checkpoint.chain_id,
            stage_index=0,
            submission_sequence=0,
            registry_task_id="registry-final",
            executor_token=running.current_executor_token,
        ),
        output_file="outputs/final.png",
        saved_inputs=["inputs/original.png"],
    )
    executed = False

    async def execute_stage(*_args):
        nonlocal executed
        executed = True
        return b"unexpected", "outputs/unexpected.png"

    delivered_payloads = []

    async def deliver_result(_checkpoint, _stage, _ref, _context, media_bytes):
        delivered_payloads.append(media_bytes)

    monkeypatch.setattr(
        continuation_service,
        "_load_continuation_output_bytes",
        AsyncMock(return_value=b"persisted"),
    )

    completed = await resume_private_qqcc_continuation(
        chain_id=checkpoint.chain_id,
        context=SimpleNamespace(lang="zh"),
        store=store,
        execute_stage_func=execute_stage,
        deliver_result_func=deliver_result,
    )

    assert completed.status == "completed"
    assert executed is False
    assert delivered_payloads == [b"persisted"]


@pytest.mark.asyncio
async def test_later_chain_failure_delivers_saved_prefix_once_without_rerunning(
    monkeypatch,
):
    store = MemoryContinuationStore()
    stages = [
        {
            "executor": "legacy_video",
            "input_mode": "current",
            "delivery_required": False,
            "qqcc_video_segment": True,
            "task_kwargs": {},
        },
        {
            "executor": "legacy_video",
            "input_mode": "current",
            "delivery_required": True,
            "qqcc_video_segment": True,
            "task_kwargs": {
                "_qqcc_chain_delivery": {
                    "mode": "video",
                    "segments": [{"scene_id": "a"}, {"scene_id": "b"}],
                }
            },
        },
    ]
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=205)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=stages,
            original_input_ref="inputs/original.png",
            original_input_durable=True,
            context=SimpleNamespace(lang="zh"),
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=None,
            store=store,
        )
    checkpoint = replace(
        checkpoint,
        next_stage_index=1,
        next_submission_sequence=1,
        current_output_ref="frames/segment-1-last.png",
        current_segment_start_ref="frames/segment-1-last.png",
        video_segment_output_refs=("outputs/segment-1.mp4",),
    )
    store.items[checkpoint.chain_id] = checkpoint

    execution_count = 0
    delivered = []

    async def fail_second_segment(*_args):
        nonlocal execution_count
        execution_count += 1
        raise RuntimeError("provider failed after refund")

    async def deliver_result(delivery_checkpoint, stage, _ref, _context, media_bytes):
        delivered.append(
            (
                delivery_checkpoint.status,
                stage["task_kwargs"]["_qqcc_chain_delivery"]["mode"],
                media_bytes,
            )
        )

    monkeypatch.setattr(
        continuation_service,
        "_load_continuation_output_bytes",
        AsyncMock(return_value=b"saved-prefix"),
    )
    completed = await resume_private_qqcc_continuation(
        chain_id=checkpoint.chain_id,
        context=SimpleNamespace(lang="zh"),
        store=store,
        execute_stage_func=fail_second_segment,
        deliver_result_func=deliver_result,
    )

    assert completed.status == "completed"
    assert completed.error_code == "RuntimeError"
    assert completed.video_segment_output_refs == ("outputs/segment-1.mp4",)
    assert execution_count == 1
    assert delivered == [("partial_delivery_pending", "video", b"saved-prefix")]

    resumed = await resume_private_qqcc_continuation(
        chain_id=checkpoint.chain_id,
        context=SimpleNamespace(lang="zh"),
        store=store,
        execute_stage_func=fail_second_segment,
        deliver_result_func=deliver_result,
    )
    assert resumed.status == "completed"
    assert execution_count == 1
    assert len(delivered) == 1


@pytest.mark.asyncio
async def test_send_then_mark_failure_retries_delivery_without_rerunning_generation(
    monkeypatch,
):
    store = MemoryContinuationStore()
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=108)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=[_stages()[1]],
            original_input_ref="inputs/original.png",
            original_input_durable=True,
            context=SimpleNamespace(lang="zh"),
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=None,
            store=store,
        )

    generation_count = 0
    delivery_count = 0

    async def execute_stage(_checkpoint, _stage, ref, _context):
        nonlocal generation_count
        generation_count += 1
        await store.record_completed_stage(
            ref=ref,
            output_file="outputs/final.png",
            saved_inputs=["inputs/original.png"],
        )
        return b"final", "outputs/final.png"

    async def deliver_result(*_args):
        nonlocal delivery_count
        delivery_count += 1

    real_mark_delivered = store.mark_delivered
    mark_attempts = 0

    async def fail_first_mark(*, ref):
        nonlocal mark_attempts
        mark_attempts += 1
        if mark_attempts == 1:
            raise continuation_service.PrivateQqccContinuationUnavailable(
                "redis unavailable after send"
            )
        return await real_mark_delivered(ref=ref)

    store.mark_delivered = fail_first_mark
    with pytest.raises(
        continuation_service.PrivateQqccContinuationUnavailable,
        match="after send",
    ):
        await resume_private_qqcc_continuation(
            chain_id=checkpoint.chain_id,
            context=SimpleNamespace(lang="zh"),
            store=store,
            execute_stage_func=execute_stage,
            deliver_result_func=deliver_result,
        )

    assert (await store.get(checkpoint.chain_id)).status == "delivery_pending"
    monkeypatch.setattr(
        continuation_service,
        "_load_continuation_output_bytes",
        AsyncMock(return_value=b"persisted-final"),
    )
    completed = await resume_private_qqcc_continuation(
        chain_id=checkpoint.chain_id,
        context=SimpleNamespace(lang="zh"),
        store=store,
        execute_stage_func=execute_stage,
        deliver_result_func=deliver_result,
    )

    assert completed.status == "completed"
    assert generation_count == 1
    assert delivery_count == 2


@pytest.mark.asyncio
async def test_recovery_rewinds_only_running_checkpoint_without_active_registry_task():
    store = MemoryContinuationStore()
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=102)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=_stages(),
            original_input_ref="/tmp/original.png",
            context=SimpleNamespace(lang="zh"),
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=400,
            store=store,
        )
    running = await store.mark_running(
        chain_id=checkpoint.chain_id,
        stage_index=0,
        submission_sequence=0,
        registry_task_id="registry-running",
        executor_token="executor-running",
    )

    assert (
        await list_private_qqcc_continuations_for_recovery(
            active_registry_task_ids={"registry-running"},
            store=store,
        )
        == []
    )
    assert (await store.get(checkpoint.chain_id)).status == "running"

    recoverable = await list_private_qqcc_continuations_for_recovery(
        active_registry_task_ids=set(),
        store=store,
    )

    assert len(recoverable) == 1
    assert recoverable[0].status == "ready"
    assert recoverable[0].next_stage_index == running.current_stage_index
    assert recoverable[0].next_submission_sequence == 0


@pytest.mark.asyncio
async def test_ready_checkpoint_waits_for_previous_active_stage_cleanup():
    store = MemoryContinuationStore()
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=107)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=_stages(),
            original_input_ref="inputs/original.png",
            original_input_durable=True,
            context=SimpleNamespace(lang="zh"),
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=None,
            store=store,
        )
    running = await store.mark_running(
        chain_id=checkpoint.chain_id,
        stage_index=0,
        submission_sequence=0,
        registry_task_id="registry-old-stage",
        executor_token="executor-old-stage",
    )
    await store.record_completed_stage(
        ref=PrivateQqccContinuationTaskRef(
            chain_id=checkpoint.chain_id,
            stage_index=0,
            submission_sequence=0,
            registry_task_id="registry-old-stage",
            executor_token=running.current_executor_token,
        ),
        output_file="outputs/stage-0.png",
        saved_inputs=["inputs/original.png"],
    )

    assert (await store.get(checkpoint.chain_id)).status == "ready"
    assert await list_private_qqcc_continuations_for_recovery(
        active_registry_task_ids={"registry-old-stage"},
        active_chain_ids={checkpoint.chain_id},
        store=store,
    ) == []

    recoverable = await list_private_qqcc_continuations_for_recovery(
        active_registry_task_ids=set(),
        active_chain_ids=set(),
        store=store,
    )
    assert [item.chain_id for item in recoverable] == [checkpoint.chain_id]


@pytest.mark.asyncio
async def test_recovery_isolates_corrupt_checkpoint_but_active_guard_fails_closed():
    memory_store = MemoryContinuationStore()
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=110)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=[_stages()[0]],
            original_input_ref="inputs/original.png",
            original_input_durable=True,
            context=SimpleNamespace(lang="zh"),
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=None,
            store=memory_store,
        )
    prefix = "test:"
    redis = ScanRedis(
        {
            f"{prefix}private_qqcc_bot:continuation:{checkpoint.chain_id}": (
                continuation_service._checkpoint_to_json(checkpoint)
            ),
            f"{prefix}private_qqcc_bot:continuation:corrupt": "{not-json",
            f"{prefix}private_qqcc_bot:continuation:corrupt:lock": "lease",
        }
    )
    store = RedisPrivateQqccContinuationStore(
        redis=redis,
        redis_prefix=prefix,
    )

    recoverable = await list_private_qqcc_continuations_for_recovery(
        active_registry_task_ids=set(),
        store=store,
    )
    assert [item.chain_id for item in recoverable] == [checkpoint.chain_id]

    with pytest.raises(
        PrivateQqccContinuationUnavailable,
        match="invalid private QQCC continuation checkpoint",
    ):
        await private_bot_has_nonterminal_continuations(7, store=store)


@pytest.mark.asyncio
async def test_running_stage_cas_and_executor_fence_reject_stale_completion():
    store = MemoryContinuationStore()
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=103)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=_stages(),
            original_input_ref="inputs/original.png",
            original_input_durable=True,
            context=SimpleNamespace(lang="zh"),
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=400,
            store=store,
        )
    first = await store.mark_running(
        chain_id=checkpoint.chain_id,
        stage_index=0,
        submission_sequence=0,
        registry_task_id="registry-0",
        executor_token="executor-old",
    )
    with pytest.raises(PrivateQqccContinuationConflict):
        await store.mark_running(
            chain_id=checkpoint.chain_id,
            stage_index=0,
            submission_sequence=0,
            registry_task_id="registry-duplicate",
            executor_token="executor-duplicate",
        )

    await store.rewind_orphaned_stage(chain_id=checkpoint.chain_id)
    await store.mark_running(
        chain_id=checkpoint.chain_id,
        stage_index=0,
        submission_sequence=0,
        registry_task_id="registry-0",
        executor_token="executor-new",
    )
    with pytest.raises(PrivateQqccContinuationConflict):
        await store.record_completed_stage(
            ref=PrivateQqccContinuationTaskRef(
                chain_id=checkpoint.chain_id,
                stage_index=0,
                submission_sequence=0,
                registry_task_id=first.current_registry_task_id,
                executor_token="executor-old",
            ),
            output_file="outputs/stale.png",
            saved_inputs=["inputs/original.png"],
        )


@pytest.mark.asyncio
async def test_continuation_lease_is_renewed_while_stage_is_running(monkeypatch):
    store = MemoryContinuationStore()
    monkeypatch.setattr(
        continuation_service,
        "PRIVATE_QQCC_CONTINUATION_LOCK_SECONDS",
        0.03,
    )
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=104)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=[_stages()[0]],
            original_input_ref="inputs/original.png",
            original_input_durable=True,
            context=SimpleNamespace(lang="zh"),
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=400,
            store=store,
        )

        async def execute_stage(_checkpoint, _stage, ref, _context):
            next_private_bot_submission_key()
            await asyncio.sleep(0.08)
            await store.record_completed_stage(
                ref=ref,
                output_file="outputs/done.png",
                saved_inputs=["inputs/original.png"],
            )
            return b"image", "outputs/done.png"

        completed = await resume_private_qqcc_continuation(
            chain_id=checkpoint.chain_id,
            context=SimpleNamespace(lang="zh"),
            store=store,
            execute_stage_func=execute_stage,
        )

    assert completed.status == "completed"
    assert store.renew_count >= 1


@pytest.mark.asyncio
async def test_lost_continuation_lease_cancels_inflight_stage_owner(monkeypatch):
    store = MemoryContinuationStore()
    store.renew_ok = False
    monkeypatch.setattr(
        continuation_service,
        "PRIVATE_QQCC_CONTINUATION_LOCK_SECONDS",
        0.03,
    )
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=106)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=[_stages()[0]],
            original_input_ref="inputs/original.png",
            original_input_durable=True,
            context=SimpleNamespace(lang="zh"),
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=None,
            store=store,
        )

    cancelled = asyncio.Event()

    async def execute_stage(*_args):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with pytest.raises(
        continuation_service.PrivateQqccContinuationUnavailable,
        match="lease was lost",
    ):
        await resume_private_qqcc_continuation(
            chain_id=checkpoint.chain_id,
            context=SimpleNamespace(lang="zh"),
            store=store,
            execute_stage_func=execute_stage,
        )

    assert cancelled.is_set()
    assert (await store.get(checkpoint.chain_id)).status == "running"


@pytest.mark.asyncio
async def test_lost_chain_lease_is_checked_before_swallowed_monitor_cancellation(
    monkeypatch,
):
    store = MemoryContinuationStore()
    store.renew_ok = False
    monkeypatch.setattr(
        continuation_service,
        "PRIVATE_QQCC_CONTINUATION_LOCK_SECONDS",
        0.03,
    )
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=109)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=[_stages()[0]],
            original_input_ref="inputs/original.png",
            original_input_durable=True,
            context=SimpleNamespace(lang="zh"),
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=None,
            store=store,
        )

    async def executor_that_swallows_inner_cancellation(*_args):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Mirrors the nested private task-monitor lease translating/shielding
            # cancellation before control returns to the chain owner.
            return None, None

    with pytest.raises(
        continuation_service.PrivateQqccContinuationUnavailable,
        match="lease was lost",
    ):
        await resume_private_qqcc_continuation(
            chain_id=checkpoint.chain_id,
            context=SimpleNamespace(lang="zh"),
            store=store,
            execute_stage_func=executor_that_swallows_inner_cancellation,
        )

    persisted = await store.get(checkpoint.chain_id)
    assert persisted.status == "running"
    assert persisted.error_code is None


@pytest.mark.asyncio
async def test_external_cancel_swallowed_by_monitor_preserves_active_stage(
    monkeypatch,
):
    store = MemoryContinuationStore()
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=111)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=[_stages()[0]],
            original_input_ref="inputs/original.png",
            original_input_durable=True,
            context=SimpleNamespace(lang="zh"),
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=None,
            store=store,
        )

    executor_started = asyncio.Event()

    async def executor_that_swallows_external_cancel(*_args):
        executor_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return None, None

    registry_lookup = AsyncMock(return_value={"backend_task_id": "paid-task"})
    monkeypatch.setattr(
        "src.services.task_registry.TaskRegistry.get_task_strict",
        registry_lookup,
    )
    resume_task = asyncio.create_task(
        resume_private_qqcc_continuation(
            chain_id=checkpoint.chain_id,
            context=SimpleNamespace(lang="zh"),
            store=store,
            execute_stage_func=executor_that_swallows_external_cancel,
        )
    )
    await executor_started.wait()
    resume_task.cancel()

    with pytest.raises(
        PrivateQqccContinuationUnavailable,
        match="monitor was interrupted",
    ):
        await resume_task

    registry_lookup.assert_awaited_once()
    persisted = await store.get(checkpoint.chain_id)
    assert persisted.status == "running"
    assert persisted.error_code is None


@pytest.mark.asyncio
async def test_external_cancel_after_delivery_checkpoint_and_registry_cleanup_delivers(
    monkeypatch,
):
    store = MemoryContinuationStore()
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=112)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=[_stages()[1]],
            original_input_ref="inputs/original.png",
            original_input_durable=True,
            context=SimpleNamespace(lang="zh"),
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=None,
            store=store,
        )

    checkpoint_advanced = asyncio.Event()

    async def executor_advances_then_swallows_cancel(_checkpoint, _stage, ref, _context):
        await store.record_completed_stage(
            ref=ref,
            output_file="outputs/final.png",
            saved_inputs=["inputs/original.png"],
        )
        # The real task flow removes TaskRegistry after this durable CAS.
        checkpoint_advanced.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return None, None

    registry_lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.services.task_registry.TaskRegistry.get_task_strict",
        registry_lookup,
    )
    monkeypatch.setattr(
        continuation_service,
        "_load_continuation_output_bytes",
        AsyncMock(return_value=b"persisted-final"),
    )
    delivered = []

    async def deliver_result(_checkpoint, _stage, _ref, _context, media_bytes):
        delivered.append(media_bytes)

    resume_task = asyncio.create_task(
        resume_private_qqcc_continuation(
            chain_id=checkpoint.chain_id,
            context=SimpleNamespace(lang="zh"),
            store=store,
            execute_stage_func=executor_advances_then_swallows_cancel,
            deliver_result_func=deliver_result,
        )
    )
    await checkpoint_advanced.wait()
    assert (await store.get(checkpoint.chain_id)).status == "delivery_pending"
    resume_task.cancel()

    completed = await resume_task

    assert completed.status == "completed"
    assert delivered == [b"persisted-final"]
    registry_lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_failure_fence_cannot_overwrite_ready_or_delivery_pending_checkpoint():
    store = MemoryContinuationStore()
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=113)
    with activate_private_bot_update_scope(scope):
        checkpoint = await create_private_qqcc_continuation(
            stages=_stages(),
            original_input_ref="inputs/original.png",
            original_input_durable=True,
            context=SimpleNamespace(lang="zh"),
            chat_id=200,
            telegram_user_id=300,
            username="visitor",
            status_message_id=None,
            store=store,
        )
    running = await store.mark_running(
        chain_id=checkpoint.chain_id,
        stage_index=0,
        submission_sequence=0,
        registry_task_id="registry-stage-0",
        executor_token="executor-stage-0",
    )
    ref = PrivateQqccContinuationTaskRef(
        chain_id=checkpoint.chain_id,
        stage_index=0,
        submission_sequence=0,
        registry_task_id="registry-stage-0",
        executor_token=running.current_executor_token,
    )
    await store.record_completed_stage(
        ref=ref,
        output_file="outputs/stage-0.png",
        saved_inputs=["inputs/original.png"],
    )

    with pytest.raises(PrivateQqccContinuationConflict, match="failure fence"):
        await store.mark_failed(ref=ref, error_code="late_failure")
    assert (await store.get(checkpoint.chain_id)).status == "ready"

    stage_one = await store.mark_running(
        chain_id=checkpoint.chain_id,
        stage_index=1,
        submission_sequence=1,
        registry_task_id="registry-stage-1",
        executor_token="executor-stage-1",
    )
    final_ref = PrivateQqccContinuationTaskRef(
        chain_id=checkpoint.chain_id,
        stage_index=1,
        submission_sequence=1,
        registry_task_id="registry-stage-1",
        executor_token=stage_one.current_executor_token,
    )
    await store.record_completed_stage(
        ref=final_ref,
        output_file="outputs/final.png",
        saved_inputs=[],
    )
    with pytest.raises(PrivateQqccContinuationConflict, match="failure fence"):
        await store.mark_failed(ref=final_ref, error_code="late_failure")
    assert (await store.get(checkpoint.chain_id)).status == "delivery_pending"


@pytest.mark.asyncio
async def test_original_input_is_persisted_before_checkpoint_acceptance(
    monkeypatch,
    tmp_path,
):
    from unittest.mock import AsyncMock, Mock

    image_path = tmp_path / "original.png"
    image_path.write_bytes(b"image")
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=88), False)),
    )
    save_input = Mock(return_value="88/input_images/original.png")
    monkeypatch.setattr("src.logger.UserLogger.save_input_image", save_input)

    persisted = await persist_private_qqcc_continuation_input(
        input_ref=str(image_path),
        telegram_user_id=300,
        username="visitor",
    )

    assert persisted == "88/input_images/original.png"
    save_input.assert_called_once_with(str(image_path))
