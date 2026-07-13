import asyncio
import ast
import inspect
import json
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ResponseError

from qqcc_private_bot import worker as worker_module
from qqcc_private_bot.worker import (
    PrivateBotRuntimeRecord,
    PrivateQqccBotWorker,
    PrivateQqccBotWorkerDependencies,
)
from src.services import private_qqcc_bot_runtime
from src.services import private_qqcc_continuation_service


def test_worker_entrypoint_refuses_to_start_when_rollout_gate_is_disabled(
    monkeypatch,
):
    monkeypatch.setenv("PRIVATE_QQCC_BOT_ENABLED", "false")
    monkeypatch.setattr("src.logger.setup_logging", lambda: None)
    monkeypatch.setattr(
        worker_module.asyncio,
        "run",
        lambda _coro: pytest.fail("disabled worker must not enter its event loop"),
    )

    worker_module.main()


def test_private_runtime_avoids_builtin_timeout_handlers_for_python310():
    modules = (
        worker_module,
        private_qqcc_bot_runtime,
        private_qqcc_continuation_service,
    )
    bare_timeout_handlers = []
    for module in modules:
        tree = ast.parse(inspect.getsource(module))
        bare_timeout_handlers.extend(
            (module.__name__, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler)
            and isinstance(node.type, ast.Name)
            and node.type.id == "TimeoutError"
        )

    assert bare_timeout_handlers == []


