from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.core import billing_core
from src.core.exceptions import InsufficientCreditsError


def _make_concurrency_dependencies(
    *,
    identity: str | None,
    group: str = "筑基期",
    queue_size: int = 0,
    active_tasks: int = 1,
):
    get_identity = AsyncMock(return_value=identity)
    get_group = AsyncMock(return_value=group)
    get_system_status = AsyncMock(return_value={"queue_size": queue_size})
    increment_concurrency = AsyncMock(return_value=active_tasks)
    decrement_concurrency = AsyncMock()

    dependencies = SimpleNamespace(
        get_system_status_func=get_system_status,
        get_user_identity_func=get_identity,
        get_user_group_func=get_group,
        calculate_user_priority_func=AsyncMock(),
        increment_user_concurrency_func=increment_concurrency,
        decrement_user_concurrency_func=decrement_concurrency,
        deduct_credits_func=AsyncMock(),
        add_credits_func=AsyncMock(),
    )

    return dependencies, SimpleNamespace(
        get_identity=get_identity,
        get_group=get_group,
        get_system_status=get_system_status,
        increment_concurrency=increment_concurrency,
        decrement_concurrency=decrement_concurrency,
    )


@pytest.mark.asyncio
async def test_check_concurrency_lock_uses_explicit_dependencies():
    get_identity = AsyncMock(return_value="外门弟子")
    get_group = AsyncMock(return_value="凡人")
    get_system_status = AsyncMock(
        return_value={"queue_size": billing_core.LOW_TIER_QUEUE_SIZE_LIMIT + 1}
    )
    increment_concurrency = AsyncMock(return_value=1)
    decrement_concurrency = AsyncMock()

    dependencies = SimpleNamespace(
        get_system_status_func=get_system_status,
        get_user_identity_func=get_identity,
        get_user_group_func=get_group,
        calculate_user_priority_func=AsyncMock(),
        increment_user_concurrency_func=increment_concurrency,
        decrement_user_concurrency_func=decrement_concurrency,
        deduct_credits_func=AsyncMock(),
        add_credits_func=AsyncMock(),
    )

    allowed, message = await billing_core.check_concurrency_lock(
        123,
        dependencies=dependencies,
    )

    assert allowed is False
    assert "服务器繁忙" in message
    assert f"超过 {billing_core.LOW_TIER_QUEUE_SIZE_LIMIT} 个" in message
    get_identity.assert_awaited_once_with(123)
    get_group.assert_awaited_once_with(123)
    get_system_status.assert_awaited_once()
    increment_concurrency.assert_not_awaited()
    decrement_concurrency.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_concurrency_lock_allows_low_tier_at_queue_limit():
    get_identity = AsyncMock(return_value="外门弟子")
    get_group = AsyncMock(return_value="练气期")
    get_system_status = AsyncMock(
        return_value={"queue_size": billing_core.LOW_TIER_QUEUE_SIZE_LIMIT}
    )
    increment_concurrency = AsyncMock(return_value=1)
    decrement_concurrency = AsyncMock()

    dependencies = SimpleNamespace(
        get_system_status_func=get_system_status,
        get_user_identity_func=get_identity,
        get_user_group_func=get_group,
        calculate_user_priority_func=AsyncMock(),
        increment_user_concurrency_func=increment_concurrency,
        decrement_user_concurrency_func=decrement_concurrency,
        deduct_credits_func=AsyncMock(),
        add_credits_func=AsyncMock(),
    )

    allowed, message = await billing_core.check_concurrency_lock(
        123,
        dependencies=dependencies,
    )

    assert allowed is True
    assert message == ""
    get_system_status.assert_awaited_once()
    increment_concurrency.assert_awaited_once_with(123)
    decrement_concurrency.assert_not_awaited()


