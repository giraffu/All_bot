import sys
from datetime import datetime, timedelta
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from dashboard.backend.routers import system as system_router
from dashboard.backend.services import system_service
from src.core.task_core import TaskTerminationFinalizationResult
from src.database.models import MembershipPlan, Order, Referral, User


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self._status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, _url, timeout=5.0):
        _ = timeout
        return _FakeResponse(self._payload, self._status_code)


class _FakeDbSession:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def execute(self, _stmt):
        return SimpleNamespace(all=lambda: self._rows)


class _FakePendingPipeline:
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.ops = []

    def hget(self, key, field):
        self.ops.append((key, field))
        return self

    async def execute(self):
        return [
            self.redis_client.hashes.get(key, {}).get(field) for key, field in self.ops
        ]


class _FakePendingRedis:
    def __init__(self, *, pending_scores=None, hashes=None, fail_zrange=False):
        self.pending_scores = dict(pending_scores or {})
        self.hashes = dict(hashes or {})
        self.fail_zrange = fail_zrange
        self.closed = False

    async def zrange(self, _key, start, end):
        if self.fail_zrange:
            raise RuntimeError("redis unavailable")
        items = sorted(self.pending_scores.items(), key=lambda item: item[1])
        if end == -1:
            sliced = items[start:]
        else:
            sliced = items[start : end + 1]
        return [task_id for task_id, _score in sliced]

    def pipeline(self, transaction=False):
        _ = transaction
        return _FakePendingPipeline(self)

    async def aclose(self):
        self.closed = True