class FakeRedis:
    def __init__(self):
        self.group_calls = []
        self.autoclaim_calls = []
        self.autoclaim_responses = [("0-0", [], [])]
        self.ack_calls = []
        self.ack_effects = []
        self.deleted_message_ids = []
        self.values = {}
        self.counters = {}
        self.eval_effects = []
        self.renew_calls = 0
        self.stream_entries = {}

    async def xgroup_create(self, **kwargs):
        self.group_calls.append(kwargs)
        return True

    async def xautoclaim(self, **kwargs):
        self.autoclaim_calls.append(kwargs)
        if self.autoclaim_responses:
            return self.autoclaim_responses.pop(0)
        return ("0-0", [], [])

    async def xrange(self, *, name, min, max, count):
        _ = (name, max, count)
        entry = self.stream_entries.get(str(min))
        return [(min, entry)] if entry is not None else []

    async def set(self, key, value, *, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def exists(self, key):
        return int(key in self.values)

    async def eval(self, script, key_count, *args):
        assert key_count == 1
        if self.eval_effects:
            effect = self.eval_effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            return effect
        key = args[0]
        if "INCR" in script:
            self.counters[key] = self.counters.get(key, 0) + 1
            return self.counters[key]
        if "XACK" in script:
            _stream_key, consumer_group, message_id = args
            self.ack_calls.append((key, consumer_group, message_id))
            if self.ack_effects:
                effect = self.ack_effects.pop(0)
                if isinstance(effect, BaseException):
                    raise effect
                acknowledged = effect
            else:
                acknowledged = 1
            if acknowledged == 1:
                self.deleted_message_ids.append(message_id)
            return acknowledged
        lease = args[1]
        if "EXPIRE" in script:
            self.renew_calls += 1
            return int(self.values.get(key) == lease)
        if self.values.get(key) == lease:
            self.values.pop(key, None)
            return 1
        return 0


class FakeStore:
    def __init__(self, records):
        self.records = dict(records)
        self.configs = {
            private_bot_id: {"global_enabled": True}
            for private_bot_id in self.records
        }
        self.record_reads = []
        self.config_reads = []
        self.processed = []
        self.runtime_errors = []

    async def get_runtime_record(self, private_bot_id):
        self.record_reads.append(private_bot_id)
        return self.records.get(private_bot_id)

    async def load_config(self, private_bot_id):
        self.config_reads.append(private_bot_id)
        return dict(self.configs[private_bot_id])

    async def mark_update_processed(
        self,
        private_bot_id,
        *,
        webhook_received_at,
        processed_at,
    ):
        self.processed.append(
            (private_bot_id, webhook_received_at, processed_at)
        )

    async def mark_runtime_error(
        self,
        private_bot_id,
        *,
        error_code,
        occurred_at,
        disable_runtime,
    ):
        self.runtime_errors.append(
            (private_bot_id, error_code, occurred_at, disable_runtime)
        )


class FakeCipher:
    def __init__(self):
        self.calls = []

    def decrypt(self, ciphertext, *, key_version, associated_data):
        self.calls.append((ciphertext, key_version, associated_data))
        return f"private-token-{associated_data}"


class FakeApplication:
    def __init__(self, private_bot_id, process_update):
        self.private_bot_id = private_bot_id
        self.bot = SimpleNamespace(id=10_000 + private_bot_id)
        self.bot_data = {}
        self._process_update = process_update
        self.initialize_calls = 0
        self.start_calls = 0
        self.stop_calls = 0
        self.shutdown_calls = 0
        self.post_init_calls = 0
        self.post_shutdown_calls = 0

        async def post_init(application):
            assert application is self
            self.post_init_calls += 1

        async def post_shutdown(application):
            assert application is self
            self.post_shutdown_calls += 1

        self.post_init = post_init
        self.post_shutdown = post_shutdown

    async def initialize(self):
        self.initialize_calls += 1

    async def start(self):
        self.start_calls += 1

    async def process_update(self, update):
        await self._process_update(self.private_bot_id, update)

    async def stop(self):
        self.stop_calls += 1

    async def shutdown(self):
        self.shutdown_calls += 1


class FakeApplicationFactory:
    def __init__(self, process_update=None):
        self.calls = []
        self.applications = {}
        self._process_update = process_update or self._noop

    async def _noop(self, _private_bot_id, _update):
        return None

    def __call__(self, token, **kwargs):
        private_bot_id = kwargs["private_bot_id"]
        self.calls.append((token, kwargs))
        app = FakeApplication(private_bot_id, self._process_update)
        self.applications[private_bot_id] = app
        return app


def active_record(private_bot_id):
    return PrivateBotRuntimeRecord(
        private_bot_id=private_bot_id,
        owner_enabled=True,
        admin_enabled=True,
        runtime_status="active",
        token_ciphertext=f"ciphertext-{private_bot_id}",
        token_key_version=3,
        token_fingerprint=f"fingerprint-{private_bot_id}",
        webhook_public_id=f"public-{private_bot_id}",
    )


async def no_task_recovery(_resolver):
    return None


async def no_zombie_cleanup(_resolver):
    return 0


def build_worker(
    *,
    records,
    redis=None,
    factory=None,
    recover_tasks=no_task_recovery,
    clean_zombies=no_zombie_cleanup,
    concurrency=4,
    pending_sweep_seconds=30,
    application_idle_seconds=300,
    zombie_sweep_seconds=600,
    retry_seconds=1,
    max_inflight_updates=64,
    per_bot_prefetch=8,
    max_deferred_updates=1024,
    channel_membership_checker=None,
):
    fake_redis = redis or FakeRedis()
    store = FakeStore(records)
    cipher = FakeCipher()
    app_factory = factory or FakeApplicationFactory()
    dependencies = PrivateQqccBotWorkerDependencies(
        redis=fake_redis,
        store=store,
        credential_cipher=cipher,
        channel_membership_checker=channel_membership_checker,
        application_builder=app_factory,
        update_decoder=lambda payload, _bot: payload,
        recover_tasks=recover_tasks,
        clean_zombies=clean_zombies,
        now=lambda: datetime(2026, 7, 12, 16, 30, 0),
    )
    worker = PrivateQqccBotWorker(
        dependencies,
        redis_prefix="test:",
        consumer_group="private-test-workers",
        consumer_name="worker-a",
        concurrency=concurrency,
        pending_sweep_seconds=pending_sweep_seconds,
        application_idle_seconds=application_idle_seconds,
        zombie_sweep_seconds=zombie_sweep_seconds,
        retry_seconds=retry_seconds,
        max_inflight_updates=max_inflight_updates,
        per_bot_prefetch=per_bot_prefetch,
        max_deferred_updates=max_deferred_updates,
    )
    return worker, fake_redis, store, cipher, app_factory


def stream_fields(private_bot_id, update_id, **extra):
    payload = {"update_id": update_id, **extra}
    return {
        "private_bot_id": str(private_bot_id),
        "update_id": str(update_id),
        "update_json": json.dumps(payload),
        "received_at": "1783840200.5",
    }


@pytest.mark.asyncio
async def test_same_bot_is_serial_while_different_bots_run_in_parallel():
    release_first = asyncio.Event()
    bot_one_started = asyncio.Event()
    bot_two_started = asyncio.Event()
    events = []

    async def process(private_bot_id, update):
        update_id = update["update_id"]
        events.append(("start", private_bot_id, update_id))
        if private_bot_id == 1 and update_id == 101:
            bot_one_started.set()
            await release_first.wait()
        if private_bot_id == 2:
            bot_two_started.set()
        events.append(("end", private_bot_id, update_id))

    factory = FakeApplicationFactory(process)
    worker, redis, store, _cipher, _factory = build_worker(
        records={1: active_record(1), 2: active_record(2)},
        factory=factory,
        concurrency=2,
    )

    await worker.dispatch_message("1-0", stream_fields(1, 101))
    await worker.dispatch_message("2-0", stream_fields(1, 102))
    await worker.dispatch_message("3-0", stream_fields(2, 201))

    await asyncio.wait_for(bot_one_started.wait(), timeout=1)
    await asyncio.wait_for(bot_two_started.wait(), timeout=1)
    assert ("start", 1, 102) not in events

    release_first.set()
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    bot_one_events = [event for event in events if event[1] == 1]
    assert bot_one_events == [
        ("start", 1, 101),
        ("end", 1, 101),
        ("start", 1, 102),
        ("end", 1, 102),
    ]
    assert [item[2] for item in redis.ack_calls] == ["3-0", "1-0", "2-0"]
    assert [item[0] for item in store.processed] == [2, 1, 1]
    await worker.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record", "should_ack"),
    [
        (
            replace(active_record(7), owner_enabled=False, runtime_status="paused"),
            True,
        ),
        (
            replace(active_record(7), admin_enabled=False, runtime_status="disabled"),
            True,
        ),
        (replace(active_record(7), runtime_status="error"), True),
    ],
)
async def test_inactive_bot_is_rechecked_and_dropped_without_building_application(
    record,
    should_ack,
):
    worker, redis, store, _cipher, factory = build_worker(records={7: record})

    await worker.dispatch_message("7-1", stream_fields(7, 701))
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    assert factory.calls == []
    assert store.record_reads == [7]
    assert store.processed == []
    assert [item[2] for item in redis.ack_calls] == (["7-1"] if should_ack else [])
    await worker.shutdown()


