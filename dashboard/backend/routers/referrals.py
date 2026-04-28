import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from datetime import datetime

from dashboard.backend.routers.stats import get_exchange_rates
from src.database.core import get_db
from src.database.models import Order, Referral, User

router = APIRouter(prefix="/api/referrals", tags=["referrals"])
logger = logging.getLogger("dashboard.referrals")

@router.get("/rewards")
async def get_referral_rewards(db: AsyncSession = Depends(get_db)):
    try:
        Invitee = aliased(User)
        stmt = (
            select(
                Order,
                User, # Inviter
                Invitee # Invitee
            )
            .join(Referral, Referral.invitee_id == Order.telegram_id)
            .join(User, User.telegram_id == Referral.inviter_id)
            .join(Invitee, Invitee.telegram_id == Referral.invitee_id)
            .where(Order.status == "SUCCESS")
        )
        
        result = await db.execute(stmt)
        rows = result.all()
        
        # Get total invitation count per user
        from sqlalchemy import func
        count_stmt = (
            select(
                Referral.inviter_id,
                func.count(Referral.id)
            )
            .group_by(Referral.inviter_id)
        )
        count_result = await db.execute(count_stmt)
        total_invitations_map = {row[0]: row[1] for row in count_result.all()}
        
        rates = await get_exchange_rates()
        ton_to_usdt = rates.get("ton_to_usdt", 5.0)
        rmb_to_usdt = rates.get("rmb_to_usdt", 0.14)
        stars_to_usdt = rates.get("stars_to_usdt", 0.013)
        
        inviters_map = {}
        for order, inviter, invitee in rows:
            if inviter.telegram_id not in inviters_map:
                inviters_map[inviter.telegram_id] = {
                    "inviter_id": inviter.id,
                    "inviter_telegram_id": inviter.telegram_id,
                    "inviter_name": inviter.full_name or inviter.username or str(inviter.telegram_id),
                    "total_stars": 0,
                    "total_ton": 0.0,
                    "total_rmb": 0.0,
                    "invitees": {}
                }
            
            invitees_map = inviters_map[inviter.telegram_id]["invitees"]
            if invitee.telegram_id not in invitees_map:
                invitees_map[invitee.telegram_id] = {
                    "invitee_id": invitee.id,
                    "invitee_telegram_id": invitee.telegram_id,
                    "invitee_name": invitee.full_name or invitee.username or str(invitee.telegram_id),
                    "recharge_count": 0,
                    "orders": []
                }
            
            order_id_str = str(order.order_id) if order.order_id else ""
            price = float(order.final_price)
            
            order_type = "TON"
            if order_id_str.startswith("RMB_"):
                order_type = "RMB"
                inviters_map[inviter.telegram_id]["total_rmb"] += price
            elif order_id_str.startswith("XTR_"):
                order_type = "Stars"
                price = int(price)
                inviters_map[inviter.telegram_id]["total_stars"] += price
            else:
                if price >= 100:
                    order_type = "Stars"
                    price = int(price)
                    inviters_map[inviter.telegram_id]["total_stars"] += price
                else:
                    inviters_map[inviter.telegram_id]["total_ton"] += price
            
            invitees_map[invitee.telegram_id]["orders"].append({
                "order_id": order_id_str,
                "type": order_type,
                "amount": price,
                "date": order.created_at.strftime("%Y-%m-%d %H:%M:%S") if order.created_at else "",
                "created_at": order.created_at
            })
            invitees_map[invitee.telegram_id]["recharge_count"] += 1
            
        response_data = []
        for inv_tg_id, inv_data in inviters_map.items():
            invitees_list = list(inv_data["invitees"].values())
            
            total_commission_usdt = 0.0
            
            for invitee_data in invitees_list:
                # Sort orders by created_at to find the first order
                sorted_orders = sorted(invitee_data["orders"], key=lambda x: x["created_at"].timestamp() if x["created_at"] else 0)
                if sorted_orders:
                    first_order = sorted_orders[0]
                    order_type = first_order["type"]
                    amount = first_order["amount"]
                    
                    # Convert to USDT
                    order_usdt = 0.0
                    if order_type == "TON":
                        order_usdt = amount * ton_to_usdt
                    elif order_type == "RMB":
                        order_usdt = amount * rmb_to_usdt
                    elif order_type == "Stars":
                        order_usdt = amount * stars_to_usdt
                        
                    # 10% commission
                    invitee_commission = order_usdt * 0.1
                    invitee_data["commission_usdt"] = round(invitee_commission, 2)
                    total_commission_usdt += invitee_commission
                else:
                    invitee_data["commission_usdt"] = 0.0
                
                # Remove 'created_at' from orders to avoid serialization issues
                for o in invitee_data["orders"]:
                    o.pop("created_at", None)

            # Sort invitees by recharge_count descending
            invitees_list.sort(key=lambda x: x["recharge_count"], reverse=True)
            inv_data["invitees"] = invitees_list
            inv_data["total_invitees"] = len(invitees_list)
            
            total_usdt = (inv_data["total_ton"] * ton_to_usdt) + (inv_data["total_rmb"] * rmb_to_usdt) + (inv_data["total_stars"] * stars_to_usdt)
            inv_data["total_usdt"] = round(total_usdt, 2)
            inv_data["commission_usdt"] = round(total_commission_usdt, 2)
            
            inv_data["total_invitations"] = total_invitations_map.get(inv_data["inviter_telegram_id"], inv_data["total_invitees"])
            
            # Calculate conversion rate
            if inv_data["total_invitations"] > 0:
                inv_data["conversion_rate"] = round((inv_data["total_invitees"] / inv_data["total_invitations"]) * 100, 2)
            else:
                inv_data["conversion_rate"] = 0.0
            
            inv_data["total_ton"] = round(inv_data["total_ton"], 2)
            inv_data["total_rmb"] = round(inv_data["total_rmb"], 2)
            response_data.append(inv_data)
            
        # Sort by total_invitees descending
        response_data.sort(key=lambda x: x["total_invitees"], reverse=True)
            
        return response_data
        
    except Exception as e:
        logger.error(f"Error getting referral rewards: {e}")
        raise HTTPException(status_code=500, detail=str(e))
