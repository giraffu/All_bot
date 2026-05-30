import json
import logging
import math
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import case, delete, desc, func, or_, select, update
from sqlalchemy.orm import selectinload

from src.core.billing_core_membership import (
    DEFAULT_IDENTITY,
    IDENTITY_PRIORITY,
    IDENTITY_RATIO,
    normalize_membership_identity,
)
from src.database.models import (
    AffiliateRedeem,
    AffiliateTransaction,
    CheckinHistory,
    GalleryComment,
    GalleryPost,
    History,
    MembershipPlan,
    Order,
    Referral,
    TemplateContribution,
    User,
    UserInteraction,
    UserLog,
)
from src.services.affiliate_redeem_service import is_membership_settlement_v2_enabled
from src.services.membership_settlement_service import (
    MembershipSettlementAuditSource,
    settle_membership_plan_in_session,
)
from src.services.storage import storage
from src.web_api.services.users_history_service import get_my_favorites_payload

logger = logging.getLogger("dashboard.users")

USER_LIST_DEFAULT_SORT_BY = "created_at"
USER_LIST_DEFAULT_SORT_ORDER = "desc"
USER_LIST_SORT_FIELDS = {
    "id": User.id,
    "credits": User.credits,
    "checkin_count": User.checkin_count,
    "referral_count": User.referral_count,
    "generation_count": User.generation_count,
    "created_at": User.created_at,
    "last_activity": User.last_activity,
}


def _normalize_user_list_sort(sort_by: str | None, sort_order: str | None) -> tuple[str, str]:
    normalized_sort_by = (sort_by or USER_LIST_DEFAULT_SORT_BY).strip()
    normalized_sort_order = (sort_order or USER_LIST_DEFAULT_SORT_ORDER).strip().lower()

    if normalized_sort_by not in USER_LIST_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid sort_by. Allowed values: "
                + ", ".join(sorted(USER_LIST_SORT_FIELDS))
            ),
        )
    if normalized_sort_order not in {"asc", "desc"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid sort_order. Allowed values: asc, desc",
        )
    return normalized_sort_by, normalized_sort_order


def _apply_user_list_sort(stmt, sort_by: str, sort_order: str):
    sort_column = USER_LIST_SORT_FIELDS[sort_by]
    if sort_order == "asc":
        primary_order = sort_column.asc()
        secondary_order = User.id.asc()
    else:
        primary_order = sort_column.desc()
        secondary_order = User.id.desc()

    if sort_by == "id":
        return stmt.order_by(primary_order)
    return stmt.order_by(primary_order.nullslast(), secondary_order)