@pytest.mark.asyncio
async def test_inactive_update_keeps_application_alive_for_paid_background_delivery():
    worker, redis, store, _cipher, factory = build_worker(
        records={7: active_record(7)},
        application_idle_seconds=0.05,
    )

    await worker.dispatch_message("7-0", stream_fields(7, 700))
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)
    application = factory.applications[7]

    release_delivery = asyncio.Event()
    delivery_task = asyncio.create_task(release_delivery.wait())
    application.bot_data.setdefault("bg_tasks", set()).add(delivery_task)
    store.records[7] = replace(
        active_record(7),
        owner_enabled=False,
        runtime_status="paused",
    )

    await worker.dispatch_message("7-1", stream_fields(7, 701))
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    assert application.stop_calls == 0
    assert application.shutdown_calls == 0
    assert delivery_task.done() is False
    assert [item[2] for item in redis.ack_calls] == ["7-0", "7-1"]

    consumer_task = worker._bot_tasks[7]
    release_delivery.set()
    await delivery_task
    await asyncio.wait_for(consumer_task, timeout=1)
    assert application.stop_calls == 1
    assert application.shutdown_calls == 1
    assert 7 not in worker._applications
    await worker.shutdown()


@pytest.mark.asyncio
async def test_inactive_update_discards_existing_application_without_backgrounds():
    worker, _redis, store, _cipher, factory = build_worker(
        records={7: active_record(7)},
    )

    await worker.dispatch_message("7-0", stream_fields(7, 700))
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)
    application = factory.applications[7]
    store.records[7] = replace(
        active_record(7),
        admin_enabled=False,
        runtime_status="disabled",
    )

    await worker.dispatch_message("7-1", stream_fields(7, 701))
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    assert application.stop_calls == 1
    assert application.shutdown_calls == 1
    assert 7 not in worker._applications
    await worker.shutdown()


