import uuid
import urllib.parse
from datetime import datetime

from fastapi import HTTPException

from src.database.models import Order
from src.services.membership_plan_catalog import (
    build_visible_membership_plan_lookup_stmt,
    build_visible_membership_plans_stmt,
)
from src.services.order_v2_service import (
    build_legacy_order_payload,
    build_order_public_lookup_stmt,
    build_order_settlement_snapshot,
    build_order_v2_payload,
    generate_business_order_id,
    get_order_public_id,
    is_order_v2_enabled,
)
from src.services.rmb_payment_service import RMBPaymentService
from src.services.ton_payment_config import (
    TonPaymentAvailability,
    get_ton_payment_availability,
)
from src.services.usdt_ton_payment_config import (
    UsdtTonPaymentAvailability,
    get_usdt_ton_payment_availability,
)
from src.web_api.presenters.payment_presenter import (
    build_order_status_payload,
    build_payment_plans_payload,
    build_rmb_order_payload,
    build_ton_order_payload,
    build_usdt_ton_order_payload,
)


def _extract_normalized_pay_url(pay_result: dict | None) -> str | None:
    if not pay_result:
        return None

    raw_pay_url = pay_result.get("payurl")
    if not raw_pay_url and isinstance(pay_result.get("data"), dict):
        raw_pay_url = pay_result["data"].get("payurl")

    if not raw_pay_url:
        return None

    parsed = urllib.parse.urlparse(str(raw_pay_url))
    if not parsed.scheme or not parsed.netloc:
        return None

    query_dict = urllib.parse.parse_qs(parsed.query)
    encoded_query = urllib.parse.urlencode(query_dict, doseq=True)
    return urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            encoded_query,
            parsed.fragment,
        )
    )


async def get_payment_plans_payload(
    *,
    db,
    availability: TonPaymentAvailability | None = None,
    usdt_availability: UsdtTonPaymentAvailability | None = None,
) -> dict:
    availability = availability or get_ton_payment_availability()
    usdt_availability = usdt_availability or get_usdt_ton_payment_availability()
    result = await db.execute(
        build_visible_membership_plans_stmt(is_rmb=True, is_subscription=None)
    )
    plans = result.scalars().all()
    return build_payment_plans_payload(
        plans,
        ton_payment_enabled=availability.enabled,
        ton_receiver_address=availability.merchant_address,
        usdt_ton_payment_enabled=usdt_availability.enabled,
        usdt_ton_receiver_address=usdt_availability.merchant_address,
        usdt_ton_jetton_master_address=usdt_availability.jetton_master_address,
    )