@pytest.mark.parametrize(
    ("identity", "limit"),
    [
        ("外门弟子", 3),
        ("内门弟子", 5),
        ("核心弟子", 8),
        ("真传弟子", 12),
    ],
)
@pytest.mark.asyncio
async def test_check_concurrency_lock_allows_at_identity_limit(identity, limit):
    dependencies, calls = _make_concurrency_dependencies(
        identity=identity,
        group="凡人",
        active_tasks=limit,
    )

    allowed, message = await billing_core.check_concurrency_lock(
        123,
        dependencies=dependencies,
    )

    assert allowed is True
    assert message == ""
    calls.increment_concurrency.assert_awaited_once_with(123)
    calls.decrement_concurrency.assert_not_awaited()


@pytest.mark.parametrize(
    ("identity", "limit", "over_limit_count"),
    [
        ("外门弟子", 3, 4),
        ("内门弟子", 5, 6),
        ("核心弟子", 8, 9),
        ("真传弟子", 12, 13),
    ],
)
@pytest.mark.asyncio
async def test_check_concurrency_lock_rejects_over_identity_limit_and_rolls_back(
    identity,
    limit,
    over_limit_count,
):
    dependencies, calls = _make_concurrency_dependencies(
        identity=identity,
        group="凡人",
        active_tasks=over_limit_count,
    )

    allowed, message = await billing_core.check_concurrency_lock(
        123,
        dependencies=dependencies,
    )

    assert allowed is False
    assert f"已有 {limit} 个任务正在处理中" in message
    calls.increment_concurrency.assert_awaited_once_with(123)
    calls.decrement_concurrency.assert_awaited_once_with(123)


@pytest.mark.parametrize("identity", ["凡人", "未知身份", None])
@pytest.mark.asyncio
async def test_check_concurrency_lock_falls_back_to_low_tier_limit(identity):
    dependencies, calls = _make_concurrency_dependencies(
        identity=identity,
        active_tasks=4,
    )

    allowed, message = await billing_core.check_concurrency_lock(
        123,
        dependencies=dependencies,
    )

    assert allowed is False
    assert "已有 3 个任务正在处理中" in message
    calls.increment_concurrency.assert_awaited_once_with(123)
    calls.decrement_concurrency.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_get_user_priority_and_identity_uses_explicit_dependencies():
    calculate_priority = AsyncMock(return_value=7)
    get_identity = AsyncMock(return_value="核心弟子")
    get_group = AsyncMock(return_value="筑基期")

    dependencies = SimpleNamespace(
        get_system_status_func=AsyncMock(),
        get_user_identity_func=get_identity,
        get_user_group_func=get_group,
        calculate_user_priority_func=calculate_priority,
        increment_user_concurrency_func=AsyncMock(),
        decrement_user_concurrency_func=AsyncMock(),
        deduct_credits_func=AsyncMock(),
        add_credits_func=AsyncMock(),
    )

    result = await billing_core.get_user_priority_and_identity(
        123,
        dependencies=dependencies,
    )

    assert result == (7, "核心弟子", "筑基期")
    calculate_priority.assert_awaited_once_with(123)
    get_identity.assert_awaited_once_with(123)
    get_group.assert_awaited_once_with(123)


def test_get_default_billing_core_dependencies_resolves_runtime_providers():
    permission_service = SimpleNamespace(
        get_user_identity=AsyncMock(),
        get_user_group=AsyncMock(),
        calculate_user_priority=AsyncMock(),
    )
    redis_client = SimpleNamespace(
        increment_user_concurrency=AsyncMock(),
        decrement_user_concurrency=AsyncMock(),
    )
    quota_manager = SimpleNamespace(
        deduct_credits=AsyncMock(),
        add_credits=AsyncMock(),
    )
    get_system_status = AsyncMock()

    providers = billing_core.BillingCoreProviders(
        get_system_status_func=get_system_status,
        get_permission_service_func=lambda: permission_service,
        get_redis_client_func=lambda: redis_client,
        get_quota_manager_func=lambda: quota_manager,
    )

    dependencies = billing_core.get_default_billing_core_dependencies(
        providers=providers
    )

    assert dependencies.get_system_status_func is get_system_status
    assert dependencies.get_user_identity_func is permission_service.get_user_identity
    assert dependencies.get_user_group_func is permission_service.get_user_group
    assert (
        dependencies.calculate_user_priority_func
        is permission_service.calculate_user_priority
    )
    assert (
        dependencies.increment_user_concurrency_func
        is redis_client.increment_user_concurrency
    )
    assert (
        dependencies.decrement_user_concurrency_func
        is redis_client.decrement_user_concurrency
    )
    assert dependencies.deduct_credits_func is quota_manager.deduct_credits
    assert dependencies.add_credits_func is quota_manager.add_credits