@pytest.mark.asyncio
async def test_application_uses_private_identity_live_config_and_safe_factory_flags():
    resolved = {}
    channel_membership_checker = AsyncMock(return_value=True)

    async def recover_tasks(resolver):
        resolved["active"] = await resolver(9)
        resolved["inactive"] = await resolver(10)

    records = {
        9: active_record(9),
        10: replace(active_record(10), runtime_status="paused", owner_enabled=False),
    }
    worker, _redis, store, cipher, factory = build_worker(
        records=records,
        recover_tasks=recover_tasks,
        channel_membership_checker=channel_membership_checker,
    )

    await worker.start()

    assert resolved["active"] is factory.applications[9]
    assert resolved["inactive"] is factory.applications[10]
    token, kwargs = factory.calls[0]
    assert token == "private-token-public-9"
    assert kwargs["bot_client_type"] == "bot:qqcc-private:9"
    assert kwargs["private_bot_id"] == 9
    assert kwargs["include_private_bot_provisioning"] is False
    assert kwargs["recover_tasks"] is False
    assert kwargs["close_shared_redis_on_shutdown"] is False
    assert kwargs["telegram_base_url"] == "https://api.telegram.org/bot"
    assert kwargs["telegram_file_base_url"] == "https://api.telegram.org/file/bot"
    assert kwargs["setup_bot_commands"] is False
    assert kwargs["request_connection_pool_size"] == 4
    assert kwargs["channel_membership_checker"] is channel_membership_checker
    assert cipher.calls == [
        ("ciphertext-9", 3, "public-9"),
        ("ciphertext-10", 3, "public-10"),
    ]

    store.configs[9] = {"global_enabled": False, "unknown": "discard-me"}
    first = await kwargs["config_loader"]()
    store.configs[9] = {"global_enabled": True}
    second = await kwargs["config_loader"]()
    assert first["global_enabled"] is False
    assert "unknown" not in first
    assert second["global_enabled"] is True
    assert store.config_reads == [9, 9]

    await worker.shutdown()
    app = factory.applications[9]
    assert app.initialize_calls == 1
    assert app.start_calls == 1
    assert app.stop_calls == 1
    assert app.shutdown_calls == 1
    assert app.post_init_calls == 1
    assert app.post_shutdown_calls == 1


@pytest.mark.asyncio
async def test_token_fingerprint_change_cancels_old_application_tasks_before_rebuild():
    worker, _redis, store, _cipher, factory = build_worker(
        records={9: active_record(9)},
    )
    old_application = await worker.resolve_recovery_application(9)
    assert old_application is not None
    cancelled = asyncio.Event()

    async def _old_background():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    old_task = asyncio.create_task(_old_background())
    old_application.bot_data["bg_tasks"] = {old_task}
    await asyncio.sleep(0)
    store.records[9] = replace(
        active_record(9),
        token_ciphertext="rotated-ciphertext-9",
        token_fingerprint="rotated-fingerprint-9",
    )

    new_application = await worker.resolve_recovery_application(9)

    assert new_application is not None
    assert new_application is not old_application
    await asyncio.wait_for(cancelled.wait(), timeout=1)
    assert old_task.cancelled()
    assert old_application.stop_calls == 1
    assert old_application.shutdown_calls == 1
    await worker.shutdown()