async def get_users_payload(
    *,
    db,
    skip: int = 0,
    limit: int = 20,
    query: str | None = None,
    query_partial: bool = True,
    identity: str | None = None,
    user_group: str | None = None,
    username: str | None = None,
    username_partial: bool = False,
    sort_by: str | None = None,
    sort_order: str | None = None,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        sort_by, sort_order = _normalize_user_list_sort(sort_by, sort_order)
        stmt = select(User)

        if query:
            query_filters = []
            if query.isdigit():
                query_filters.append(User.id == int(query))
            if query_partial:
                query_filters.extend(
                    [
                        User.full_name.ilike(f"%{query}%"),
                        User.username.ilike(f"%{query}%"),
                    ]
                )
            else:
                query_filters.extend([User.full_name == query, User.username == query])
            stmt = stmt.where(or_(*query_filters))
        if identity:
            if identity == "外门弟子":
                stmt = stmt.where(
                    (User.current_identity == identity) | (User.current_identity.is_(None))
                )
            else:
                stmt = stmt.where(User.current_identity == identity)
        if user_group:
            if user_group == "凡人":
                stmt = stmt.where((User.user_group == user_group) | (User.user_group.is_(None)))
            else:
                stmt = stmt.where(User.user_group == user_group)
        if username:
            if username_partial:
                stmt = stmt.where(User.username.ilike(f"%{username}%"))
            else:
                stmt = stmt.where(User.username == username)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.options(selectinload(User.inviter_user))
        stmt = _apply_user_list_sort(stmt, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        users = result.scalars().all()

        items = []
        for user in users:
            user_dict = {column.name: getattr(user, column.name) for column in user.__table__.columns}
            user_dict["referral_count"] = user.referral_count or 0
            user_dict["last_activity"] = user.last_activity
            user_dict["generation_count"] = user.generation_count or 0
            user_dict["checkin_count"] = user.checkin_count or 0
            user_dict["current_identity"] = user.current_identity or "外门弟子"
            user_dict["identity_expire_at"] = user.identity_expire_at
            user_dict["total_contributions"] = int(user.total_contributions or 0)
            user_dict["approved_contributions"] = int(user.approved_contributions or 0)
            user_dict["channel_joined"] = (
                bool(user.is_channel_member) if hasattr(user, "is_channel_member") else False
            )
            if user.inviter_user:
                user_dict["inviter_info"] = {
                    "id": user.inviter_user.id,
                    "username": user.inviter_user.username,
                    "full_name": user.inviter_user.full_name,
                }
            else:
                user_dict["inviter_info"] = None
            items.append(user_dict)

        return {
            "items": items,
            "total": total,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error getting users: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def get_user_stats_payload(*, user_id: int, db, logger_override: logging.Logger | None = None) -> dict:
    active_logger = logger_override or logger
    try:
        recharge_stmt = (
            select(
                func.sum(case((Order.payment_channel == "RMB", Order.final_price), else_=0)).label("total_recharge_rmb"),
                func.sum(case((Order.payment_channel == "TON", Order.final_price), else_=0)).label("total_recharge_ton"),
                func.sum(case((Order.payment_channel == "XTR", Order.final_price), else_=0)).label("total_recharge_stars"),
            )
            .where(Order.status == "SUCCESS")
            .where(Order.tx_hash.notlike("manual_%"))
            .where(Order.internal_user_id == user_id)
        )
        recharge_result = await db.execute(recharge_stmt)
        row = recharge_result.one_or_none()
        return {
            "total_recharge_ton": float(row.total_recharge_ton or 0) if row else 0.0,
            "total_recharge_stars": int(row.total_recharge_stars or 0) if row else 0,
            "total_recharge_rmb": float(row.total_recharge_rmb or 0) if row else 0.0,
        }
    except Exception as exc:
        active_logger.error(f"Error getting user stats: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def get_user_favorites_payload(
    *,
    user_id: int,
    page: int,
    size: int,
    task_type: str | None,
    db,
    logger_override: logging.Logger | None = None,
):
    active_logger = logger_override or logger
    user = await _load_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        # Reuse the same favorites payload builder as the Web favorites page.
        return await get_my_favorites_payload(
            page=page,
            size=size,
            task_type=task_type,
            current_user=SimpleNamespace(id=user_id),
            db=db,
        )
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error getting user favorites for {user_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def _load_user(db, user_id: int):
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


def _safe_rowcount(result) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


def _max_value(*values):
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return max(filtered)


def _min_value(*values):
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return min(filtered)


def _compute_user_group(
    *, referral_count: int, checkin_count: int, generation_count: int, is_channel_member: bool
) -> str:
    if referral_count > 100 and checkin_count > 300 and generation_count > 1000:
        return "元婴期"
    if referral_count > 10 and checkin_count > 30 and generation_count > 100:
        return "金丹期"
    if referral_count > 1 and checkin_count > 3 and generation_count > 10:
        return "筑基期"
    if is_channel_member:
        return "练气期"
    return "凡人"


def _merge_membership_state(source_user: User, target_user: User) -> tuple[str, datetime | None]:
    now = datetime.now()
    entitlements: list[tuple[str, float]] = []
    for user in (source_user, target_user):
        identity = normalize_membership_identity(getattr(user, "current_identity", None))
        expire_at = getattr(user, "identity_expire_at", None)
        if identity != DEFAULT_IDENTITY and expire_at and expire_at > now:
            remaining_days = max((expire_at - now).total_seconds() / 86400.0, 0.0)
            entitlements.append((identity, remaining_days))

    if not entitlements:
        return DEFAULT_IDENTITY, None

    final_identity = max(
        (identity for identity, _ in entitlements),
        key=lambda value: IDENTITY_PRIORITY.get(value, 0),
    )
    total_identity_value = sum(
        remaining_days * IDENTITY_RATIO.get(identity, 1)
        for identity, remaining_days in entitlements
    )
    merged_days = max(
        1,
        math.ceil(total_identity_value / IDENTITY_RATIO.get(final_identity, 1)),
    )
    return final_identity, now + timedelta(days=merged_days)


async def _decrement_gallery_post_counters(db, duplicate_rows) -> None:
    counter_field_map = {
        "like": "likes_count",
        "dislike": "dislikes_count",
        "apply": "applied_count",
    }
    for post_id, action_type, deleted_count in duplicate_rows:
        counter_name = counter_field_map.get(action_type)
        if not post_id or not counter_name or not deleted_count:
            continue
        counter_column = getattr(GalleryPost, counter_name)
        await db.execute(
            update(GalleryPost)
            .where(GalleryPost.id == post_id)
            .values(**{counter_name: func.greatest(counter_column - deleted_count, 0)})
        )


async def _prune_duplicate_interactions(
    *, db, source_user_id: int, target_user_id: int, actions: list[str]
) -> int:
    target_posts_subquery = select(UserInteraction.post_id).where(
        UserInteraction.user_id == target_user_id,
        UserInteraction.action_type.in_(actions),
    )
    duplicate_rows = (
        await db.execute(
            select(
                UserInteraction.post_id,
                UserInteraction.action_type,
                func.count(UserInteraction.id).label("deleted_count"),
            )
            .where(
                UserInteraction.user_id == source_user_id,
                UserInteraction.action_type.in_(actions),
                UserInteraction.post_id.in_(target_posts_subquery),
            )
            .group_by(UserInteraction.post_id, UserInteraction.action_type)
        )
    ).all()
    if not duplicate_rows:
        return 0

    await db.execute(
        delete(UserInteraction).where(
            UserInteraction.user_id == source_user_id,
            UserInteraction.action_type.in_(actions),
            UserInteraction.post_id.in_(target_posts_subquery),
        )
    )
    await _decrement_gallery_post_counters(db, duplicate_rows)
    return sum(int(deleted_count or 0) for _, _, deleted_count in duplicate_rows)


async def _merge_user_interactions(*, db, source_user_id: int, target_user_id: int) -> dict:
    duplicate_reactions_deleted = await _prune_duplicate_interactions(
        db=db,
        source_user_id=source_user_id,
        target_user_id=target_user_id,
        actions=["like", "dislike"],
    )
    duplicate_applies_deleted = await _prune_duplicate_interactions(
        db=db,
        source_user_id=source_user_id,
        target_user_id=target_user_id,
        actions=["apply"],
    )
    move_result = await db.execute(
        update(UserInteraction)
        .where(UserInteraction.user_id == source_user_id)
        .values(user_id=target_user_id)
    )
    return {
        "interactions_moved": _safe_rowcount(move_result),
        "duplicate_reactions_deleted": duplicate_reactions_deleted,
        "duplicate_applies_deleted": duplicate_applies_deleted,
    }


async def _merge_referral_graph(*, db, source_user: User, target_user: User) -> dict:
    source_referral_result = await db.execute(
        select(Referral).where(Referral.invitee_id == source_user.id)
    )
    target_referral_result = await db.execute(
        select(Referral).where(Referral.invitee_id == target_user.id)
    )
    source_invitee_referral = source_referral_result.scalar_one_or_none()
    target_invitee_referral = target_referral_result.scalar_one_or_none()

    inherited_inviter_id = None
    if source_invitee_referral is not None:
        inherited_inviter_id = source_invitee_referral.inviter_id
    elif source_user.invited_by not in (None, target_user.id):
        inherited_inviter_id = source_user.invited_by

    if target_user.invited_by == source_user.id:
        target_user.invited_by = inherited_inviter_id
    elif target_user.invited_by is None and inherited_inviter_id not in (None, target_user.id):
        target_user.invited_by = inherited_inviter_id

    repoint_invited_users_result = await db.execute(
        update(User)
        .where(User.invited_by == source_user.id, User.id != target_user.id)
        .values(invited_by=target_user.id)
    )
    delete_self_referral_result = await db.execute(
        delete(Referral).where(
            Referral.inviter_id == source_user.id,
            Referral.invitee_id == target_user.id,
        )
    )

    source_binding_moved = 0
    source_binding_removed = 0
    if source_invitee_referral is not None:
        if (
            target_invitee_referral is None
            and source_invitee_referral.inviter_id != target_user.id
        ):
            source_invitee_referral.invitee_id = target_user.id
            source_binding_moved = 1
        else:
            await db.delete(source_invitee_referral)
            source_binding_removed = 1

    repoint_referrals_result = await db.execute(
        update(Referral)
        .where(Referral.inviter_id == source_user.id)
        .values(inviter_id=target_user.id)
    )
    referral_count_result = await db.execute(
        select(func.count(Referral.id)).where(Referral.inviter_id == target_user.id)
    )
    target_user.referral_count = int(referral_count_result.scalar() or 0)

    return {
        "invited_users_repointed": _safe_rowcount(repoint_invited_users_result),
        "invite_relations_repointed": _safe_rowcount(repoint_referrals_result),
        "self_referrals_deleted": _safe_rowcount(delete_self_referral_result),
        "source_inviter_binding_moved": source_binding_moved,
        "source_inviter_binding_removed": source_binding_removed,
    }


async def delete_user_payload(*, user_id: int, db, logger_override: logging.Logger | None = None) -> dict:
    active_logger = logger_override or logger
    try:
        user = await _load_user(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        await db.execute(delete(CheckinHistory).where(CheckinHistory.user_id == user_id))
        await db.execute(delete(History).where(History.user_id == user_id))
        await db.execute(
            delete(Referral).where(
                (Referral.inviter_id == user_id) | (Referral.invitee_id == user_id)
            )
        )
        await db.execute(
            delete(TemplateContribution).where(TemplateContribution.user_id == user_id)
        )
        comment_count_rows = (
            await db.execute(
                select(
                    GalleryComment.post_id,
                    func.count(GalleryComment.id).label("deleted_count"),
                )
                .where(
                    GalleryComment.user_id == user_id,
                    GalleryComment.is_active.is_(True),
                )
                .group_by(GalleryComment.post_id)
            )
        ).all()
        await db.execute(delete(GalleryComment).where(GalleryComment.user_id == user_id))
        for post_id, deleted_count in comment_count_rows:
            if not post_id or not deleted_count:
                continue
            await db.execute(
                update(GalleryPost)
                .where(GalleryPost.id == post_id)
                .values(
                    comments_count=func.greatest(GalleryPost.comments_count - deleted_count, 0)
                )
            )
        await db.delete(user)
        await db.commit()
        return {
            "message": f"User {user_id} and all associated data deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        active_logger.error(f"Error deleting user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def update_user_credits_payload(
    *,
    user_id: int,
    request,
    db,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        user = await _load_user(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        old_credits = user.credits
        user.credits = request.credits
        credit_change = request.credits - old_credits
        if request.checkin_count is not None:
            user.checkin_count = request.checkin_count
        await db.commit()

        if credit_change != 0:
            from src.services.log_service import LogService

            await LogService.log_action(
                user_id=user_id,
                username=user.username or user.full_name,
                operation_type="admin_update",
                credit_change=credit_change,
                current_balance=user.credits,
                extra_info={"source": "dashboard_admin_edit"},
            )

        return {
            "status": "ok",
            "credits": user.credits,
            "checkin_count": user.checkin_count,
        }
    except Exception as exc:
        active_logger.error(f"Error updating user data: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def clear_user_history_payload(
    *,
    user_id: int,
    db,
    storage_client=None,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    if storage_client is None:
        storage_client = storage.client

    try:
        result = await db.execute(select(History).where(History.user_id == user_id))
        history_records = result.scalars().all()

        for record in history_records:
            if record.input_file:
                for file_name in record.input_file.split("|"):
                    if file_name.startswith("template:"):
                        continue
                    try:
                        storage_client.remove_object("bot-data", file_name)
                    except Exception as file_exc:
                        active_logger.warning(f"Failed to delete input file {file_name}: {file_exc}")

            if record.output_file:
                bucket = "comfyui-temp" if "/" not in record.output_file else "bot-data"
                try:
                    storage_client.remove_object(bucket, record.output_file)
                except Exception as file_exc:
                    active_logger.warning(
                        f"Failed to delete output file {record.output_file}: {file_exc}"
                    )

        await db.execute(delete(History).where(History.user_id == user_id))
        user = await _load_user(db, user_id)
        if user:
            user.generation_count = 0
            user.last_activity = None
        await db.commit()
        return {"status": "ok", "message": f"Cleared history for user {user_id}"}
    except Exception as exc:
        active_logger.error(f"Error clearing history: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def admin_gift_plan_payload(
    *,
    user_id: int,
    request,
    db,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        user = await _load_user(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        plan_result = await db.execute(select(MembershipPlan).where(MembershipPlan.id == request.plan_id))
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        order_id = f"GIFT:{user_id}:{plan.id}:{int(datetime.now().timestamp())}"
        tx_hash = f"manual_{uuid.uuid4().hex[:16]}"

        new_order = Order(
            order_id=order_id,
            internal_user_id=user_id,
            plan_id=plan.id,
            original_price=0,
            final_price=0,
            status="SUCCESS",
            tx_hash=tx_hash,
            paid_at=datetime.now(),
        )
        db.add(new_order)
        if is_membership_settlement_v2_enabled():
            await db.flush()
            await settle_membership_plan_in_session(
                locked_user=user,
                plan=plan,
                audit_source=MembershipSettlementAuditSource(
                    source="admin_gift_plan",
                    source_channel="ADMIN_GIFT",
                    source_order_id=order_id,
                    source_tx_hash=tx_hash,
                ),
                session=db,
                now=datetime.now(),
                grant_reward_credits=True,
            )
        else:
            from src.core.billing_core import calculate_identity_conversion

            final_identity, new_expire_at = calculate_identity_conversion(
                current_identity=user.current_identity,
                current_expire_at=user.identity_expire_at,
                new_identity=plan.identity_name,
                duration_days=plan.duration_days,
            )
            user.credits += plan.reward_credits
            user.current_identity = final_identity
            user.identity_expire_at = new_expire_at

            extra_info = {
                "order_id": order_id,
                "plan_name": plan.name,
                "note": request.note,
                "is_gift": True,
            }
            db.add(
                UserLog(
                    user_id=user.id,
                    username=user.username,
                    operation_type="recharge",
                    credit_change=plan.reward_credits,
                    current_balance=user.credits,
                    extra_info=json.dumps(extra_info, ensure_ascii=False),
                )
            )

        await db.commit()
        return {
            "status": "ok",
            "message": f"Successfully gifted plan {plan.name} to user {user.id}",
            "new_credits": user.credits,
            "new_identity": user.current_identity,
        }
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        active_logger.error(f"Error gifting plan: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def transfer_user_data_payload(
    *,
    user_id: int,
    request,
    db,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        target_user_id = int(request.target_user_id)
        if user_id == target_user_id:
            raise HTTPException(status_code=400, detail="源用户和目标用户不能相同")

        result = await db.execute(
            select(User)
            .where(User.id.in_([user_id, target_user_id]))
            .with_for_update()
        )
        users_by_id = {user.id: user for user in result.scalars().all()}
        source_user = users_by_id.get(user_id)
        target_user = users_by_id.get(target_user_id)

        if not source_user:
            raise HTTPException(status_code=404, detail="源用户不存在")
        if not target_user:
            raise HTTPException(status_code=404, detail="目标用户不存在")

        moved_counts: dict[str, int] = {}

        history_update_result = await db.execute(
            update(History).where(History.user_id == user_id).values(user_id=target_user_id)
        )
        moved_counts["history_rows"] = _safe_rowcount(history_update_result)

        template_update_result = await db.execute(
            update(TemplateContribution)
            .where(TemplateContribution.user_id == user_id)
            .values(user_id=target_user_id)
        )
        moved_counts["template_contributions"] = _safe_rowcount(template_update_result)

        checkin_update_result = await db.execute(
            update(CheckinHistory)
            .where(CheckinHistory.user_id == user_id)
            .values(user_id=target_user_id)
        )
        moved_counts["checkin_history_rows"] = _safe_rowcount(checkin_update_result)

        user_log_update_result = await db.execute(
            update(UserLog).where(UserLog.user_id == user_id).values(user_id=target_user_id)
        )
        moved_counts["user_logs"] = _safe_rowcount(user_log_update_result)

        order_update_result = await db.execute(
            update(Order)
            .where(Order.internal_user_id == user_id)
            .values(internal_user_id=target_user_id)
        )
        moved_counts["orders"] = _safe_rowcount(order_update_result)

        affiliate_tx_update_result = await db.execute(
            update(AffiliateTransaction)
            .where(AffiliateTransaction.user_id == user_id)
            .values(user_id=target_user_id)
        )
        moved_counts["affiliate_transactions"] = _safe_rowcount(
            affiliate_tx_update_result
        )

        affiliate_redeem_update_result = await db.execute(
            update(AffiliateRedeem)
            .where(AffiliateRedeem.user_id == user_id)
            .values(user_id=target_user_id)
        )
        moved_counts["affiliate_redeems"] = _safe_rowcount(
            affiliate_redeem_update_result
        )

        gallery_post_update_result = await db.execute(
            update(GalleryPost)
            .where(GalleryPost.user_id == user_id)
            .values(user_id=target_user_id)
        )
        moved_counts["gallery_posts"] = _safe_rowcount(gallery_post_update_result)

        gallery_comment_update_result = await db.execute(
            update(GalleryComment)
            .where(GalleryComment.user_id == user_id)
            .values(user_id=target_user_id)
        )
        moved_counts["gallery_comments"] = _safe_rowcount(gallery_comment_update_result)

        moved_counts.update(
            await _merge_user_interactions(
                db=db,
                source_user_id=user_id,
                target_user_id=target_user_id,
            )
        )
        moved_counts.update(
            await _merge_referral_graph(
                db=db,
                source_user=source_user,
                target_user=target_user,
            )
        )

        target_user.credits = int(target_user.credits or 0) + int(source_user.credits or 0)
        target_user.checkin_count = int(target_user.checkin_count or 0) + int(
            source_user.checkin_count or 0
        )
        target_user.generation_count = int(target_user.generation_count or 0) + int(
            source_user.generation_count or 0
        )
        target_user.total_contributions = int(target_user.total_contributions or 0) + int(
            source_user.total_contributions or 0
        )
        target_user.approved_contributions = int(
            target_user.approved_contributions or 0
        ) + int(source_user.approved_contributions or 0)
        target_user.last_checkin = _max_value(
            target_user.last_checkin,
            source_user.last_checkin,
        )
        target_user.last_activity = _max_value(
            target_user.last_activity,
            source_user.last_activity,
        )
        target_user.created_at = _min_value(target_user.created_at, source_user.created_at)
        target_user.is_channel_member = bool(
            target_user.is_channel_member or source_user.is_channel_member
        )
        target_user.language_code = target_user.language_code or source_user.language_code
        target_user.full_name = target_user.full_name or source_user.full_name

        merged_identity, merged_expire_at = _merge_membership_state(
            source_user,
            target_user,
        )
        target_user.current_identity = merged_identity
        target_user.identity_expire_at = merged_expire_at
        target_user.user_group = _compute_user_group(
            referral_count=int(target_user.referral_count or 0),
            checkin_count=int(target_user.checkin_count or 0),
            generation_count=int(target_user.generation_count or 0),
            is_channel_member=bool(target_user.is_channel_member),
        )

        await db.delete(source_user)
        await db.commit()

        moved_counts["source_user_deleted"] = 1

        try:
            from src.services.log_service import LogService

            await LogService.log_action(
                user_id=target_user_id,
                username=target_user.username or target_user.full_name,
                operation_type="admin_transfer_user_data",
                credit_change=int(source_user.credits or 0),
                current_balance=int(target_user.credits or 0),
                extra_info={
                    "source_user_id": user_id,
                    "target_user_id": target_user_id,
                    "source_username": source_user.username,
                    "source_full_name": source_user.full_name,
                    "note": getattr(request, "note", None),
                    "moved_counts": moved_counts,
                    "source_deleted": True,
                },
            )
        except Exception as log_exc:
            active_logger.warning(
                "User transfer succeeded but log write failed for %s -> %s: %s",
                user_id,
                target_user_id,
                log_exc,
            )

        return {
            "status": "ok",
            "message": f"已将用户 {user_id} 的业务数据转移到用户 {target_user_id}，并删除源用户",
            "source_user_id": user_id,
            "target_user_id": target_user_id,
            "moved_counts": moved_counts,
            "merged_profile": {
                "credits": int(target_user.credits or 0),
                "current_identity": target_user.current_identity,
                "identity_expire_at": target_user.identity_expire_at,
                "user_group": target_user.user_group,
                "referral_count": int(target_user.referral_count or 0),
                "checkin_count": int(target_user.checkin_count or 0),
                "generation_count": int(target_user.generation_count or 0),
                "is_channel_member": bool(target_user.is_channel_member),
            },
        }
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        active_logger.error(f"Error transferring user data {user_id} -> {request.target_user_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def update_user_identity_payload(
    *,
    user_id: int,
    request,
    db,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        user = await _load_user(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        old_identity = user.current_identity
        old_expire = user.identity_expire_at
        new_expire = request.expire_at
        if (
            request.convert
            and not request.expire_at
            and old_expire
            and old_expire > datetime.now()
            and old_identity != request.identity
        ):
            from src.core.billing_core import calculate_identity_manual_conversion

            new_expire = calculate_identity_manual_conversion(
                current_identity=old_identity,
                current_expire_at=old_expire,
                new_identity=request.identity,
            )
            active_logger.info(
                f"Admin manual convert for user {user_id}: {old_identity} -> {request.identity}"
            )

        user.current_identity = request.identity
        if new_expire:
            user.identity_expire_at = new_expire
        await db.commit()

        from src.services.log_service import LogService

        await LogService.log_action(
            user_id=user_id,
            username=user.username or user.full_name,
            operation_type="admin_update_identity",
            credit_change=0,
            current_balance=user.credits,
            extra_info={
                "old_identity": old_identity,
                "new_identity": user.current_identity,
                "old_expire": str(old_expire) if old_expire else None,
                "new_expire": str(user.identity_expire_at) if user.identity_expire_at else None,
                "converted": request.convert,
                "source": "dashboard_admin_edit",
            },
        )

        return {
            "status": "ok",
            "id": user.id,
            "current_identity": user.current_identity,
            "identity_expire_at": user.identity_expire_at,
        }
    except Exception as exc:
        active_logger.error(f"Error updating user identity: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def update_user_group_payload(
    *,
    user_id: int,
    request,
    db,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        user = await _load_user(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        old_group = user.user_group
        user.user_group = request.user_group
        await db.commit()

        from src.services.log_service import LogService

        await LogService.log_action(
            user_id=user_id,
            username=user.username or user.full_name,
            operation_type="admin_update_group",
            credit_change=0,
            current_balance=user.credits,
            extra_info={
                "old_group": old_group,
                "new_group": user.user_group,
                "source": "dashboard_admin_edit",
            },
        )
        return {"status": "ok", "id": user.id, "user_group": user.user_group}
    except Exception as exc:
        active_logger.error(f"Error updating user group: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def update_user_channel_member_payload(
    *,
    user_id: int,
    request,
    db,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    try:
        user = await _load_user(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        old_status = user.is_channel_member
        user.is_channel_member = request.is_channel_member
        await db.commit()

        from src.services.log_service import LogService

        await LogService.log_action(
            user_id=user_id,
            username=user.username or user.full_name,
            operation_type="admin_update_channel_member",
            credit_change=0,
            current_balance=user.credits,
            extra_info={
                "old_status": old_status,
                "new_status": user.is_channel_member,
                "source": "dashboard_admin_edit",
            },
        )

        if request.is_channel_member and not old_status:
            from src.services.permission_service import permission_service

            await permission_service.check_channel_reward(
                tg_id=user.telegram_id or user.id,
                username=user.username,
                full_name=user.full_name,
                internal_user_id=user.id,
            )
            await permission_service.refresh_user_group(user.id, is_member=True)

        return {
            "status": "ok",
            "id": user.id,
            "is_channel_member": user.is_channel_member,
        }
    except Exception as exc:
        active_logger.error(f"Error updating user channel member status: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