def test_build_default_billing_core_providers_uses_explicit_runtime_sources():
    get_system_status = AsyncMock()
    permission_loader = Mock(return_value=object())
    redis_loader = Mock(return_value=object())
    quota_loader = Mock(return_value=object())

    providers = billing_core.build_default_billing_core_providers(
        get_system_status_func=get_system_status,
        get_permission_service_func=permission_loader,
        get_redis_client_func=redis_loader,
        get_quota_manager_func=quota_loader,
    )

    assert providers.get_system_status_func is get_system_status
    assert providers.get_permission_service_func is permission_loader
    assert providers.get_redis_client_func is redis_loader
    assert providers.get_quota_manager_func is quota_loader


@pytest.mark.asyncio
async def test_check_and_deduct_credits_uses_atomic_deduct_without_precheck():
    mock_deduct = AsyncMock()
    dependencies = SimpleNamespace(
        get_system_status_func=AsyncMock(),
        get_user_identity_func=AsyncMock(),
        get_user_group_func=AsyncMock(),
        calculate_user_priority_func=AsyncMock(),
        increment_user_concurrency_func=AsyncMock(),
        decrement_user_concurrency_func=AsyncMock(),
        deduct_credits_func=mock_deduct,
        add_credits_func=AsyncMock(),
    )

    success, message = await billing_core.check_and_deduct_credits(
        123,
        5,
        "test_task",
        "tester",
        dependencies=dependencies,
    )

    assert success is True
    assert message == ""
    mock_deduct.assert_awaited_once_with(
        123, 5, username="tester", task_type="test_task"
    )


@pytest.mark.asyncio
async def test_check_and_deduct_credits_returns_atomic_insufficient_message():
    mock_deduct = AsyncMock(
        side_effect=InsufficientCreditsError(current=3, cost=5)
    )
    dependencies = SimpleNamespace(
        get_system_status_func=AsyncMock(),
        get_user_identity_func=AsyncMock(),
        get_user_group_func=AsyncMock(),
        calculate_user_priority_func=AsyncMock(),
        increment_user_concurrency_func=AsyncMock(),
        decrement_user_concurrency_func=AsyncMock(),
        deduct_credits_func=mock_deduct,
        add_credits_func=AsyncMock(),
    )

    success, message = await billing_core.check_and_deduct_credits(
        123,
        5,
        "test_task",
        "tester",
        dependencies=dependencies,
    )

    assert success is False
    assert "当前余额: `3` 灵石" in message
    assert "本次需要: `5` 灵石" in message
    mock_deduct.assert_awaited_once()


@pytest.mark.asyncio
async def test_refund_credits_uses_explicit_add_credits():
    mock_add = AsyncMock()
    dependencies = SimpleNamespace(
        get_system_status_func=AsyncMock(),
        get_user_identity_func=AsyncMock(),
        get_user_group_func=AsyncMock(),
        calculate_user_priority_func=AsyncMock(),
        increment_user_concurrency_func=AsyncMock(),
        decrement_user_concurrency_func=AsyncMock(),
        deduct_credits_func=AsyncMock(),
        add_credits_func=mock_add,
    )

    await billing_core.refund_credits(
        123,
        5,
        task_type="refund_case",
        username="tester",
        dependencies=dependencies,
    )

    mock_add.assert_awaited_once_with(
        123, 5, username="tester", task_type="refund_case"
    )