@pytest.mark.asyncio
async def test_start_accepts_busy_group_and_claims_timed_out_pending_entries():
    class BusyGroupRedis(FakeRedis):
        async def xgroup_create(self, **kwargs):
            self.group_calls.append(kwargs)
            raise ResponseError("BUSYGROUP Consumer Group name already exists")

    redis = BusyGroupRedis()
    redis.autoclaim_responses = [
        (
            "0-0",
            [("8-0", stream_fields(8, 801))],
            [],
        )
    ]
    worker, _redis, store, _cipher, _factory = build_worker(
        records={8: active_record(8)},
        redis=redis,
    )

    await worker.start()
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    assert redis.group_calls == [
        {
            "name": "test:private_qqcc_bot:webhook:updates",
            "groupname": "private-test-workers",
            "id": "0-0",
            "mkstream": True,
        }
    ]
    assert redis.autoclaim_calls[0]["start_id"] == "0-0"
    assert redis.autoclaim_calls[0]["min_idle_time"] == 0
    assert [item[2] for item in redis.ack_calls] == ["8-0"]
    assert [item[0] for item in store.processed] == [8]
    await worker.shutdown()


@pytest.mark.asyncio
async def test_startup_finishes_old_pending_scan_before_new_stream_reads():
    started = asyncio.Event()
    release = asyncio.Event()

    async def process(_private_bot_id, _update):
        started.set()
        await release.wait()

    redis = FakeRedis()
    redis.autoclaim_responses = [
        ("5-0", [("1-0", stream_fields(1, 101))], []),
        ("0-0", [], []),
    ]
    worker, *_ = build_worker(
        records={1: active_record(1)},
        redis=redis,
        factory=FakeApplicationFactory(process),
        max_inflight_updates=1,
        per_bot_prefetch=1,
    )

    await worker.start()
    await asyncio.wait_for(started.wait(), timeout=1)

    assert worker._pending_catchup_complete.is_set() is False
    assert [call["start_id"] for call in redis.autoclaim_calls] == ["0-0"]

    release.set()
    await asyncio.wait_for(worker._pending_catchup_complete.wait(), timeout=1)
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    assert [call["start_id"] for call in redis.autoclaim_calls[:2]] == [
        "0-0",
        "5-0",
    ]
    await worker.shutdown()


@pytest.mark.asyncio
async def test_processing_exception_dead_letters_without_logging_update_body(caplog):
    async def fail_processing(_private_bot_id, _update):
        raise RuntimeError("SENSITIVE-UPDATE-BODY")

    worker, redis, store, _cipher, _factory = build_worker(
        records={3: active_record(3)},
        factory=FakeApplicationFactory(fail_processing),
        retry_seconds=0.01,
    )

    await worker.dispatch_message(
        "3-0",
        stream_fields(3, 301, text="SENSITIVE-UPDATE-BODY"),
    )
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    assert [item[2] for item in redis.ack_calls] == ["3-0"]
    assert store.processed == []
    assert [(item[0], item[1], item[3]) for item in store.runtime_errors] == [
        (3, "update_dead_lettered", False)
    ]
    assert list(redis.counters.values()) == [3]
    assert "SENSITIVE-UPDATE-BODY" not in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    await worker.shutdown()


@pytest.mark.asyncio
async def test_poison_update_does_not_reorder_later_updates_for_same_bot():
    events = []

    async def process(_private_bot_id, update):
        events.append(update["update_id"])
        if update["update_id"] == 601:
            raise RuntimeError("bad update")

    worker, redis, store, _cipher, _factory = build_worker(
        records={6: active_record(6)},
        factory=FakeApplicationFactory(process),
        retry_seconds=0.01,
    )
    await worker.dispatch_message(
        "6-0",
        stream_fields(6, 601, text="never-store-this-body"),
    )
    await worker.dispatch_message("6-1", stream_fields(6, 602))
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    assert events == [601, 601, 601, 602]
    assert [item[2] for item in redis.ack_calls] == ["6-0", "6-1"]
    assert redis.deleted_message_ids == ["6-0", "6-1"]
    assert [(item[0], item[1], item[3]) for item in store.runtime_errors] == [
        (6, "update_dead_lettered", False)
    ]
    assert all(
        "never-store-this-body" not in str(value)
        for value in redis.values.values()
    )
    await worker.shutdown()


