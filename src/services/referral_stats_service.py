from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import String, and_, case, cast, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.database.models import AffiliateRedeem, AffiliateTransaction, Order, Referral, User
from src.exchange_rates import get_exchange_rates

VALID_PAYMENT_CHANNELS = ("RMB", "TON", "XTR")
ZERO_DECIMAL = Decimal("0.0")
DISPLAY_MONEY_QUANT = Decimal("0.01")


def _round_money(value: Decimal | None) -> float:
    rounded = Decimal(str(value or 0)).quantize(
        DISPLAY_MONEY_QUANT, rounding=ROUND_HALF_UP
    )
    return float(rounded)


async def query_invitation_recharge_stats(
    session: AsyncSession, inviter_id: int
) -> dict:
    stmt = (
        select(
            Order.internal_user_id,
            Order.final_price,
            Order.payment_channel,
            Order.commission_usdt,
        )
        .join(Referral, Referral.invitee_id == Order.internal_user_id)
        .where(
            and_(
                Referral.inviter_id == inviter_id,
                Order.status == "SUCCESS",
                Order.final_price > 0,
                Order.commission_usdt > 0,
                Order.payment_channel.in_(VALID_PAYMENT_CHANNELS),
            )
        )
    )
    rows = (await session.execute(stmt)).all()

    ledger_stmt = select(
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            AffiliateTransaction.direction == "IN",
                            AffiliateTransaction.status == "SUCCESS",
                        ),
                        AffiliateTransaction.amount_usdt,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            AffiliateTransaction.direction == "OUT",
                            AffiliateTransaction.status == "SUCCESS",
                        ),
                        AffiliateTransaction.amount_usdt,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            AffiliateTransaction.direction == "IN",
                            AffiliateTransaction.status == "SUCCESS",
                        ),
                        AffiliateTransaction.amount_usdt,
                    ),
                    (
                        and_(
                            AffiliateTransaction.direction == "OUT",
                            AffiliateTransaction.status == "SUCCESS",
                        ),
                        -AffiliateTransaction.amount_usdt,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
    ).where(AffiliateTransaction.user_id == inviter_id)
    (
        total_commission_ledger_usdt,
        spent_commission_usdt,
        available_balance_usdt,
    ) = (
        await session.execute(ledger_stmt)
    ).all()[0]

    recharged_invitees = set()
    total_recharge_count = 0
    total_ton = ZERO_DECIMAL
    total_rmb = ZERO_DECIMAL
    total_stars = 0
    for invitee_id, final_price, payment_channel, commission_usdt in rows:
        if Decimal(str(commission_usdt or 0)) <= 0:
            continue

        recharged_invitees.add(invitee_id)
        total_recharge_count += 1

        if payment_channel == "TON":
            total_ton += Decimal(str(final_price))
        elif payment_channel == "RMB":
            total_rmb += Decimal(str(final_price))
        elif payment_channel == "XTR":
            total_stars += int(final_price)

    total_commission = _round_money(Decimal(str(total_commission_ledger_usdt or 0)))
    return {
        "recharged_invitees_count": len(recharged_invitees),
        "total_recharge_count": total_recharge_count,
        "total_ton": float(total_ton),
        "total_rmb": float(total_rmb),
        "total_stars": total_stars,
        "commission_usdt": total_commission,
        "total_commission_usdt": total_commission,
        "spent_commission_usdt": _round_money(Decimal(str(spent_commission_usdt or 0))),
        "available_balance_usdt": _round_money(
            Decimal(str(available_balance_usdt or 0))
        ),
    }


