import datetime
from collections.abc import Awaitable, Callable
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from src.core.billing_core import get_default_billing_core_providers


class BreakthroughConditionDTO(BaseModel):
    type: str
    target: int
    current: int
    done: bool


class UserDashboardDTO(BaseModel):
    first_name: str
    current_group: str
    current_identity: str
    current_priority: int
    credits: int
    invitations: int
    checkins: int
    generations: int
    today_generations: int = 0
    invitation_recharge: Dict[str, Any]
    is_unlocked: bool

    # Newly structured fields to replace breakthrough_msg and identity_display
    breakthrough_conditions: List[BreakthroughConditionDTO]
    identity_expire_at: Optional[datetime.datetime]


def _get_user_detailed_stats_func() -> Callable[[int], Awaitable[dict]]:
    return get_default_billing_core_providers().get_permission_service_func().get_user_detailed_stats


async def get_user_dashboard_info(
    tg_id: int,
    first_name: str,
    *,
    get_user_detailed_stats_func: Optional[Callable[[int], Awaitable[dict]]] = None,
) -> UserDashboardDTO:
    get_user_detailed_stats_func = (
        get_user_detailed_stats_func or _get_user_detailed_stats_func()
    )
    stats = await get_user_detailed_stats_func(tg_id)

    current_group = stats["group"]
    current_identity = stats.get("identity", "外门弟子")
    current_priority = stats.get("priority", 0)

    breakthrough_conditions = []

    # Calculate breakthrough conditions structurally
    if current_group == "凡人":
        breakthrough_conditions.append(
            BreakthroughConditionDTO(
                type="channel_join", target=1, current=0, done=False
            )
        )
    elif current_group == "练气期":
        breakthrough_conditions.extend(
            [
                BreakthroughConditionDTO(
                    type="invite",
                    target=1,
                    current=stats["invitations"],
                    done=stats["invitations"] >= 1,
                ),
                BreakthroughConditionDTO(
                    type="checkin",
                    target=3,
                    current=stats["checkins"],
                    done=stats["checkins"] >= 3,
                ),
                BreakthroughConditionDTO(
                    type="generation",
                    target=10,
                    current=stats["generations"],
                    done=stats["generations"] >= 10,
                ),
            ]
        )
    elif current_group == "筑基期":
        breakthrough_conditions.extend(
            [
                BreakthroughConditionDTO(
                    type="invite",
                    target=10,
                    current=stats["invitations"],
                    done=stats["invitations"] >= 10,
                ),
                BreakthroughConditionDTO(
                    type="checkin",
                    target=30,
                    current=stats["checkins"],
                    done=stats["checkins"] >= 30,
                ),
                BreakthroughConditionDTO(
                    type="generation",
                    target=100,
                    current=stats["generations"],
                    done=stats["generations"] >= 100,
                ),
            ]
        )
    elif current_group == "金丹期":
        breakthrough_conditions.extend(
            [
                BreakthroughConditionDTO(
                    type="invite",
                    target=100,
                    current=stats["invitations"],
                    done=stats["invitations"] >= 100,
                ),
                BreakthroughConditionDTO(
                    type="checkin",
                    target=300,
                    current=stats["checkins"],
                    done=stats["checkins"] >= 300,
                ),
                BreakthroughConditionDTO(
                    type="generation",
                    target=1000,
                    current=stats["generations"],
                    done=stats["generations"] >= 1000,
                ),
            ]
        )
    # 元婴期 has no conditions, it's the max level currently.

    from src.constants import WEB_ACCESS_ALLOWED_IDENTITIES, WEB_ACCESS_ALLOWED_GROUPS

    is_unlocked = (
        current_identity in WEB_ACCESS_ALLOWED_IDENTITIES
        or current_group in WEB_ACCESS_ALLOWED_GROUPS
    )

    return UserDashboardDTO(
        first_name=first_name,
        current_group=current_group,
        current_identity=current_identity,
        current_priority=current_priority,
        credits=stats["credits"],
        invitations=stats["invitations"],
        checkins=stats["checkins"],
        generations=stats["generations"],
        today_generations=stats.get("today_generations", 0),
        invitation_recharge=stats["invitation_recharge"],
        is_unlocked=is_unlocked,
        breakthrough_conditions=breakthrough_conditions,
        identity_expire_at=stats.get("identity_expire_at"),
    )
