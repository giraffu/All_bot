from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import User
from src.web_api.dependencies import get_db, get_payment_user
from src.web_api.services.payment_api_service import (
    create_rmb_order_payload,
    create_ton_order_payload,
    create_usdt_ton_order_payload,
    get_payment_order_status_payload,
    get_payment_plans_payload,
)

router = APIRouter()


@router.get("/plans")
async def get_plans(db: AsyncSession = Depends(get_db)):
    """
    获取充值套餐列表
    """
    return await get_payment_plans_payload(db=db)


class CreateOrderRequest(BaseModel):
    plan_id: int
    pay_type: str = "alipay"  # wxpay, alipay, etc.


class CreateTonOrderRequest(BaseModel):
    plan_id: int


class CreateUsdtTonOrderRequest(BaseModel):
    plan_id: int


@router.post("/orders")
async def create_order(
    req: CreateOrderRequest,
    request: Request,
    current_user: User = Depends(get_payment_user),
    db: AsyncSession = Depends(get_db),
):
    """
    创建 RMB 预建单并返回支付链接
    """
    return await create_rmb_order_payload(
        db=db,
        current_user=current_user,
        plan_id=req.plan_id,
        pay_type=req.pay_type,
        request_origin=request.headers.get("origin"),
    )


@router.post("/ton-orders")
async def create_ton_order(
    req: CreateTonOrderRequest,
    current_user: User = Depends(get_payment_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_ton_order_payload(
        db=db,
        current_user=current_user,
        plan_id=req.plan_id,
    )


@router.post("/usdt-ton-orders")
async def create_usdt_ton_order(
    req: CreateUsdtTonOrderRequest,
    current_user: User = Depends(get_payment_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_usdt_ton_order_payload(
        db=db,
        current_user=current_user,
        plan_id=req.plan_id,
    )


@router.get("/orders/{order_id}/status")
async def get_order_status(
    order_id: str,
    current_user: User = Depends(get_payment_user),
    db: AsyncSession = Depends(get_db),
):
    """
    轮询订单状态
    """
    return await get_payment_order_status_payload(
        order_id=order_id,
        current_user=current_user,
        db=db,
    )