@pytest.mark.asyncio
async def test_refund_credits_passes_idempotency_key_and_reports_duplicate_skip():
    mock_add = AsyncMock(
        return_value=SimpleNamespace(old_balance=20, new_balance=20)
    )
    dependencies = SimpleNamespace(
        get_system_status_func=AsyncMock(),
        get_user_identity_func=AsyncMock(),
        get_user_group_func=AsyncMock(),
        calculate_user_priority_func=AsyncMock(),
        increment_user_concurrency_func=AsyncMock(),
        decrement_user_concurrency_func=AsyncMock(),
        deduct_credits_func=AsyncMock(),
        add_credits_func=mock_add,
    )

    refunded = await billing_core.refund_credits(
        123,
        5,
        task_type="refund_user_cancel",
        username="tester",
        idempotency_key="task_refund:refund_user_cancel:reg-1",
        dependencies=dependencies,
    )

    assert refunded is False
    mock_add.assert_awaited_once_with(
        123,
        5,
        username="tester",
        task_type="refund_user_cancel",
        idempotency_key="task_refund:refund_user_cancel:reg-1",
        extra_info={
            "credit_idempotency_key": "task_refund:refund_user_cancel:reg-1"
        },
    )


def test_calculate_membership_settlement_treats_unknown_identity_as_default():
    now = datetime(2026, 5, 20, 12, 0, 0)

    result = billing_core.calculate_membership_settlement(
        current_identity=None,
        current_expire_at=None,
        target_identity="内门弟子",
        duration_days=30,
        reward_credits=0,
        grant_reward_credits=False,
        now=now,
    )

    assert result.final_identity == "内门弟子"
    assert result.final_expire_at == now + timedelta(days=30)
    assert result.settlement_reason == "NEW_PURCHASE"


def test_calculate_membership_settlement_handles_upgrade_conversion():
    now = datetime(2026, 5, 20, 12, 0, 0)
    expire_at = now + timedelta(days=10)

    result = billing_core.calculate_membership_settlement(
        current_identity="内门弟子",
        current_expire_at=expire_at,
        target_identity="核心弟子",
        duration_days=30,
        reward_credits=0,
        grant_reward_credits=False,
        now=now,
    )

    assert result.final_identity == "核心弟子"
    assert result.converted_days == 4
    assert result.final_expire_at == now + timedelta(days=34)
    assert result.settlement_reason == "UPGRADE_CONVERSION"
    assert result.is_upgrade is True


def test_calculate_membership_settlement_handles_downgrade_extension():
    now = datetime(2026, 5, 20, 12, 0, 0)
    expire_at = now + timedelta(days=10)

    result = billing_core.calculate_membership_settlement(
        current_identity="真传弟子",
        current_expire_at=expire_at,
        target_identity="内门弟子",
        duration_days=30,
        reward_credits=0,
        grant_reward_credits=False,
        now=now,
    )

    assert result.final_identity == "真传弟子"
    assert result.converted_days == 6
    assert result.final_expire_at == expire_at + timedelta(days=6)
    assert result.settlement_reason == "DOWNGRADE_EXTENSION"
    assert result.kept_current_identity is True


def test_calculate_membership_settlement_supports_pure_credit_plan():
    now = datetime(2026, 5, 20, 12, 0, 0)
    expire_at = now + timedelta(days=10)

    result = billing_core.calculate_membership_settlement(
        current_identity="核心弟子",
        current_expire_at=expire_at,
        target_identity="核心弟子",
        duration_days=0,
        reward_credits=1200,
        grant_reward_credits=True,
        now=now,
    )

    assert result.final_identity == "核心弟子"
    assert result.final_expire_at == expire_at
    assert result.credits_to_grant == 1200
    assert result.settlement_reason == "PURE_CREDIT_PLAN"
    assert result.is_pure_credit_plan is True