@pytest.mark.asyncio
async def test_application_bootstrap_failure_degrades_bot_and_drops_update():
    def fail_factory(_token, **_kwargs):
        raise RuntimeError("telegram init unavailable")

    worker, redis, store, *_ = build_worker(
        records={14: active_record(14)},
        factory=fail_factory,
    )

    await worker.dispatch_message("14-0", stream_fields(14, 1401))
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    assert [item[2] for item in redis.ack_calls] == ["14-0"]
    assert [(item[0], item[1], item[3]) for item in store.runtime_errors] == [
        (14, "application_unavailable", True)
    ]
    await worker.shutdown()


@pytest.mark.asyncio
async def test_ack_failure_keeps_processed_entry_recoverable_without_stopping_queue(caplog):
    redis = FakeRedis()
    redis.ack_effects = [RuntimeError("redis unavailable"), 1]
    worker, _redis, store, _cipher, _factory = build_worker(
        records={4: active_record(4)},
        redis=redis,
    )

    await worker.dispatch_message("4-0", stream_fields(4, 401))
    await worker.dispatch_message("5-0", stream_fields(4, 402))
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    assert [item[2] for item in redis.ack_calls] == ["4-0", "5-0"]
    assert [item[0] for item in store.processed] == [4, 4]
    assert "ACK failed message_id=4-0 error_type=RuntimeError" in caplog.text
    assert redis.deleted_message_ids == ["5-0"]
    await worker.shutdown()


@pytest.mark.asyncio
async def test_processed_marker_prevents_handler_replay_after_ack_failure():
    calls = 0

    async def process(_private_bot_id, _update):
        nonlocal calls
        calls += 1

    redis = FakeRedis()
    redis.ack_effects = [RuntimeError("redis unavailable"), 1]
    worker, _redis, store, _cipher, _factory = build_worker(
        records={11: active_record(11)},
        redis=redis,
        factory=FakeApplicationFactory(process),
    )

    await worker.dispatch_message("11-0", stream_fields(11, 1101))
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)
    await worker.dispatch_message("11-1", stream_fields(11, 1101))
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    assert calls == 1
    assert len(store.processed) == 1
    assert [item[2] for item in redis.ack_calls] == ["11-0", "11-1"]
    assert redis.deleted_message_ids == ["11-1"]
    await worker.shutdown()


@pytest.mark.asyncio
async def test_singleton_lease_rejects_a_second_worker():
    redis = FakeRedis()
    first, *_ = build_worker(records={}, redis=redis)
    second, *_ = build_worker(records={}, redis=redis)

    await first.start()
    with pytest.raises(RuntimeError, match="singleton lease"):
        await second.start()

    await first.shutdown()
    await second.shutdown()


@pytest.mark.asyncio
async def test_singleton_lease_renews_during_slow_startup(monkeypatch):
    release_recovery = asyncio.Event()

    async def slow_recovery(_resolver):
        await release_recovery.wait()

    monkeypatch.setattr(worker_module, "WORKER_LEADER_RENEW_SECONDS", 0.01)
    worker, redis, *_ = build_worker(records={}, recover_tasks=slow_recovery)
    start_task = asyncio.create_task(worker.start())

    await asyncio.sleep(0.04)
    assert redis.renew_calls >= 1
    release_recovery.set()
    await asyncio.wait_for(start_task, timeout=1)
    await worker.shutdown()


