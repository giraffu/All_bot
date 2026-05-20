import logging
import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants import TON_RECEIVER_ADDRESS
from src.database.models import Order, User
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
from src.web_api.dependencies import get_current_user, get_db

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/plans")
async def get_plans(db: AsyncSession = Depends(get_db)):
    """
    获取充值套餐列表
    """
    result = await db.execute(
        build_visible_membership_plans_stmt(is_rmb=True, is_subscription=None)
    )
    plans = result.scalars().all()

    return {
        "code": 0,
        "message": "success",
        "data": {
            "plans": [
                {
                    "id": plan.id,
                    "name": plan.name,
                    "description": f"获得 {plan.reward_credits} 灵石",
                    "price_rmb": float(plan.price_rmb),
                    "price_ton": float(plan.price_ton),
                    "duration_days": plan.duration_days,
                    "identity_override": plan.identity_name,
                    "credits_granted": plan.reward_credits,
                    "type": "monthly" if plan.duration_days > 0 else "one_time",
                }
                for plan in plans
            ],
            "ton_receiver_address": TON_RECEIVER_ADDRESS,
        },
    }


class CreateOrderRequest(BaseModel):
    plan_id: int
    pay_type: str = "alipay"  # wxpay, alipay, etc.


class CreateTonOrderRequest(BaseModel):
    plan_id: int


@router.post("/orders")
async def create_order(
    req: CreateOrderRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建 RMB 预建单并返回支付链接
    """
    # 查询套餐
    plan_res = await db.execute(
        build_visible_membership_plan_lookup_stmt(req.plan_id)
    )
    plan = plan_res.scalar_one_or_none()
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found or inactive")

    # 创建单号 (每次都生成新单号，避免切换支付方式时引发网关报错)
    out_trade_no = (
        f"WEB_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    )

    # 写库
    new_order = Order(
        order_id=out_trade_no,
        business_order_id=generate_business_order_id(),
        telegram_id=current_user.id,  # 核心避坑：必须赋值 internal_user_id
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

    # 调用易支付获取链接
    origin = request.headers.get("origin", "https://web.aivison.it.com")
    public_order_id = get_order_public_id(new_order)
    return_url = f"{origin}/billing?order_id={public_order_id}"

    pay_result = await RMBPaymentService.create_payment_url(
        out_trade_no=out_trade_no,
        plan_name=plan.name,
        amount=plan.price_rmb,
        pay_type=req.pay_type,
        return_url=return_url,
    )

    if pay_result and pay_result.get("code") == 1:
        pay_url = pay_result.get("payurl")
        return {
            "code": 0,
            "message": "success",
            "data": {
                "order_id": public_order_id,
                "business_order_id": new_order.business_order_id,
                "legacy_order_id": out_trade_no,
                "pay_url": pay_url,
            },
        }
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create payment url: {pay_result.get('msg')}",
        )


@router.post("/ton-orders")
async def create_ton_order(
    req: CreateTonOrderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan_res = await db.execute(
        build_visible_membership_plan_lookup_stmt(req.plan_id)
    )
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
        telegram_id=current_user.id,
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
    return {
        "code": 0,
        "message": "success",
        "data": {
            "order_id": get_order_public_id(new_order),
            "business_order_id": business_order_id,
            "legacy_order_id": legacy_order_id,
            "ton_comment": ton_comment,
            "ton_receiver_address": TON_RECEIVER_ADDRESS,
            "amount_ton": float(plan.price_ton),
            "amount_nanotons": str(
                int(Decimal(str(plan.price_ton)) * Decimal("1000000000"))
            ),
        },
    }


@router.get("/orders/{order_id}/status")
async def get_order_status(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    轮询订单状态
    """
    order_res = await db.execute(build_order_public_lookup_stmt(order_id))
    order = order_res.scalar_one_or_none()

    if not order or order.telegram_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")

    return {
        "code": 0,
        "message": "success",
        "data": {
            "status": order.status,
            "order_id": get_order_public_id(order),
            "business_order_id": order.business_order_id,
            "legacy_order_id": order.order_id,
        },
    }
