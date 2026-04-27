from pydantic import BaseModel
from typing import Dict, Any, Optional
from src.services.permission_service import permission_service

class UserDashboardDTO(BaseModel):
    first_name: str
    current_group: str
    current_identity: str
    current_priority: int
    credits: int
    invitations: int
    checkins: int
    generations: int
    invitation_recharge: Dict[str, Any]
    breakthrough_msg: str
    identity_display: str
    is_unlocked: bool

async def get_user_dashboard_info(tg_id: int, first_name: str, invite_link_template: str) -> UserDashboardDTO:
    stats = await permission_service.get_user_detailed_stats(tg_id)
    
    breakthrough_msg = ""
    current_group = stats['group']
    current_identity = stats.get('identity', '普通用户')
    current_priority = stats.get('priority', 0)
    
    if current_group == "凡人":
        breakthrough_msg = (
            "🚀 **突破至练气期条件**：\n"
            f"🔸 拜入宗门 [👉 [点击即刻拜入]({invite_link_template})]"
        )
    elif current_group == "练气期":
        inv_done = "✅" if stats['invitations'] > 1 else "❌"
        checkin_done = "✅" if stats['checkins'] > 3 else "❌"
        gen_done = "✅" if stats['generations'] > 10 else "❌"
        breakthrough_msg = (
            "🚀 **突破至筑基期(视野更加清晰了)条件**：\n"
            f"🔸 邀请道友 > 1人 ({inv_done})\n"
            f"🔸 累计签到 > 3天 ({checkin_done})\n"
            f"🔸 修炼次数 > 10次 ({gen_done})"
        )
    elif current_group == "筑基期":
        inv_done = "✅" if stats['invitations'] > 10 else "❌"
        checkin_done = "✅" if stats['checkins'] > 30 else "❌"
        gen_done = "✅" if stats['generations'] > 100 else "❌"
        breakthrough_msg = (
            "🚀 **突破至金丹期条件**：\n"
            f"🔸 邀请道友 > 10人 ({inv_done})\n"
            f"🔸 累计签到 > 30天 ({checkin_done})\n"
            f"🔸 修炼次数 > 100次 ({gen_done})"
        )
    elif current_group == "金丹期":
        inv_done = "✅" if stats['invitations'] > 100 else "❌"
        checkin_done = "✅" if stats['checkins'] > 300 else "❌"
        gen_done = "✅" if stats['generations'] > 1000 else "❌"
        breakthrough_msg = (
            "🚀 **突破至元婴期条件**：\n"
            f"🔸 邀请道友 > 100人 ({inv_done})\n"
            f"🔸 累计签到 > 300天 ({checkin_done})\n"
            f"🔸 修炼次数 > 1000次 ({gen_done})"
        )
    elif current_group == "元婴期":
        breakthrough_msg = "✨ **已修成元婴，神通广大，万法不侵**"

    identity_display = f"`{current_identity}`"
    if current_identity != "外门弟子" and stats.get('identity_expire_at'):
        from datetime import datetime
        now = datetime.now()
        expire_at = stats['identity_expire_at']
        if expire_at.tzinfo is not None:
            expire_at = expire_at.replace(tzinfo=None)
        if expire_at > now:
            remaining = expire_at - now
            days = remaining.days
            hours = remaining.seconds // 3600
            expire_str = expire_at.strftime('%Y-%m-%d %H:%M')
            if days > 0:
                identity_display += f" (剩余 {days} 天，{expire_str} 到期)"
            else:
                identity_display += f" (剩余 {hours} 小时，{expire_str} 到期)"
        else:
            identity_display += " (已过期)"

    allowed_identities = ["内门弟子", "核心弟子", "真传弟子"]
    allowed_groups = ["金丹期", "元婴期", "化神期", "炼虚期", "合体期", "大乘期", "渡劫期"]
    is_unlocked = current_identity in allowed_identities or current_group in allowed_groups

    return UserDashboardDTO(
        first_name=first_name,
        current_group=current_group,
        current_identity=current_identity,
        current_priority=current_priority,
        credits=stats['credits'],
        invitations=stats['invitations'],
        checkins=stats['checkins'],
        generations=stats['generations'],
        invitation_recharge=stats['invitation_recharge'],
        breakthrough_msg=breakthrough_msg,
        identity_display=identity_display,
        is_unlocked=is_unlocked
    )