@pytest.mark.asyncio
async def test_leader_renewal_failure_stops_worker_fail_closed(monkeypatch):
    monkeypatch.setattr(worker_module, "WORKER_LEADER_RENEW_SECONDS", 0.01)
    redis = FakeRedis()
    redis.eval_effects = [ConnectionError("redis unavailable")]
    worker, *_ = build_worker(records={}, redis=redis)

    await worker.start()
    await asyncio.wait_for(worker._stop_event.wait(), timeout=1)

    assert worker._stop_event.is_set()
    await worker.shutdown()


@pytest.mark.asyncio
async def test_continuous_pending_sweep_claims_entries_after_startup():
    redis = FakeRedis()
    worker, _redis, store, *_ = build_worker(
        records={12: active_record(12)},
        redis=redis,
        pending_sweep_seconds=0.1,
    )
    await worker.start()
    redis.autoclaim_responses.append(
        ("0-0", [("12-0", stream_fields(12, 1201))], [])
    )

    await asyncio.sleep(0.15)
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    assert [item[0] for item in store.processed] == [12]
    assert redis.deleted_message_ids == ["12-0"]
    assert redis.autoclaim_calls[-1]["min_idle_time"] == 60_000
    await worker.shutdown()


@pytest.mark.asyncio
async def test_metrics_publisher_catches_asyncio_timeout_on_python310(monkeypatch):
    worker, *_ = build_worker(records={})
    worker.metrics_publish_seconds = 0.001
    publish_calls = []

    async def publish_metrics(*_args, **_kwargs):
        publish_calls.append(True)
        if len(publish_calls) == 2:
            worker._stop_event.set()

    class DistinctBuiltinTimeoutError(Exception):
        pass

    monkeypatch.setattr(
        worker_module,
        "TimeoutError",
        DistinctBuiltinTimeoutError,
        raising=False,
    )
    monkeypatch.setattr(
        worker_module,
        "publish_private_qqcc_worker_metrics",
        publish_metrics,
    )

    await asyncio.wait_for(worker._run_metrics_publisher(), timeout=1)

    assert len(publish_calls) == 2


@pytest.mark.asyncio
async def test_idle_application_is_reclaimed_when_no_background_task_remains():
    worker, _redis, _store, _cipher, factory = build_worker(
        records={13: active_record(13)},
        application_idle_seconds=0.1,
    )

    await worker.dispatch_message("13-0", stream_fields(13, 1301))
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)
    await asyncio.sleep(0.15)

    application = factory.applications[13]
    assert application.stop_calls == 1
    assert application.shutdown_calls == 1
    assert 13 not in worker._applications
    await worker.shutdown()


@pytest.mark.asyncio
async def test_500_tenant_webhook_burst_preserves_tenant_routing():
    tenant_count = 500
    records = {
        private_bot_id: active_record(private_bot_id)
        for private_bot_id in range(1, tenant_count + 1)
    }
    seen = set()

    async def process(private_bot_id, update):
        seen.add((private_bot_id, update["update_id"]))

    worker, redis, store, _cipher, factory = build_worker(
        records=records,
        factory=FakeApplicationFactory(process),
        concurrency=16,
        max_inflight_updates=tenant_count,
    )

    await asyncio.gather(
        *(
            worker.dispatch_message(
                f"{private_bot_id}-0",
                stream_fields(private_bot_id, 10_000 + private_bot_id),
            )
            for private_bot_id in records
        )
    )
    await asyncio.wait_for(worker.wait_until_idle(), timeout=5)

    assert len(seen) == tenant_count
    assert len(store.processed) == tenant_count
    assert len(redis.deleted_message_ids) == tenant_count
    assert set(factory.applications) == set(records)
    await worker.shutdown()