async def query_invited_recharge_totals_usdt(
    session: AsyncSession, inviter_ids: list[int]
) -> dict[int, float]:
    normalized_inviter_ids = [int(inviter_id) for inviter_id in inviter_ids if inviter_id]
    if not normalized_inviter_ids:
        return {}

    stmt = (
        select(
            Referral.inviter_id,
            Order.payment_channel,
            func.sum(Order.final_price).label("total_amount"),
        )
        .join(Order, Order.internal_user_id == Referral.invitee_id)
        .where(
            and_(
                Referral.inviter_id.in_(normalized_inviter_ids),
                Order.status == "SUCCESS",
                Order.final_price > 0,
                Order.payment_channel.in_(VALID_PAYMENT_CHANNELS),
            )
        )
        .group_by(Referral.inviter_id, Order.payment_channel)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return {}

    rates = await get_exchange_rates()
    rate_by_channel = {
        "TON": Decimal(str(rates.get("ton_to_usdt", 1.4))),
        "RMB": Decimal(str(rates.get("rmb_to_usdt", 1.0 / 6.7))),
        "XTR": Decimal(str(rates.get("stars_to_usdt", 0.013))),
    }

    totals: dict[int, Decimal] = {}
    for inviter_id, payment_channel, total_amount in rows:
        multiplier = rate_by_channel.get(payment_channel)
        if multiplier is None:
            continue
        totals[int(inviter_id)] = totals.get(int(inviter_id), ZERO_DECIMAL) + (
            Decimal(str(total_amount or 0)) * multiplier
        )

    return {
        inviter_id: _round_money(total_usdt)
        for inviter_id, total_usdt in totals.items()
    }


async def query_referral_rewards(session: AsyncSession) -> list[dict]:
    Invitee = aliased(User)
    stmt = (
        select(
            Order,
            User,  # Inviter
            Invitee,  # Invitee
        )
        .join(Referral, Referral.invitee_id == Order.internal_user_id)
        .join(User, User.id == Referral.inviter_id)
        .join(Invitee, Invitee.id == Referral.invitee_id)
        .where(
            and_(
                Order.status == "SUCCESS",
                Order.final_price > 0,
                Order.payment_channel.in_(VALID_PAYMENT_CHANNELS),
            )
        )
    )
    rows = (await session.execute(stmt)).all()

    count_stmt = select(Referral.inviter_id, func.count(Referral.id)).group_by(
        Referral.inviter_id
    )
    total_invitations_map = {
        row[0]: row[1] for row in (await session.execute(count_stmt)).all()
    }
    inviter_ids = {inviter.id for _order, inviter, _invitee in rows}
    spent_commission_map: dict[int, float] = {}
    if inviter_ids:
        spent_stmt = (
            select(
                AffiliateTransaction.user_id,
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    AffiliateTransaction.direction == "OUT",
                                    AffiliateTransaction.status == "SUCCESS",
                                ),
                                AffiliateTransaction.amount_usdt,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .where(AffiliateTransaction.user_id.in_(inviter_ids))
            .group_by(AffiliateTransaction.user_id)
        )
        spent_commission_map = {
            int(user_id): _round_money(Decimal(str(spent_usdt or 0)))
            for user_id, spent_usdt in (await session.execute(spent_stmt)).all()
        }

    rates = await get_exchange_rates()
    ton_to_usdt = rates.get("ton_to_usdt", 1.4)
    rmb_to_usdt = rates.get("rmb_to_usdt", 1.0 / 6.7)
    stars_to_usdt = rates.get("stars_to_usdt", 0.013)

    inviters_map = {}
    for order, inviter, invitee in rows:
        inviter_data = inviters_map.setdefault(
            inviter.id,
            {
                "inviter_id": inviter.id,
                "inviter_telegram_id": inviter.telegram_id,
                "inviter_name": inviter.full_name
                or inviter.username
                or str(inviter.telegram_id or inviter.id),
                "total_stars": 0,
                "total_ton": 0.0,
                "total_rmb": 0.0,
                "spent_commission_usdt": spent_commission_map.get(inviter.id, 0.0),
                "invitees": {},
            },
        )

        invitee_data = inviter_data["invitees"].setdefault(
            invitee.id,
            {
                "invitee_id": invitee.id,
                "invitee_telegram_id": invitee.telegram_id,
                "invitee_name": invitee.full_name
                or invitee.username
                or str(invitee.telegram_id or invitee.id),
                "recharge_count": 0,
                "commission_usdt": Decimal("0.0"),
                "orders": [],
            },
        )

        if order.payment_channel == "RMB":
            inviter_data["total_rmb"] += float(order.final_price)
            order_type = "RMB"
            order_amount = float(order.final_price)
        elif order.payment_channel == "XTR":
            inviter_data["total_stars"] += int(order.final_price)
            order_type = "Stars"
            order_amount = int(order.final_price)
        else:
            inviter_data["total_ton"] += float(order.final_price)
            order_type = "TON"
            order_amount = float(order.final_price)

        invitee_data["orders"].append(
            {
                "order_id": str(order.order_id or ""),
                "type": order_type,
                "amount": order_amount,
                "date": (order.paid_at or order.created_at).strftime("%Y-%m-%d %H:%M:%S")
                if (order.paid_at or order.created_at)
                else "",
                "created_at": order.paid_at or order.created_at,
            }
        )
        invitee_data["recharge_count"] += 1
        invitee_data["commission_usdt"] += Decimal(str(order.commission_usdt or 0))

    response_data = []
    for inv_data in inviters_map.values():
        invitees_list = list(inv_data["invitees"].values())
        total_commission_usdt = sum(
            (invitee["commission_usdt"] for invitee in invitees_list),
            Decimal("0.0"),
        )
        for invitee_data in invitees_list:
            invitee_data["commission_usdt"] = round(
                float(invitee_data["commission_usdt"]), 2
            )
            invitee_data["orders"].sort(
                key=lambda item: item["created_at"].timestamp()
                if item["created_at"]
                else 0
            )
            for order_item in invitee_data["orders"]:
                order_item.pop("created_at", None)

        invitees_list.sort(key=lambda item: item["recharge_count"], reverse=True)
        inv_data["invitees"] = invitees_list
        inv_data["total_invitees"] = len(invitees_list)
        inv_data["commission_usdt"] = round(float(total_commission_usdt), 2)
        inv_data["total_usdt"] = round(
            (inv_data["total_ton"] * ton_to_usdt)
            + (inv_data["total_rmb"] * rmb_to_usdt)
            + (inv_data["total_stars"] * stars_to_usdt),
            2,
        )
        inv_data["total_invitations"] = total_invitations_map.get(
            inv_data["inviter_id"], inv_data["total_invitees"]
        )
        inv_data["conversion_rate"] = (
            round(
                (inv_data["total_invitees"] / inv_data["total_invitations"]) * 100,
                2,
            )
            if inv_data["total_invitations"] > 0
            else 0.0
        )
        inv_data["total_ton"] = round(inv_data["total_ton"], 2)
        inv_data["total_rmb"] = round(inv_data["total_rmb"], 2)
        response_data.append(inv_data)

    response_data.sort(key=lambda item: item["total_invitees"], reverse=True)
    return response_data


async def query_affiliate_redeem_records(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    query: str | None = None,
    redeem_type: str | None = None,
) -> dict:
    stmt = select(AffiliateRedeem, User).join(User, User.id == AffiliateRedeem.user_id)

    if query:
        like_query = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                User.full_name.ilike(like_query),
                User.username.ilike(like_query),
                cast(User.telegram_id, String).ilike(like_query),
                cast(User.id, String).ilike(like_query),
            )
        )

    if redeem_type:
        stmt = stmt.where(AffiliateRedeem.redeem_type == redeem_type)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = (
        stmt.order_by(desc(AffiliateRedeem.created_at), desc(AffiliateRedeem.id))
        .offset(max(page - 1, 0) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).all()

    items = []
    for redeem, user in rows:
        user_name = user.full_name or user.username or str(user.telegram_id or user.id)
        items.append(
            {
                "redeem_id": redeem.id,
                "user_id": user.id,
                "user_telegram_id": user.telegram_id,
                "user_name": user_name,
                "username": user.username,
                "redeem_type": redeem.redeem_type,
                "redeem_option_key": redeem.redeem_option_key,
                "requested_amount_usdt": float(redeem.requested_amount_usdt or 0),
                "amount_usdt": float(redeem.amount_usdt or 0),
                "credits_granted": int(redeem.credits_granted or 0),
                "target_identity": redeem.target_identity,
                "duration_days": redeem.duration_days,
                "status": redeem.status,
                "created_at": redeem.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if redeem.created_at
                else "",
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