async def _create_low_trust_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(Referral.__table__.create)
        await conn.run_sync(MembershipPlan.__table__.create)
        await conn.run_sync(Order.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


async def _seed_dashboard_low_trust_case(session_factory):
    async with session_factory() as session:
        session.add(
            MembershipPlan(
                id=1,
                name="gift",
                identity_name="外门弟子",
                price_ton=0,
                price_stars=0,
                price_rmb=0,
                reward_credits=0,
            )
        )
        session.add_all(
            [
                User(id=10, username="low", checkin_count=8),
                User(id=20, username="quality", checkin_count=8),
                User(id=30, username="ordered", checkin_count=8),
                User(id=40, username="under", checkin_count=7),
            ]
        )
        session.add(
            Order(
                order_id="own-success",
                internal_user_id=30,
                plan_id=1,
                original_price=0,
                final_price=0,
                status="SUCCESS",
                tx_hash="manual_own_success",
            )
        )

        invitees = []
        referrals = []
        orders = []
        for index in range(101):
            invitee_id = 20_000 + index
            invitees.append(User(id=invitee_id, username=f"invitee{index}"))
            referrals.append(Referral(inviter_id=20, invitee_id=invitee_id))
            if index < 4:
                orders.append(
                    Order(
                        order_id=f"GIFT:{invitee_id}",
                        internal_user_id=invitee_id,
                        plan_id=1,
                        original_price=0,
                        final_price=0,
                        status="SUCCESS",
                        tx_hash=f"manual_invitee_{invitee_id}",
                    )
                )
        session.add_all(invitees)
        session.add_all(referrals)
        session.add_all(orders)
        await session.commit()


@pytest.fixture(autouse=True)
def _clear_backend_task_status_cache():
    system_service.clear_backend_task_status_cache()
    yield
    system_service.clear_backend_task_status_cache()


@pytest.mark.asyncio
async def test_refund_bot_task_payload_uses_finalize_terminated_task():
    finalize_terminated_task = AsyncMock(
        return_value=TaskTerminationFinalizationResult(
            terminated=True,
            refunded=True,
        )
    )

    result = await system_service.refund_bot_task_payload(
        task_id="registry-task-1",
        get_system_task_stats_func=AsyncMock(
            return_value=(
                {
                    "registry-task-1": {
                        "user_id": 123,
                        "username": "tester",
                        "cost": 7,
                    }
                },
                {},
            )
        ),
        finalize_terminated_task_func=finalize_terminated_task,
    )

    assert result == {
        "status": "success",
        "message": "Task registry-task-1 terminated and 7 credits refunded.",
    }
    finalize_terminated_task.assert_awaited_once_with(
        registry_task_id="registry-task-1",
        user_id=123,
        username="tester",
        cost=7,
        should_refund=True,
        refund_task_type="refund_admin_force",
    )


@pytest.mark.asyncio
async def test_clean_zombie_tasks_payload_uses_finalize_terminated_task():
    finalize_terminated_task = AsyncMock(
        return_value=TaskTerminationFinalizationResult(
            terminated=True,
            refunded=True,
        )
    )

    result = await system_service.clean_zombie_tasks_payload(
        get_system_task_stats_func=AsyncMock(
            return_value=(
                {
                    "registry-task-1": {
                        "user_id": 123,
                        "username": "tester",
                        "cost": 7,
                        "created_at": 0,
                    },
                    "registry-task-2": {
                        "user_id": 456,
                        "username": "tester2",
                        "cost": 0,
                        "created_at": 7900,
                    },
                },
                {},
            )
        ),
        finalize_terminated_task_func=finalize_terminated_task,
        now_func=lambda: 8000,
    )

    assert result == {
        "status": "success",
        "message": "Cleaned up 1 zombie tasks.",
        "removed": 1,
    }
    finalize_terminated_task.assert_awaited_once_with(
        registry_task_id="registry-task-1",
        user_id=123,
        username="tester",
        cost=7,
        should_refund=True,
        refund_task_type="refund_admin_force_cleanup",
    )


def test_count_tasks_by_type_uses_worker_execution_task_types():
    tasks = {
        "task-1": {"task_type": "edit"},
        "task-2": {"task_type": "img2img_lora"},
        "task-3": {"task_type": "custom_video"},
        "task-4": {"task_type": "video_lora"},
        "task-5": {"task_type": "image_to_video"},
        "task-6": {"task_type": "ltx_video"},
        "task-7": {"task_type": "txt2img"},
        "task-8": {"task_type": "doggy_style"},
        "task-9": {"task_type": "face_video_step1"},
        "task-10": {"task_type": None},
    }

    assert system_service.count_tasks_by_type(tasks) == {
        "img2img": 1,
        "img2img_lora": 1,
        "image_to_video": 4,
        "ltx_video": 1,
        "t2i-pornmaster-turbo": 1,
        "face_video": 1,
        "unknown": 1,
    }


@pytest.mark.asyncio
async def test_get_pending_queue_wait_details_uses_created_at_not_priority_score():
    redis_client = _FakePendingRedis(
        pending_scores={
            "newer-but-higher-priority": 1.0,
            "oldest-by-created-at": 9999.0,
        },
        hashes={
            "comfy:task:newer-but-higher-priority": {
                "type": "custom_video",
                "created_at": "1900",
                "priority": "5",
            },
            "comfy:task:oldest-by-created-at": {
                "type": "image_to_video",
                "created_at": "1000",
                "priority": "0",
            },
        },
    )

    details = await system_service.get_pending_queue_wait_details(
        redis_url="redis://worker",
        redis_from_url_func=lambda *_args, **_kwargs: redis_client,
        now_func=lambda: 2000,
    )

    assert details["image_to_video"]["pending_count"] == 2
    assert details["image_to_video"]["max_pending_wait_seconds"] == 1000
    assert details["image_to_video"]["oldest_pending_task_id"] == "oldest-by-created-at"
    assert details["image_to_video"]["oldest_pending_created_at"] == 1000.0
    assert details["image_to_video"]["pending_wait_records"] == [
        {"wait_seconds": 100, "priority": 5},
        {"wait_seconds": 1000, "priority": 0},
    ]
    assert redis_client.closed is True


@pytest.mark.asyncio
async def test_get_pending_queue_wait_details_falls_back_to_bot_redis_when_worker_queue_empty(
    monkeypatch,
):
    worker_redis = _FakePendingRedis()
    bot_redis = _FakePendingRedis(
        pending_scores={"backend-task-1": 1.0},
        hashes={
            "comfy:task:backend-task-1": {
                "type": "custom_video",
                "created_at": "1000",
                "priority": "0",
            },
        },
    )
    clients = {
        "redis://worker": worker_redis,
        "redis://bot": bot_redis,
    }

    monkeypatch.setenv("WORKER_REDIS_URL", "redis://worker")
    monkeypatch.setenv("REDIS_URL", "redis://bot")

    details = await system_service.get_pending_queue_wait_details(
        redis_from_url_func=lambda url, **_kwargs: clients[url],
        now_func=lambda: 2000,
    )

    assert details["image_to_video"]["pending_count"] == 1
    assert details["image_to_video"]["max_pending_wait_seconds"] == 1000
    assert worker_redis.closed is True
    assert bot_redis.closed is True


@pytest.mark.asyncio
async def test_get_pending_queue_wait_details_counts_low_trust_free_tier_users():
    redis_client = _FakePendingRedis(
        pending_scores={
            "backend-task-low-1": 1.0,
            "backend-task-low-2": 2.0,
            "backend-task-normal": 3.0,
        },
        hashes={
            "comfy:task:backend-task-low-1": {
                "type": "image_to_video",
                "created_at": "1000",
                "priority": "0",
            },
            "comfy:task:backend-task-low-2": {
                "type": "image_to_video",
                "created_at": "1010",
                "priority": "0",
            },
            "comfy:task:backend-task-normal": {
                "type": "i2i_pro",
                "created_at": "1020",
                "priority": "3",
            },
        },
    )
    get_low_trust_user_ids = AsyncMock(return_value={10})

    details = await system_service.get_pending_queue_wait_details(
        redis_url="redis://worker",
        redis_from_url_func=lambda *_args, **_kwargs: redis_client,
        now_func=lambda: 2000,
        backend_task_user_ids={
            "backend-task-low-1": 10,
            "backend-task-low-2": 10,
            "backend-task-normal": 20,
        },
        get_low_trust_free_tier_user_ids_func=get_low_trust_user_ids,
    )

    image_detail = details["image_to_video"]
    assert image_detail["pending_count"] == 2
    assert image_detail["low_trust_free_tier_task_count"] == 2
    assert image_detail["low_trust_free_tier_user_count"] == 1
    assert image_detail["max_non_low_trust_pending_wait_seconds"] is None
    assert image_detail[system_service.LOW_TRUST_FREE_TIER_USER_IDS_DETAIL_KEY] == {10}
    assert details["i2i_pro"]["low_trust_free_tier_task_count"] == 0
    assert details["i2i_pro"]["max_non_low_trust_pending_wait_seconds"] == 980
    get_low_trust_user_ids.assert_awaited_once_with({10, 20})


@pytest.mark.asyncio
async def test_get_low_trust_free_tier_user_ids_excludes_high_quality_inviters():
    engine, session_factory = await _create_low_trust_session_factory()
    try:
        await _seed_dashboard_low_trust_case(session_factory)

        low_trust_user_ids = await system_service.get_low_trust_free_tier_user_ids(
            {10, 20, 30, 40},
            session_factory=session_factory,
        )

        assert low_trust_user_ids == {10}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_pending_queue_wait_details_excludes_unknown_users_from_non_low_trust_wait():
    redis_client = _FakePendingRedis(
        pending_scores={
            "backend-task-low": 1.0,
            "backend-task-normal": 2.0,
            "backend-task-unknown": 3.0,
        },
        hashes={
            "comfy:task:backend-task-low": {
                "type": "pornmaster_flux2_single_edit",
                "created_at": "900",
                "priority": "0",
            },
            "comfy:task:backend-task-normal": {
                "type": "pornmaster_flux2_single_edit",
                "created_at": "1000",
                "priority": "0",
            },
            "comfy:task:backend-task-unknown": {
                "type": "pornmaster_flux2_single_edit",
                "created_at": "500",
                "priority": "0",
            },
        },
    )

    details = await system_service.get_pending_queue_wait_details(
        redis_url="redis://worker",
        redis_from_url_func=lambda *_args, **_kwargs: redis_client,
        now_func=lambda: 2000,
        backend_task_user_ids={
            "backend-task-low": 10,
            "backend-task-normal": 20,
        },
        get_low_trust_free_tier_user_ids_func=AsyncMock(return_value={10}),
    )

    detail = details["pornmaster_flux2_single_edit"]
    assert detail["max_pending_wait_seconds"] == 1500
    assert detail["max_non_low_trust_pending_wait_seconds"] == 1000
    assert detail["low_trust_free_tier_task_count"] == 1


@pytest.mark.asyncio
async def test_get_pending_queue_wait_details_does_not_default_to_non_low_trust_on_lookup_failure():
    redis_client = _FakePendingRedis(
        pending_scores={
            "backend-task-normal": 1.0,
        },
        hashes={
            "comfy:task:backend-task-normal": {
                "type": "pornmaster_flux2_multi_edit",
                "created_at": "1000",
                "priority": "0",
            },
        },
    )

    details = await system_service.get_pending_queue_wait_details(
        redis_url="redis://worker",
        redis_from_url_func=lambda *_args, **_kwargs: redis_client,
        now_func=lambda: 2000,
        backend_task_user_ids={"backend-task-normal": 20},
        get_low_trust_free_tier_user_ids_func=AsyncMock(
            side_effect=RuntimeError("database down")
        ),
    )

    detail = details["pornmaster_flux2_multi_edit"]
    assert detail["max_pending_wait_seconds"] == 1000
    assert detail["max_non_low_trust_pending_wait_seconds"] is None


@pytest.mark.asyncio
async def test_runpod_profile_queue_details_count_tasks_until_last_non_low_trust_pending():
    active_tasks = {
        "txt2img-task": {"task_type": "txt2img"},
        "face-swap-task": {"task_type": "face_swap_v2"},
    }
    pending_wait_details = {
        "t2i-pornmaster-turbo": {
            "pending_count": 3,
            "max_pending_wait_seconds": 300,
            "max_non_low_trust_pending_wait_seconds": 200,
            "pending_queue_records": [
                {
                    "queue_index": 0,
                    "execution_type": "t2i-pornmaster-turbo",
                    "is_non_low_trust": False,
                },
                {
                    "queue_index": 3,
                    "execution_type": "t2i-pornmaster-turbo",
                    "is_non_low_trust": True,
                },
                {
                    "queue_index": 5,
                    "execution_type": "t2i-pornmaster-turbo",
                    "is_non_low_trust": False,
                },
            ],
        },
        "face_swap_v2": {
            "pending_count": 2,
            "max_pending_wait_seconds": 250,
            "max_non_low_trust_pending_wait_seconds": 100,
            "pending_queue_records": [
                {
                    "queue_index": 2,
                    "execution_type": "face_swap_v2",
                    "is_non_low_trust": False,
                },
                {
                    "queue_index": 4,
                    "execution_type": "face_swap_v2",
                    "is_non_low_trust": True,
                },
            ],
        },
        "image_to_video": {
            "pending_count": 1,
            "max_pending_wait_seconds": 400,
            "max_non_low_trust_pending_wait_seconds": 400,
            "pending_queue_records": [
                {
                    "queue_index": 1,
                    "execution_type": "image_to_video",
                    "is_non_low_trust": True,
                },
            ],
        },
    }

    data = await system_service.get_system_status_proxy_payload(
        httpx_async_client_factory=lambda **_kwargs: _FakeAsyncClient(
            {
                "queue_size": 0,
                "queue_by_type": {},
                "active_workers": 1,
                "healthy_workers": 1,
                "comfy_online": True,
            }
        ),
        get_system_task_stats_func=AsyncMock(return_value=(active_tasks, {})),
        get_pending_queue_wait_details_func=AsyncMock(
            return_value=pending_wait_details
        ),
    )

    profiles = {item["profile"]: item for item in data["runpod_profile_queue_details"]}
    i2i_profile = profiles["i2i_pro"]

    assert i2i_profile["pending_count"] == 5
    assert i2i_profile["last_non_low_trust_pending_queue_index"] == 4
    assert i2i_profile["non_low_trust_clear_pending_count"] == 4
    assert i2i_profile["non_low_trust_clear_pending_count_by_task_type"] == {
        "t2i-pornmaster-turbo": 2,
        "face_swap_v2": 2,
    }
    assert (
        "pending_queue_records"
        not in data["queue_by_type_details"]["t2i-pornmaster-turbo"]
    )
    assert profiles["image_to_video"]["non_low_trust_clear_pending_count"] == 1


@pytest.mark.asyncio
async def test_get_system_status_proxy_payload_uses_active_task_registry_counts():
    middleware_payload = {
        "queue_size": 71,
        "queue_by_type": {"i2i_pro": 23, "ltx_video": 33},
        "active_workers": 9,
        "healthy_workers": 7,
        "error_workers": 1,
        "quarantined_workers": 1,
        "workers_by_status": {"running": 3, "idle": 4, "error": 1, "quarantined": 1},
        "comfy_online": True,
    }
    active_tasks = {
        "registry-task-1": {
            "task_type": "i2i_pro",
            "backend_task_id": "backend-task-1",
            "user_id": 1001,
        },
        "registry-task-2": {
            "task_type": "ltx_video",
            "backend_task_id": "backend-task-2",
            "user_id": 1002,
        },
        "registry-task-3": {
            "task_type": "ltx_video",
            "backend_task_id": "backend-task-3",
            "user_id": 1003,
        },
    }
    pending_wait_details = {
        "ltx_video": {
            "pending_count": 1,
            "max_pending_wait_seconds": 742,
            "oldest_pending_task_id": "backend-task-2",
            "oldest_pending_created_at": 1782050000.0,
            "low_trust_free_tier_task_count": 1,
            "low_trust_free_tier_user_count": 1,
            system_service.LOW_TRUST_FREE_TIER_USER_IDS_DETAIL_KEY: {1002},
        }
    }
    get_pending_queue_wait_details = AsyncMock(return_value=pending_wait_details)

    data = await system_service.get_system_status_proxy_payload(
        httpx_async_client_factory=lambda **_kwargs: _FakeAsyncClient(
            middleware_payload
        ),
        get_system_task_stats_func=AsyncMock(
            return_value=(active_tasks, {1001: 1, 1002: 2})
        ),
        get_pending_queue_wait_details_func=get_pending_queue_wait_details,
    )

    assert data["queue_size"] == 3
    assert data["queue_by_type"] == {"i2i_pro": 1, "ltx_video": 2}
    assert data["queue_by_type_details"] == {
        "i2i_pro": {
            "active_count": 1,
            "pending_count": 0,
            "max_pending_wait_seconds": None,
            "max_non_low_trust_pending_wait_seconds": None,
            "oldest_pending_task_id": None,
            "oldest_pending_created_at": None,
            "low_trust_free_tier_task_count": 0,
            "low_trust_free_tier_user_count": 0,
        },
        "ltx_video": {
            "active_count": 2,
            "pending_count": 1,
            "max_pending_wait_seconds": 742,
            "max_non_low_trust_pending_wait_seconds": None,
            "oldest_pending_task_id": "backend-task-2",
            "oldest_pending_created_at": 1782050000.0,
            "low_trust_free_tier_task_count": 1,
            "low_trust_free_tier_user_count": 1,
        },
    }
    assert (
        system_service.LOW_TRUST_FREE_TIER_USER_IDS_DETAIL_KEY
        not in data["queue_by_type_details"]["ltx_video"]
    )
    assert data["low_trust_free_tier_pending_task_count"] == 1
    assert data["low_trust_free_tier_pending_user_count"] == 1
    get_pending_queue_wait_details.assert_awaited_once_with(
        backend_task_user_ids={
            "backend-task-1": 1001,
            "backend-task-2": 1002,
            "backend-task-3": 1003,
        }
    )
    assert data["middleware_queue_size"] == 71
    assert data["middleware_queue_by_type"] == {"i2i_pro": 23, "ltx_video": 33}
    assert data["concurrency_locks"] == 3
    assert data["healthy_workers"] == 7
    assert data["error_workers"] == 1
    assert data["quarantined_workers"] == 1
    assert data["workers_by_status"] == {
        "running": 3,
        "idle": 4,
        "error": 1,
        "quarantined": 1,
    }


@pytest.mark.asyncio
async def test_get_system_status_proxy_payload_groups_runpod_profile_queue_details():
    active_tasks = {
        "txt2img-task": {"task_type": "txt2img"},
        "i2i-task": {"task_type": "i2i_pro"},
        "face-swap-task": {"task_type": "face_swap_v2"},
        "scail2-action-task": {"task_type": "scail2_action_transfer"},
        "scail2-face-swap-task": {"task_type": "scail2_face_swap_v2"},
        "pornmaster-single-task": {"task_type": "pornmaster_flux2_single_edit"},
        "pornmaster-multi-task": {"task_type": "pornmaster_flux2_multi_edit"},
    }
    pending_wait_details = {
        "t2i-pornmaster-turbo": {
            "pending_count": 2,
            "max_pending_wait_seconds": 300,
            "max_non_low_trust_pending_wait_seconds": 280,
            "oldest_pending_task_id": "pending-txt2img",
            "oldest_pending_created_at": 1782050100.0,
        },
        "face_swap_v2": {
            "pending_count": 3,
            "max_pending_wait_seconds": 901,
            "max_non_low_trust_pending_wait_seconds": 700,
            "oldest_pending_task_id": "pending-face-swap",
            "oldest_pending_created_at": 1782050000.0,
        },
        "scail2_video_replacement": {
            "pending_count": 2,
            "max_pending_wait_seconds": 620,
            "max_non_low_trust_pending_wait_seconds": 500,
            "oldest_pending_task_id": "pending-scail2-replacement",
            "oldest_pending_created_at": 1782050200.0,
        },
        "scail2_face_swap_v2": {
            "pending_count": 9,
            "max_pending_wait_seconds": 999,
            "oldest_pending_task_id": "pending-scail2-face-swap",
            "oldest_pending_created_at": 1782050300.0,
        },
        "pornmaster_flux2_single_edit": {
            "pending_count": 1,
            "max_pending_wait_seconds": 800,
            "max_non_low_trust_pending_wait_seconds": 800,
            "oldest_pending_task_id": "pending-pornmaster-single",
            "oldest_pending_created_at": 1782050400.0,
        },
        "pornmaster_flux2_multi_edit": {
            "pending_count": 2,
            "max_pending_wait_seconds": 1200,
            "max_non_low_trust_pending_wait_seconds": 1000,
            "oldest_pending_task_id": "pending-pornmaster-multi",
            "oldest_pending_created_at": 1782050500.0,
        },
    }

    data = await system_service.get_system_status_proxy_payload(
        httpx_async_client_factory=lambda **_kwargs: _FakeAsyncClient(
            {
                "queue_size": 0,
                "queue_by_type": {},
                "active_workers": 1,
                "healthy_workers": 1,
                "comfy_online": True,
            }
        ),
        get_system_task_stats_func=AsyncMock(return_value=(active_tasks, {})),
        get_pending_queue_wait_details_func=AsyncMock(
            return_value=pending_wait_details
        ),
    )

    profiles = {item["profile"]: item for item in data["runpod_profile_queue_details"]}

    assert list(profiles) == [
        "img2img",
        "image_to_video",
        "wan22_video_v2",
        "i2i_pro",
        "scail2",
        "ltx_video",
        "pornmaster_flux2_edit",
        "pornmaster_flux2_edit_bf16",
    ]
    assert profiles["i2i_pro"] == {
        "profile": "i2i_pro",
        "label": "i2i_pro / txt2img / face_swap_v2",
        "supported_task_types": [
            "i2i_pro",
            "t2i-pornmaster-turbo",
            "face_swap_v2",
        ],
        "autoscaler_enabled": True,
        "active_count": 3,
        "pending_count": 5,
        "active_count_by_task_type": {
            "i2i_pro": 1,
            "t2i-pornmaster-turbo": 1,
            "face_swap_v2": 1,
        },
        "pending_count_by_task_type": {
            "t2i-pornmaster-turbo": 2,
            "face_swap_v2": 3,
        },
        "max_pending_wait_seconds": 901,
        "max_non_low_trust_pending_wait_seconds": 700,
        "non_low_trust_clear_pending_count": 0,
        "non_low_trust_clear_pending_count_by_task_type": {},
        "last_non_low_trust_pending_queue_index": None,
        "oldest_pending_task_id": "pending-face-swap",
        "oldest_pending_created_at": 1782050000.0,
        "pending_wait_records": [],
    }
    assert profiles["scail2"]["active_count"] == 1
    assert profiles["scail2"]["pending_count"] == 2
    assert profiles["scail2"]["max_pending_wait_seconds"] == 620
    assert profiles["scail2"]["max_non_low_trust_pending_wait_seconds"] == 500
    assert profiles["scail2"]["oldest_pending_task_id"] == "pending-scail2-replacement"
    assert profiles["ltx_video"]["active_count"] == 0
    assert profiles["ltx_video"]["pending_count"] == 0
    assert profiles["ltx_video"]["max_pending_wait_seconds"] is None
    assert profiles["pornmaster_flux2_edit"]["label"] == "pornmaster_flux2 / 自由P图 v2"
    assert profiles["pornmaster_flux2_edit"]["supported_task_types"] == [
        "pornmaster_flux2_single_edit",
        "pornmaster_flux2_multi_edit",
    ]
    assert profiles["pornmaster_flux2_edit"]["autoscaler_enabled"] is True
    assert profiles["pornmaster_flux2_edit"]["active_count"] == 2
    assert profiles["pornmaster_flux2_edit"]["pending_count"] == 3
    assert profiles["pornmaster_flux2_edit"]["max_pending_wait_seconds"] == 1200
    assert (
        profiles["pornmaster_flux2_edit"]["max_non_low_trust_pending_wait_seconds"]
        == 1000
    )
    assert profiles["pornmaster_flux2_edit_bf16"]["label"] == (
        "pornmaster_flux2 BF16 / 自由P图 v2.5 + v3 共用执行池"
    )
    assert profiles["pornmaster_flux2_edit_bf16"]["supported_task_types"] == [
        "pornmaster_flux2_edit_bf16",
        "pornmaster_flux2_multi_edit_bf16",
    ]
    assert profiles["pornmaster_flux2_edit_bf16"]["autoscaler_enabled"] is True
    assert profiles["pornmaster_flux2_edit_bf16"]["active_count"] == 0
    assert profiles["pornmaster_flux2_edit_bf16"]["pending_count"] == 0


@pytest.mark.asyncio
async def test_get_system_workers_proxy_payload_annotates_runpod_locks():
    async def annotate(payload):
        payload["workers"][0]["runpod_locked"] = True
        return payload

    data = await system_service.get_system_workers_proxy_payload(
        httpx_async_client_factory=lambda **_kwargs: _FakeAsyncClient(
            {
                "workers": [
                    {
                        "agent_id": "runpod_prod_wan22_video_v2_manual_03",
                        "provider": "runpod",
                    }
                ],
                "count": 1,
            }
        ),
        annotate_runpod_locks_func=annotate,
    )

    assert data["workers"][0]["runpod_locked"] is True


@pytest.mark.asyncio
async def test_get_system_status_proxy_payload_degrades_when_pending_wait_fails():
    active_tasks = {
        "registry-task-1": {"task_type": "i2i_pro"},
    }

    data = await system_service.get_system_status_proxy_payload(
        httpx_async_client_factory=lambda **_kwargs: _FakeAsyncClient(
            {
                "queue_size": 1,
                "queue_by_type": {"i2i_pro": 1},
                "active_workers": 1,
                "healthy_workers": 1,
                "comfy_online": True,
            }
        ),
        get_system_task_stats_func=AsyncMock(return_value=(active_tasks, {})),
        get_pending_queue_wait_details_func=AsyncMock(
            side_effect=RuntimeError("worker redis down")
        ),
    )

    assert data["queue_size"] == 1
    assert data["queue_by_type"] == {"i2i_pro": 1}
    assert data["queue_by_type_details"]["i2i_pro"] == {
        "active_count": 1,
        "pending_count": 0,
        "max_pending_wait_seconds": None,
        "max_non_low_trust_pending_wait_seconds": None,
        "oldest_pending_task_id": None,
        "oldest_pending_created_at": None,
        "low_trust_free_tier_task_count": 0,
        "low_trust_free_tier_user_count": 0,
    }
    assert data["low_trust_free_tier_pending_task_count"] == 0
    assert data["low_trust_free_tier_pending_user_count"] == 0


@pytest.mark.asyncio
async def test_sync_user_concurrency_payload_repairs_excess_lock():
    sync_func = AsyncMock()

    result = await system_service.sync_user_concurrency_payload(
        user_id=123,
        get_system_task_stats_func=AsyncMock(
            return_value=(
                {
                    "task-1": {"user_id": 123},
                    "task-2": {"user_id": 999},
                },
                {123: 2},
            )
        ),
        sync_user_concurrency_func=sync_func,
    )

    assert result["status"] == "success"
    sync_func.assert_awaited_once_with(123, 1)


@pytest.mark.asyncio
async def test_get_concurrency_stats_payload_includes_effective_identity_limits():
    now = datetime.now()

    result = await system_service.get_concurrency_stats_payload(
        get_system_task_stats_func=AsyncMock(
            return_value=(
                {
                    "task-1": {"user_id": 123, "username": "task-name"},
                    "task-2": {"user_id": 456},
                },
                {123: 2, 456: 1, 789: 4},
            )
        ),
        session_factory=lambda: _FakeDbSession(
            [
                SimpleNamespace(
                    id=123,
                    username="db-name",
                    current_identity="核心弟子",
                    identity_expire_at=now + timedelta(days=1),
                ),
                SimpleNamespace(
                    id=456,
                    username="expired-user",
                    current_identity="真传弟子",
                    identity_expire_at=now - timedelta(days=1),
                ),
                SimpleNamespace(
                    id=789,
                    username="lifetime-user",
                    current_identity="内门弟子",
                    identity_expire_at=None,
                ),
            ]
        ),
    )

    rows = {row["user_id"]: row for row in result["data"]}

    assert rows[123]["username"] == "task-name"
    assert rows[123]["current_identity"] == "核心弟子"
    assert rows[123]["effective_identity"] == "核心弟子"
    assert rows[123]["max_concurrent_tasks"] == 8
    assert rows[456]["current_identity"] == "真传弟子"
    assert rows[456]["effective_identity"] == "外门弟子"
    assert rows[456]["max_concurrent_tasks"] == 3
    assert rows[789]["current_identity"] == "内门弟子"
    assert rows[789]["effective_identity"] == "内门弟子"
    assert rows[789]["max_concurrent_tasks"] == 5


@pytest.mark.asyncio
async def test_get_active_bot_tasks_payload_merges_user_and_backend_status():
    tasks = {
        "task-1": {
            "user_id": 123,
            "backend_task_id": "backend-1",
            "task_type": "i2i_pro",
        },
        "task-2": {
            "user_id": 456,
            "task_type": "ltx_video",
        },
    }

    result = await system_service.get_active_bot_tasks_payload(
        get_system_task_stats_func=AsyncMock(return_value=(tasks, {})),
        session_factory=lambda: _FakeDbSession(
            [
                SimpleNamespace(
                    id=123,
                    user_group="金丹期",
                    current_identity="核心弟子",
                    full_name="炼丹道人",
                    username="tester_handle",
                )
            ]
        ),
        request_backend_status_func=AsyncMock(
            return_value=_FakeResponse({"status": "pending", "queue_pos": 4})
        ),
    )

    assert result["status"] == "success"
    assert result["count"] == 2
    assert result["tasks"]["task-1"]["user_group"] == "金丹期"
    assert result["tasks"]["task-1"]["user_identity"] == "核心弟子"
    assert result["tasks"]["task-1"]["display_name"] == "炼丹道人"
    assert result["tasks"]["task-1"]["execution_status"] == "pending"
    assert result["tasks"]["task-1"]["queue_position"] == 4
    assert result["tasks"]["task-2"]["user_group"] == "未知"
    assert result["tasks"]["task-2"]["display_name"] == "User_456"
    assert result["tasks"]["task-2"]["execution_status"] == "submitting"


@pytest.mark.asyncio
async def test_fetch_backend_task_statuses_uses_short_cache(monkeypatch):
    request_backend_status_func = AsyncMock(
        return_value=_FakeResponse({"status": "pending", "queue_pos": 5})
    )
    monkeypatch.setattr(
        system_service,
        "BACKEND_TASK_STATUS_CACHE_TTL_SECONDS",
        5.0,
    )

    first = await system_service._fetch_backend_task_statuses(
        tasks={"task-1": {"backend_task_id": "backend-1"}},
        api_base="http://127.0.0.1:8003",
        request_backend_status_func=request_backend_status_func,
    )
    second = await system_service._fetch_backend_task_statuses(
        tasks={"task-1": {"backend_task_id": "backend-1"}},
        api_base="http://127.0.0.1:8003",
        request_backend_status_func=request_backend_status_func,
    )

    assert first == {"backend-1": {"status": "pending", "queue_pos": 5}}
    assert second == {"backend-1": {"status": "pending", "queue_pos": 5}}
    request_backend_status_func.assert_awaited_once_with("backend-1")


@pytest.mark.asyncio
async def test_fetch_backend_task_statuses_skips_global_circuit_breaker(monkeypatch):
    calls = []

    class FakeApiClient:
        async def _request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return _FakeResponse({"status": "pending", "queue_pos": 3})

    fake_api_client_module = ModuleType("src.api_client")
    fake_api_client_module.api_client = FakeApiClient()
    monkeypatch.setitem(sys.modules, "src.api_client", fake_api_client_module)
    system_service._backend_task_status_cache.clear()

    result = await system_service._fetch_backend_task_statuses(
        tasks={"task-1": {"backend_task_id": "backend-1"}},
        api_base="http://central-api-prod:8003",
    )

    assert result == {"backend-1": {"status": "pending", "queue_pos": 3}}
    assert calls == [
        (
            "GET",
            "http://central-api-prod:8003/status/backend-1",
            {"timeout": 2, "use_circuit_breaker": False},
        )
    ]


@pytest.mark.asyncio
async def test_fetch_backend_task_statuses_prunes_old_cache(monkeypatch):
    request_backend_status_func = AsyncMock(
        side_effect=[
            _FakeResponse({"status": "pending"}),
            _FakeResponse({"status": "running"}),
            _FakeResponse({"status": "done"}),
        ]
    )
    monkeypatch.setattr(
        system_service,
        "BACKEND_TASK_STATUS_CACHE_TTL_SECONDS",
        30.0,
    )
    monkeypatch.setattr(
        system_service,
        "BACKEND_TASK_STATUS_CACHE_MAX_ENTRIES",
        1,
    )

    await system_service._fetch_backend_task_statuses(
        tasks={"task-1": {"backend_task_id": "backend-1"}},
        api_base="http://127.0.0.1:8003",
        request_backend_status_func=request_backend_status_func,
    )
    await system_service._fetch_backend_task_statuses(
        tasks={"task-2": {"backend_task_id": "backend-2"}},
        api_base="http://127.0.0.1:8003",
        request_backend_status_func=request_backend_status_func,
    )
    await system_service._fetch_backend_task_statuses(
        tasks={"task-1": {"backend_task_id": "backend-1"}},
        api_base="http://127.0.0.1:8003",
        request_backend_status_func=request_backend_status_func,
    )

    assert len(system_service._backend_task_status_cache) == 1
    assert [call.args[0] for call in request_backend_status_func.await_args_list] == [
        "backend-1",
        "backend-2",
        "backend-1",
    ]


@pytest.mark.asyncio
async def test_dashboard_health_check_returns_503_when_database_init_failed():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/health",
        "headers": [],
        "app": SimpleNamespace(
            state=SimpleNamespace(
                dashboard_health={
                    "database_ready": False,
                    "startup_complete": True,
                    "database_error": "db unavailable",
                }
            )
        ),
    }

    response = await system_router.health_check(Request(scope))

    assert response.status_code == 503
    assert b'"status":"degraded"' in response.body
    assert b'"database_error":"db unavailable"' in response.body


@pytest.mark.asyncio
async def test_dashboard_health_check_returns_ok_when_startup_completed():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/health",
        "headers": [],
        "app": SimpleNamespace(
            state=SimpleNamespace(
                dashboard_health={
                    "database_ready": True,
                    "startup_complete": True,
                    "database_error": None,
                }
            )
        ),
    }

    response = await system_router.health_check(Request(scope))

    assert response.status_code == 200
    assert b'"status":"ok"' in response.body