@pytest.mark.asyncio
async def test_worker_bounds_in_memory_prefetch_and_leaves_excess_pending():
    first_started = asyncio.Event()
    release = asyncio.Event()
    seen = []

    async def process(_private_bot_id, update):
        seen.append(update["update_id"])
        if update["update_id"] == 101:
            first_started.set()
            await release.wait()

    worker, redis, _store, _cipher, _factory = build_worker(
        records={1: active_record(1)},
        factory=FakeApplicationFactory(process),
        max_inflight_updates=2,
        per_bot_prefetch=1,
    )

    assert await worker.dispatch_message("1-0", stream_fields(1, 101)) is True
    await asyncio.wait_for(first_started.wait(), timeout=1)
    assert await worker.dispatch_message("1-1", stream_fields(1, 102)) is True
    assert await worker.dispatch_message("1-2", stream_fields(1, 103)) is False
    assert worker._inflight_updates == 2
    assert "1-2" not in redis.deleted_message_ids

    release.set()
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)
    assert await worker.dispatch_message("1-2", stream_fields(1, 103)) is True
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    assert seen == [101, 102, 103]
    assert worker._inflight_updates == 0
    await worker.shutdown()


@pytest.mark.asyncio
async def test_deferred_same_bot_updates_resume_in_stream_order_before_later_update():
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    all_seen = asyncio.Event()
    seen = []

    async def process(_private_bot_id, update):
        update_id = update["update_id"]
        seen.append(update_id)
        if update_id == 101:
            first_started.set()
            await release_first.wait()
        if len(seen) == 4:
            all_seen.set()

    worker, redis, _store, _cipher, _factory = build_worker(
        records={1: active_record(1)},
        factory=FakeApplicationFactory(process),
        max_inflight_updates=2,
        per_bot_prefetch=1,
        max_deferred_updates=8,
    )
    entries = {
        f"1-{index}": stream_fields(1, update_id)
        for index, update_id in enumerate((101, 102, 103, 104))
    }
    redis.stream_entries.update(entries)
    await worker.start()

    await worker._dispatch_messages([("1-0", entries["1-0"])])
    await asyncio.wait_for(first_started.wait(), timeout=1)
    await worker._dispatch_messages(
        [
            ("1-1", entries["1-1"]),
            ("1-2", entries["1-2"]),
            ("1-3", entries["1-3"]),
        ]
    )
    assert list(map(_as_text_for_test, worker._deferred_by_bot[1])) == [
        "1-2",
        "1-3",
    ]

    release_first.set()
    await asyncio.wait_for(all_seen.wait(), timeout=2)
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)

    assert seen == [101, 102, 103, 104]
    assert worker._deferred_message_ids == set()
    await worker.shutdown()


def _as_text_for_test(value):
    return value.decode() if isinstance(value, bytes) else str(value)


@pytest.mark.asyncio
async def test_reclaimed_inflight_message_id_is_not_processed_twice():
    started = asyncio.Event()
    release = asyncio.Event()
    seen = []

    async def process(_private_bot_id, update):
        seen.append(update["update_id"])
        started.set()
        await release.wait()

    worker, _redis, _store, _cipher, _factory = build_worker(
        records={1: active_record(1)},
        factory=FakeApplicationFactory(process),
    )
    fields = stream_fields(1, 101)

    assert await worker.dispatch_message("1-0", fields) is True
    await asyncio.wait_for(started.wait(), timeout=1)
    assert (
        await worker.dispatch_message(
            "1-0",
            fields,
            defer_on_backpressure=True,
        )
        is True
    )

    release.set()
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)
    assert seen == [101]
    await worker.shutdown()


@pytest.mark.asyncio
async def test_shutdown_cancels_application_backgrounds_before_stopping_ptb():
    worker, _redis, _store, _cipher, factory = build_worker(
        records={15: active_record(15)},
    )
    await worker.dispatch_message("15-0", stream_fields(15, 1501))
    await asyncio.wait_for(worker.wait_until_idle(), timeout=1)
    cancelled = asyncio.Event()

    async def long_monitor():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(long_monitor())
    factory.applications[15].bot_data.setdefault("bg_tasks", set()).add(task)

    await asyncio.wait_for(worker.shutdown(), timeout=1)

    assert cancelled.is_set()
    assert task.done()
    assert factory.applications[15].stop_calls == 1
