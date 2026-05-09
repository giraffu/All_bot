import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants import TON_RECEIVER_ADDRESS
from src.database.core import AsyncSessionLocal
from src.database.models import MembershipPlan, Order, User
from src.services.rmb_payment_service import RMBPaymentService
from src.web_api.dependencies import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/plans")
async def get_plans(db: AsyncSession = Depends(get_db)):
    """
    获取充值套餐列表
    """
    result = await db.execute(
        select(MembershipPlan)
        .where(MembershipPlan.is_active == True)
        .order_by(MembershipPlan.sort_order.asc())
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
                    "description": plan.description,
                    "price_rmb": float(plan.price_rmb),
                    "price_ton": float(plan.price_ton),
                    "duration_days": plan.duration_days,
                    "identity_override": plan.identity_override,
                    "credits_granted": plan.credits_granted,
                    "type": plan.type
                }
                for plan in plans
            ],
            "ton_receiver_address": TON_RECEIVER_ADDRESS
        }
    }

class CreateOrderRequest(BaseModel):
    plan_id: int
    pay_type: str = "alipay"  # wxpay, alipay, etc.

@router.post("/orders")
async def create_order(
    req: CreateOrderRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    创建 RMB 预建单并返回支付链接
    """
    # 查询套餐
    plan_res = await db.execute(select(MembershipPlan).where(MembershipPlan.id == req.plan_id))
    plan = plan_res.scalar_one_or_none()
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found or inactive")

    # 创建单号 (每次都生成新单号，避免切换支付方式时引发网关报错)
    out_trade_no = f"WEB_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    # 写库
    new_order = Order(
        order_id=out_trade_no,
        telegram_id=current_user.id, # 核心避坑：必须赋值 internal_user_id
        plan_id=plan.id,
        original_price=plan.price_rmb,
        final_price=plan.price_rmb,
        status="PENDING",
        created_at=datetime.now()
    )
    db.add(new_order)
    await db.commit()
    
    # 调用易支付获取链接
    origin = request.headers.get("origin", "https://web.aivison.it.com")
    return_url = f"{origin}/dashboard/billing?order_id={out_trade_no}"
    
    pay_result = await RMBPaymentService.create_payment_url(
        out_trade_no=out_trade_no,
        plan_name=plan.name,
        amount=float(plan.price_rmb),
        pay_type=req.pay_type,
        return_url=return_url
    )
    
    if pay_result and pay_result.get("code") == 1:
        pay_url = pay_result.get("payurl")
        return {
            "code": 0, 
            "message": "success", 
            "data": {
                "order_id": out_trade_no, 
                "pay_url": pay_url
            }
        }
    else:
        raise HTTPException(status_code=500, detail=f"Failed to create payment url: {pay_result.get('msg')}")

@router.get("/orders/{order_id}/status")
async def get_order_status(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    轮询订单状态
    """
    order_res = await db.execute(
        select(Order).where(Order.order_id == order_id, Order.telegram_id == current_user.id)
    )
    order = order_res.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    return {
        "code": 0,
        "message": "success",
        "data": {
            "status": order.status
        }
    }