async def create_rmb_order_payload(
    *,
    db,
    current_user,
    plan_id: int,
    pay_type: str,
    request_origin: str | None,
    create_payment_url_func=None,
) -> dict:
    plan_res = await db.execute(build_visible_membership_plan_lookup_stmt(plan_id))
    plan = plan_res.scalar_one_or_none()
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found or inactive")

    legacy_order_id = (
        f"WEB_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    )
    new_order = Order(
        order_id=legacy_order_id,
        business_order_id=generate_business_order_id(),
        internal_user_id=current_user.id,
        plan_id=plan.id,
        original_price=plan.price_rmb,
        final_price=plan.price_rmb,
        settlement_schema_version="order_plan_v1",
        settlement_snapshot=build_order_settlement_snapshot(plan),
        status="PENDING",
        payment_channel="RMB",
        created_at=datetime.now(),
    )
    db.add(new_order)
    await db.commit()

    if create_payment_url_func is None:
        create_payment_url_func = RMBPaymentService.create_payment_url

    origin = request_origin or "https://web.aivison.it.com"
    return_url = f"{origin}/billing?order_id={get_order_public_id(new_order)}"
    pay_result = await create_payment_url_func(
        out_trade_no=legacy_order_id,
        plan_name=plan.name,
        amount=plan.price_rmb,
        pay_type=pay_type,
        return_url=return_url,
    )

    pay_url = _extract_normalized_pay_url(pay_result)
    if pay_result and pay_result.get("code") == 1 and pay_url:
        return build_rmb_order_payload(new_order, pay_url)

    raise HTTPException(
        status_code=500,
        detail=f"Failed to create payment url: {pay_result.get('msg')}",
    )


async def create_ton_order_payload(
    *,
    db,
    current_user,
    plan_id: int,
) -> dict:
    availability = get_ton_payment_availability()
    if not availability.enabled or not availability.merchant_address:
        raise HTTPException(
            status_code=503,
            detail={
                "reason": "TON_PAYMENT_UNAVAILABLE",
                "message": "TON payment is unavailable",
            },
        )

    plan_res = await db.execute(build_visible_membership_plan_lookup_stmt(plan_id))
    plan = plan_res.scalar_one_or_none()
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found or inactive")
    if not getattr(plan, "price_ton", None):
        raise HTTPException(status_code=400, detail="Plan does not support TON payment")

    business_order_id = generate_business_order_id()
    legacy_order_id = (
        f"ORDER:{current_user.telegram_id or current_user.id}:{plan.id}:{int(datetime.now().timestamp())}"
    )[:64]
    new_order = Order(
        order_id=legacy_order_id,
        business_order_id=business_order_id,
        internal_user_id=current_user.id,
        plan_id=plan.id,
        original_price=plan.price_ton,
        final_price=plan.price_ton,
        settlement_schema_version="order_plan_v1",
        settlement_snapshot=build_order_settlement_snapshot(plan),
        status="PENDING",
        payment_channel="TON",
        created_at=datetime.now(),
    )
    db.add(new_order)
    await db.commit()

    ton_comment = (
        build_order_v2_payload(business_order_id)
        if is_order_v2_enabled()
        else build_legacy_order_payload(
            telegram_user_id=current_user.telegram_id or current_user.id,
            plan_id=plan.id,
            timestamp=int(datetime.now().timestamp()),
        )
    )
    return build_ton_order_payload(
        order=new_order,
        ton_comment=ton_comment,
        amount_ton=plan.price_ton,
        ton_receiver_address=availability.merchant_address,
    )


async def create_usdt_ton_order_payload(
    *,
    db,
    current_user,
    plan_id: int,
) -> dict:
    availability = get_usdt_ton_payment_availability()
    if not availability.enabled or not availability.merchant_address:
        raise HTTPException(
            status_code=503,
            detail={
                "reason": "USDT_TON_PAYMENT_UNAVAILABLE",
                "message": "USDT-TON payment is unavailable",
            },
        )

    plan_res = await db.execute(build_visible_membership_plan_lookup_stmt(plan_id))
    plan = plan_res.scalar_one_or_none()
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found or inactive")
    if not getattr(plan, "price_usdt", None):
        raise HTTPException(
            status_code=400,
            detail="Plan does not support USDT-TON payment",
        )

    business_order_id = generate_business_order_id()
    legacy_order_id = (
        f"USDT:{current_user.telegram_id or current_user.id}:{plan.id}:"
        f"{int(datetime.now().timestamp())}"
    )[:64]
    new_order = Order(
        order_id=legacy_order_id,
        business_order_id=business_order_id,
        internal_user_id=current_user.id,
        plan_id=plan.id,
        original_price=plan.price_usdt,
        final_price=plan.price_usdt,
        settlement_schema_version="order_plan_v1",
        settlement_snapshot=build_order_settlement_snapshot(plan),
        status="PENDING",
        payment_channel="USDT_TON",
        created_at=datetime.now(),
    )
    db.add(new_order)
    await db.commit()

    usdt_comment = (
        build_order_v2_payload(business_order_id)
        if is_order_v2_enabled()
        else build_legacy_order_payload(
            telegram_user_id=current_user.telegram_id or current_user.id,
            plan_id=plan.id,
            timestamp=int(datetime.now().timestamp()),
        )
    )
    return build_usdt_ton_order_payload(
        order=new_order,
        usdt_comment=usdt_comment,
        amount_usdt=plan.price_usdt,
        usdt_receiver_address=availability.merchant_address,
        usdt_jetton_master_address=availability.jetton_master_address,
    )


async def get_payment_order_status_payload(
    *,
    order_id: str,
    current_user,
    db,
) -> dict:
    order_res = await db.execute(build_order_public_lookup_stmt(order_id))
    order = order_res.scalar_one_or_none()
    if not order or order.internal_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    return build_order_status_payload(order, account=current_user)
