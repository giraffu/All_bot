from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from src.services.user_tier_policy_service import (
    DEFAULT_USER_TIER_POLICY_CONFIG,
    get_identity_policy,
    get_priority_for_usage,
    normalize_user_tier_policy_config,
    resolve_flashback_limit,
    resolve_video_permissions,
    validate_user_tier_policy_config,
)
from src.services.permission_identity_priority_service import PermissionIdentityPriorityService


def test_default_policy_preserves_existing_rights_and_small_flashback_steps():
    config = normalize_user_tier_policy_config(None)

    assert config["cultivation_ranks"]["筑基期"]["upgrade"] == {
        "invitations": 2,
        "checkins": 4,
        "generations": 11,
        "channel_member": False,
    }
    assert config["membership_identities"]["核心弟子"]["benefits"]["concurrent_tasks"] == 8
    assert [
        config["cultivation_ranks"][rank]["benefits"]["flashback_bottles"]
        for rank in ("凡人", "练气期", "筑基期", "金丹期", "元婴期")
    ] == [8, 9, 10, 12, 14]


def test_policy_normalization_fixes_unknown_missing_and_out_of_range_values():
    config = normalize_user_tier_policy_config(
        {
            "cultivation_ranks": {
                "筑基期": {
                    "benefits": {"flashback_bottles": 999},
                    "video": {"resolutions": ["bad", "720p", "512p"]},
                },
                "不存在": {"benefits": {"web_access": True}},
            },
            "membership_identities": {
                "内门弟子": {"benefits": {"concurrent_tasks": 7}}
            },
            "low_trust": {"successful_invitee_rate_percent_threshold": 101},
        }
    )

    assert set(config["cultivation_ranks"]) == set(DEFAULT_USER_TIER_POLICY_CONFIG["cultivation_ranks"])
    assert config["cultivation_ranks"]["筑基期"]["benefits"]["flashback_bottles"] == 10
    assert config["cultivation_ranks"]["筑基期"]["video"]["resolutions"] == ["512p", "720p"]
    assert config["membership_identities"]["内门弟子"]["benefits"]["concurrent_tasks"] == 7
    assert config["low_trust"]["successful_invitee_rate_percent_threshold"] == 3


def test_combined_rights_use_maximum_not_addition():
    config = deepcopy(DEFAULT_USER_TIER_POLICY_CONFIG)

    assert resolve_flashback_limit(config, "筑基期", "核心弟子") == 12
    assert resolve_flashback_limit(config, "元婴期", "真传弟子") == 14
    assert resolve_video_permissions(config, "筑基期", "核心弟子") == (
        ["512p", "720p", "1024p"],
        ["5s", "8s", "10s"],
    )
    assert get_identity_policy(config, "unknown") == config["membership_identities"]["外门弟子"]


def test_priority_rules_support_bounded_and_fallback_bands():
    rules = [
        {"daily_usage_lt": 10, "priority": 8},
        {"daily_usage_lt": 50, "priority": 3},
        {"daily_usage_lt": None, "priority": 1},
    ]

    assert get_priority_for_usage(rules, 9) == 8
    assert get_priority_for_usage(rules, 10) == 3
    assert get_priority_for_usage(rules, 500) == 1


def test_policy_rejects_higher_tier_that_loses_a_lower_tier_benefit():
    config = deepcopy(DEFAULT_USER_TIER_POLICY_CONFIG)
    config["membership_identities"]["核心弟子"]["benefits"]["favorite_limit"] = 200

    with pytest.raises(ValueError, match="核心弟子.*favorite_limit"):
        validate_user_tier_policy_config(config)


@pytest.mark.asyncio
async def test_saved_upgrade_thresholds_are_used_by_group_refresh():
    policy = deepcopy(DEFAULT_USER_TIER_POLICY_CONFIG)
    policy["cultivation_ranks"]["筑基期"]["upgrade"].update(
        invitations=1,
        checkins=2,
        generations=3,
    )
    quota = type("Quota", (), {})()
    quota.get_user_stats = AsyncMock(
        return_value={
            "invitation_count": 1,
            "checkin_count": 2,
            "generation_count": 3,
            "is_channel_member": False,
        }
    )
    quota.update_user_group = AsyncMock()
    service = PermissionIdentityPriorityService(
        quota,
        policy_loader=AsyncMock(return_value=policy),
    )

    result = await service.refresh_user_group(123)

    assert result == "筑基期"
    quota.update_user_group.assert_awaited_once_with(123, "筑基期")


@pytest.mark.asyncio
async def test_saved_low_trust_threshold_and_bonus_are_used_for_priority():
    policy = deepcopy(DEFAULT_USER_TIER_POLICY_CONFIG)
    policy["low_trust"].update(checkin_threshold=20, trusted_priority_bonus=55)
    quota = type("Quota", (), {})()
    quota.get_user_stats = AsyncMock(return_value={"checkin_count": 8, "generation_count": 1})
    service = PermissionIdentityPriorityService(
        quota,
        policy_loader=AsyncMock(return_value=policy),
    )
    service._has_successful_order = AsyncMock()

    result = await service.calculate_user_priority(123)

    assert result == 85
    service._has_successful_order.assert_not_awaited()
