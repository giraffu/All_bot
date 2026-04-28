import logging
import os
import time
from datetime import date, datetime, timedelta

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Float, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from src.database.core import get_db

load_dotenv()
from src.database.models import (
    CheckinHistory,
    History,
    Referral,
    TemplateContribution,
    User,
    UserLog,
)

router = APIRouter(prefix="/api/stats", tags=["stats"])
logger = logging.getLogger("dashboard.stats")

_exchange_rates_cache = {
    "rates": {
        "ton_to_usdt": 5.0,
        "rmb_to_usdt": 0.14,
        "stars_to_usdt": 0.013
    },
    "last_fetched": 0
}

async def get_exchange_rates():
    now = time.time()
    if now - _exchange_rates_cache["last_fetched"] < 3600:  # cache for 1 hour
        return _exchange_rates_cache["rates"]
        
    rates = _exchange_rates_cache["rates"].copy()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp1 = await client.get("https://tonapi.io/v2/rates?tokens=ton&currencies=usd")
            if resp1.status_code == 200:
                data = resp1.json()
                rates["ton_to_usdt"] = float(data["rates"]["TON"]["prices"]["USD"])
                
            resp2 = await client.get("https://api.exchangerate-api.com/v4/latest/USD")
            if resp2.status_code == 200:
                cny_rate = float(resp2.json()["rates"]["CNY"])
                rates["rmb_to_usdt"] = 1.0 / cny_rate
                
        _exchange_rates_cache["rates"] = rates
        _exchange_rates_cache["last_fetched"] = now
    except Exception as e:
        logger.error(f"Error fetching exchange rates: {e}")
        
    return rates

def get_hour_expr(col, dialect_name):
    if dialect_name == 'postgresql':
        return func.extract('hour', col)
    return func.strftime('%H', col)

def get_days_diff_expr(col, dialect_name):
    if dialect_name == 'postgresql':
        return func.extract('day', func.now() - col)
    return func.julianday('now') - func.julianday(col)

@router.get("")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics"""
    try:
        video_types = [
            'video', 'video_undress', 'custom_video', 'perfect_video_insert', 
            'video_pro', 'doggy_style', 'blowjob', 'undress_tongue', 
            'closeup_blowjob', 'face_show', 'face_tongue', 'fuck', 
            'penetration', 'penetration_step1', 'penetration_step2', 'masturbation',
            'face_video_step1', 'face_video_step2'
        ]
        cost_case = case(
            (History.type.in_(video_types), 6),
            else_=2
        )

        result = await db.execute(select(func.count(User.id)).where(User.is_channel_member == True))
        total_users = result.scalar()

        result_all = await db.execute(select(func.count(User.id)))
        total_db_users = result_all.scalar() or 0

        identity_stmt = select(User.current_identity, func.count(User.id)).group_by(User.current_identity)
        identity_result = await db.execute(identity_stmt)
        identity_counts = {}
        for row in identity_result:
            if row.current_identity:
                identity_counts[row.current_identity] = row.count
                
        inner_disciple_count = identity_counts.get("内门弟子", 0)
        core_disciple_count = identity_counts.get("核心弟子", 0)
        true_disciple_count = identity_counts.get("真传弟子", 0)

        # Calculate User Group (Cultivation Level) distribution
        user_group_stmt = select(User.user_group, func.count(User.id)).group_by(User.user_group)
        user_group_result = await db.execute(user_group_stmt)
        user_group_distribution = {}
        for row in user_group_result:
            if row.user_group:
                user_group_distribution[row.user_group] = row.count
        
        # We ensure the requested keys exist
        for k in ["凡人", "练气期", "筑基期", "金丹期", "元婴期"]:
            if k not in user_group_distribution:
                user_group_distribution[k] = 0

        result = await db.execute(select(func.count(History.id)))
        total_generations = result.scalar()

        result = await db.execute(select(func.sum(User.credits)))
        total_credits = result.scalar() or 0

        result = await db.execute(select(func.sum(User.credits)).where(User.generation_count > 0))
        total_active_credits = result.scalar() or 0

        result = await db.execute(select(func.count(Referral.id)))
        total_referrals = result.scalar() or 0

        result = await db.execute(select(func.sum(cost_case)))
        total_consumed_credits = result.scalar() or 0
        
        result = await db.execute(select(func.count(TemplateContribution.id)))
        total_template_contributions = result.scalar() or 0
        
        result = await db.execute(select(func.count(TemplateContribution.id)).where(TemplateContribution.is_reviewed == True))
        total_approved_contributions = result.scalar() or 0
        
        # Calculate invitation recharge stats
        from src.database.models import Order
        stmt = (
            select(
                Order.telegram_id,
                Order.final_price,
                Order.order_id
            )
            .join(Referral, Referral.invitee_id == Order.telegram_id)
            .where(
                Order.status == "SUCCESS"
            )
        )
        result = await db.execute(stmt)
        rows = result.all()
        
        total_invitation_ton = 0.0
        total_invitation_rmb = 0.0
        total_invitation_stars = 0
        
        for tg_id, price, order_id in rows:
            if order_id and str(order_id).startswith("RMB_"):
                total_invitation_rmb += float(price)
            elif order_id and str(order_id).startswith("XTR_"):
                total_invitation_stars += int(price)
            else:
                if price >= 100:
                    total_invitation_stars += int(price)
                else:
                    total_invitation_ton += float(price)
                    
        today = date.today()
        
        result = await db.execute(select(func.count(User.id)).where(func.date(User.created_at) == today, User.is_channel_member == True))
        today_users = result.scalar() or 0

        result = await db.execute(select(func.count(User.id)).where(func.date(User.created_at) == today))
        today_users_all = result.scalar() or 0
        
        result = await db.execute(select(func.count(History.id)).where(func.date(History.created_at) == today))
        today_generations = result.scalar() or 0

        result = await db.execute(select(func.count(func.distinct(History.user_id))).where(func.date(History.created_at) == today))
        today_active_users = result.scalar() or 0

        # Web user statistics
        result = await db.execute(select(func.count(func.distinct(History.user_id))).where(History.source == 'web'))
        total_web_users = result.scalar() or 0

        result = await db.execute(select(func.count(func.distinct(History.user_id))).where(func.date(History.created_at) == today, History.source == 'web'))
        today_web_users = result.scalar() or 0

        result = await db.execute(select(func.sum(cost_case)).where(func.date(History.created_at) == today))
        today_consumed_credits = result.scalar() or 0

        result = await db.execute(select(func.count(User.id)).where(User.last_checkin == today))
        today_checkins = result.scalar() or 0

        today_dist_stmt = select(History.type, func.count(History.id)).where(func.date(History.created_at) == today).group_by(History.type)
        today_dist_result = await db.execute(today_dist_stmt)
        today_type_distribution = {row.type or "unknown": row.count for row in today_dist_result}
        
        total_dist_stmt = select(History.type, func.count(History.id)).group_by(History.type)
        total_dist_result = await db.execute(total_dist_stmt)
        total_type_distribution = {row.type or "unknown": row.count for row in total_dist_result}
        
        dialect = db.bind.dialect.name
        hour_expr = get_hour_expr(History.created_at, dialect)
        
        hourly_stmt = select(hour_expr.label("hour"), func.count(History.id).label("count")).where(func.date(History.created_at) == today).group_by(hour_expr).order_by(hour_expr)
        hourly_result = await db.execute(hourly_stmt)
        
        today_hourly_distribution = {str(h).zfill(2): 0 for h in range(24)}
        for row in hourly_result:
            hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
            today_hourly_distribution[hour_str] = row.count

        user_gen_count = func.coalesce(User.generation_count, 0)
        gen_case = case(
            (user_gen_count == 0, '0'),
            (user_gen_count == 1, '1'),
            (user_gen_count == 2, '2'),
            (user_gen_count == 3, '3'),
            (user_gen_count == 4, '4'),
            (user_gen_count == 5, '5'),
            ((user_gen_count >= 6) & (user_gen_count <= 10), '6-10'),
            ((user_gen_count >= 11) & (user_gen_count <= 20), '11-20'),
            ((user_gen_count >= 21) & (user_gen_count <= 50), '21-50'),
            ((user_gen_count >= 51) & (user_gen_count <= 100), '51-100'),
            ((user_gen_count >= 101) & (user_gen_count <= 200), '101-200'),
            ((user_gen_count >= 201) & (user_gen_count <= 500), '201-500'),
            ((user_gen_count >= 501) & (user_gen_count <= 1000), '501-1000'),
            (user_gen_count > 1000, '1000+'),
            else_='0'
        )
        gen_dist_stmt = select(gen_case.label('range'), func.count(User.id).label('count')).group_by(gen_case)
        gen_dist_result = await db.execute(gen_dist_stmt)
        gen_distribution_order = ['0', '1', '2', '3', '4', '5', '6-10', '11-20', '21-50', '51-100', '101-200', '201-500', '501-1000', '1000+']
        gen_distribution = {k: 0 for k in gen_distribution_order}
        for row in gen_dist_result:
            if row.range in gen_distribution:
                gen_distribution[row.range] = row.count

        days_diff = get_days_diff_expr(User.created_at, dialect)
        days_valid = case((days_diff < 1, 1), else_=days_diff)
        avg_daily = func.cast(func.coalesce(User.generation_count, 0), Float) / days_valid
        
        avg_case = case(
            (avg_daily <= 0, '0'),
            ((avg_daily > 0) & (avg_daily <= 1), '0-1'),
            ((avg_daily > 1) & (avg_daily <= 3), '1-3'),
            ((avg_daily > 3) & (avg_daily <= 5), '3-5'),
            ((avg_daily > 5) & (avg_daily <= 10), '5-10'),
            ((avg_daily > 10) & (avg_daily <= 20), '10-20'),
            (avg_daily > 20, '20+'),
            else_='0'
        )
        avg_dist_stmt = select(avg_case.label('range'), func.count(User.id).label('count')).group_by(avg_case)
        avg_dist_result = await db.execute(avg_dist_stmt)
        avg_distribution_order = ['0', '0-1', '1-3', '3-5', '5-10', '10-20', '20+']
        avg_distribution = {k: 0 for k in avg_distribution_order}
        for row in avg_dist_result:
            if row.range in avg_distribution:
                avg_distribution[row.range] = row.count

        consumption_stmt = select(History.user_id, func.sum(cost_case).label('consumed')).group_by(History.user_id)
        consumed_sub = consumption_stmt.subquery()
        consumed_col = consumed_sub.c.consumed
        
        credit_dist_case = case(
            ((consumed_col >= 1) & (consumed_col <= 10), '1-10'),
            ((consumed_col >= 11) & (consumed_col <= 50), '11-50'),
            ((consumed_col >= 51) & (consumed_col <= 100), '51-100'),
            ((consumed_col >= 101) & (consumed_col <= 500), '101-500'),
            ((consumed_col >= 501) & (consumed_col <= 1000), '501-1000'),
            ((consumed_col >= 1001) & (consumed_col <= 5000), '1001-5000'),
            (consumed_col > 5000, '5000+'),
            else_='0'
        )
        credit_dist_stmt = select(credit_dist_case.label('range'), func.count().label('count')).group_by(credit_dist_case)
        credit_dist_result = await db.execute(credit_dist_stmt)
        credit_distribution_order = ['0', '1-10', '11-50', '51-100', '101-500', '501-1000', '1001-5000', '5000+']
        credit_distribution = {k: 0 for k in credit_distribution_order}
        users_with_consumption = 0
        for row in credit_dist_result:
            if row.range in credit_distribution:
                credit_distribution[row.range] = row.count
                users_with_consumption += row.count
        credit_distribution['0'] = max(0, total_db_users - users_with_consumption)

        days_diff_sub = get_days_diff_expr(User.created_at, dialect)
        days_valid_sub = case((days_diff_sub < 1, 1), else_=days_diff_sub)
        avg_daily_credit = func.cast(consumed_col, Float) / days_valid_sub
        avg_credit_case = case(
            (avg_daily_credit <= 0, '0'),
            ((avg_daily_credit > 0) & (avg_daily_credit <= 1), '0-1'),
            ((avg_daily_credit > 1) & (avg_daily_credit <= 5), '1-5'),
            ((avg_daily_credit > 5) & (avg_daily_credit <= 10), '5-10'),
            ((avg_daily_credit > 10) & (avg_daily_credit <= 20), '10-20'),
            ((avg_daily_credit > 20) & (avg_daily_credit <= 50), '20-50'),
            (avg_daily_credit > 50, '50+'),
            else_='0'
        )
        avg_credit_dist_stmt = select(avg_credit_case.label('range'), func.count().label('count')).select_from(User).join(consumed_sub, User.id == consumed_sub.c.user_id).group_by(avg_credit_case)
        avg_credit_dist_result = await db.execute(avg_credit_dist_stmt)
        avg_credit_distribution_order = ['0', '0-1', '1-5', '5-10', '10-20', '20-50', '50+']
        avg_credit_distribution = {k: 0 for k in avg_credit_distribution_order}
        users_with_avg_credit = 0
        for row in avg_credit_dist_result:
            if row.range in avg_credit_distribution:
                avg_credit_distribution[row.range] = row.count
                users_with_avg_credit += row.count
        avg_credit_distribution['0'] = max(0, total_db_users - users_with_avg_credit)

        user_credits = func.coalesce(User.credits, 0)
        holding_case = case(
            (user_credits <= 0, '0'),
            ((user_credits >= 1) & (user_credits <= 10), '1-10'),
            ((user_credits >= 11) & (user_credits <= 50), '11-50'),
            ((user_credits >= 51) & (user_credits <= 100), '51-100'),
            ((user_credits >= 101) & (user_credits <= 500), '101-500'),
            ((user_credits >= 501) & (user_credits <= 1000), '501-1000'),
            ((user_credits >= 1001) & (user_credits <= 5000), '1001-5000'),
            (user_credits > 5000, '5000+'),
            else_='0'
        )
        holding_dist_stmt = select(holding_case.label('range'), func.count(User.id).label('count')).group_by(holding_case)
        holding_dist_result = await db.execute(holding_dist_stmt)
        holding_distribution_order = ['0', '1-10', '11-50', '51-100', '101-500', '501-1000', '1001-5000', '5000+']
        holding_distribution = {k: 0 for k in holding_distribution_order}
        for row in holding_dist_result:
            if row.range in holding_distribution:
                holding_distribution[row.range] = row.count

        # 外部余额查询: TON & USDT & Stars & RMB
        ton_balance = 0.0
        usdt_balance = 0.0
        star_balance = 0
        rmb_balance = 0.0
        
        try:
            ton_address = os.getenv("VITE_MERCHANT_ADDRESS")
            if ton_address:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"https://toncenter.com/api/v2/getAddressBalance?address={ton_address}")
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("ok"):
                            ton_balance = round(float(data.get("result", 0)) / 1e9, 2)
                            
                    # Fetch USDT balance
                    resp_jettons = await client.get(f"https://tonapi.io/v2/accounts/{ton_address}/jettons")
                    if resp_jettons.status_code == 200:
                        data = resp_jettons.json()
                        balances = data.get("balances", [])
                        for b in balances:
                            jetton = b.get("jetton", {})
                            symbol = jetton.get("symbol", "")
                            if symbol in ["USDT", "USD₮"]:
                                decimals = jetton.get("decimals", 6)
                                balance_str = b.get("balance", "0")
                                usdt_balance = round(float(balance_str) / (10 ** decimals), 2)
                                break
        except Exception as e:
            logger.error(f"Error fetching TON/USDT balance: {e}")
            
        try:
            bot_token = os.getenv("BOT_TOKEN")
            # 默认给一个宿主机的代理以便能够访问 Telegram API
            proxy_url = os.getenv("PROXY_URL", "http://127.0.0.1:7890")
            if bot_token:
                # Add proxy configuration if it exists to allow container to access Telegram API
                if proxy_url:
                    from telegram.request import HTTPXRequest
                    request = HTTPXRequest(proxy=proxy_url)
                    bot = Bot(token=bot_token, request=request)
                else:
                    bot = Bot(token=bot_token)
                    
                offset = 0
                limit = 100
                total_stars = 0
                
                # Use a larger timeout context for the bot requests
                response = await bot.get_star_transactions(limit=limit, offset=offset, read_timeout=30, connect_timeout=30)
                transactions = response.transactions
                if transactions:
                    for tx in transactions:
                        if tx.amount > 0:
                            total_stars += tx.amount
                            
                    # Only fetch next pages if there were transactions
                    offset += len(transactions)
                    while len(transactions) == limit:
                        response = await bot.get_star_transactions(limit=limit, offset=offset, read_timeout=30, connect_timeout=30)
                        transactions = response.transactions
                        if not transactions:
                            break
                        for tx in transactions:
                            if tx.amount > 0:
                                total_stars += tx.amount
                        offset += len(transactions)
                        
                star_balance = total_stars
        except Exception as e:
            logger.error(f"Error fetching Stars balance: {e}")

        # Calculate total RMB balance from logs
        try:
            # Get plan RMB prices
            plans_res = await db.execute(text('SELECT name, price_rmb FROM membership_plans'))
            plan_name_to_rmb = {row.name: float(row.price_rmb) for row in plans_res}
            
            # Fetch all recharge logs
            logs_res = await db.execute(select(UserLog.extra_info).where(UserLog.operation_type == "recharge"))
            import json
            for row in logs_res:
                info = row.extra_info or ""
                if "rmb_payment" in info:
                    try:
                        data = json.loads(info)
                        plan_name = data.get("plan")
                        if plan_name:
                            rmb_balance += plan_name_to_rmb.get(plan_name, 0.0)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Error calculating RMB balance: {e}")

        return {
            "total_users": total_users,
            "inner_disciple_count": inner_disciple_count,
            "core_disciple_count": core_disciple_count,
            "true_disciple_count": true_disciple_count,
            "total_generations": total_generations,
            "total_credits": total_credits,
            "total_active_credits": total_active_credits,
            "total_referrals": total_referrals,
            "total_consumed_credits": total_consumed_credits,
            "total_template_contributions": total_template_contributions,
            "total_approved_contributions": total_approved_contributions,
            "today_users": today_users,
            "today_users_all": today_users_all,
            "today_generations": today_generations,
            "today_active_users": today_active_users,
            "total_web_users": total_web_users,
            "today_web_users": today_web_users,
            "today_checkins": today_checkins,
            "today_consumed_credits": today_consumed_credits,
            "today_type_distribution": today_type_distribution,
            "total_type_distribution": total_type_distribution,
            "today_hourly_distribution": today_hourly_distribution,
            "generation_distribution": gen_distribution,
            "avg_daily_distribution": avg_distribution,
            "credit_distribution": credit_distribution,
            "avg_daily_credit_distribution": avg_credit_distribution,
            "credit_holding_distribution": holding_distribution,
            "user_group_distribution": user_group_distribution,
            "ton_balance": ton_balance,
            "usdt_balance": usdt_balance,
            "star_balance": star_balance,
            "rmb_balance": round(rmb_balance, 2),
            "total_invitation_ton": round(total_invitation_ton, 2),
            "total_invitation_rmb": round(total_invitation_rmb, 2),
            "total_invitation_stars": total_invitation_stars
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/finance_hourly")
async def get_finance_hourly_stats(date_str: str = None, db: AsyncSession = Depends(get_db)):
    """Get hourly finance stats (recharged credits and new disciples) for a specific date"""
    try:
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = date.today()
            
        dialect = db.bind.dialect.name
        hour_expr = get_hour_expr(UserLog.created_at, dialect)
        
        # 1. Map plan names/ids to prices and identities
        plans_result = await db.execute(text('SELECT id, name, identity_name, reward_credits FROM membership_plans'))
        plan_id_to_identity = {}
        plan_name_to_identity = {}
        plan_id_to_credits = {}
        plan_name_to_credits = {}
        for row in plans_result:
            plan_id_to_identity[str(row.id)] = row.identity_name
            plan_name_to_identity[row.name] = row.identity_name
            plan_id_to_credits[str(row.id)] = int(row.reward_credits)
            plan_name_to_credits[row.name] = int(row.reward_credits)
            
        # 2. Fetch logs for the target date
        logs_stmt = select(hour_expr.label("hour"), UserLog.extra_info).where(
            UserLog.operation_type == "recharge",
            func.date(UserLog.created_at) == target_date
        )
        logs_result = await db.execute(logs_stmt)
        
        hourly_data = {
            str(h).zfill(2): {
                "recharged_credits": 0,
                "inner_disciples": 0,
                "core_disciples": 0,
                "true_disciples": 0
            } for h in range(24)
        }
        
        import json
        for row in logs_result:
            hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
            info = row.extra_info or ""
            
            try:
                data = json.loads(info)
                if data.get("is_gift"):
                    continue
                    
                plan_name = data.get("plan")
                plan_id = str(data.get("plan_id", ""))
                
                # Track Recharge Credits
                credits_added = 0
                if plan_name:
                    credits_added = plan_name_to_credits.get(plan_name, 0)
                elif plan_id:
                    credits_added = plan_id_to_credits.get(plan_id, 0)
                elif "ORDER:" in info:
                    order_id = data.get("order_id", "")
                    parts = order_id.split(":")
                    if len(parts) >= 3:
                        credits_added = plan_id_to_credits.get(parts[2], 0)
                        
                hourly_data[hour_str]["recharged_credits"] += credits_added
                
                # Track Disciples
                identity_name = data.get("identity")
                if not identity_name:
                    if plan_name:
                        identity_name = plan_name_to_identity.get(plan_name)
                    elif plan_id:
                        identity_name = plan_id_to_identity.get(plan_id)
                    elif "ORDER:" in info:
                        order_id = data.get("order_id", "")
                        parts = order_id.split(":")
                        if len(parts) >= 3:
                            identity_name = plan_id_to_identity.get(parts[2])
                            
                if identity_name:
                    if "内门" in identity_name:
                        hourly_data[hour_str]["inner_disciples"] += 1
                    elif "核心" in identity_name:
                        hourly_data[hour_str]["core_disciples"] += 1
                    elif "真传" in identity_name:
                        hourly_data[hour_str]["true_disciples"] += 1
                        
            except Exception as e:
                logger.error(f"Error parsing log info in finance_hourly: {e}")
                
        return hourly_data
    except Exception as e:
        logger.error(f"Error getting finance hourly stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/finance_hourly/cumulative")
async def get_cumulative_finance_hourly_stats(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Get cumulative hourly finance stats for the last N days"""
    try:
        start_date = date.today() - timedelta(days=days-1)
        dialect = db.bind.dialect.name
        hour_expr = get_hour_expr(UserLog.created_at, dialect)
        
        plans_result = await db.execute(text('SELECT id, name, identity_name, reward_credits FROM membership_plans'))
        plan_id_to_identity = {}
        plan_name_to_identity = {}
        plan_id_to_credits = {}
        plan_name_to_credits = {}
        for row in plans_result:
            plan_id_to_identity[str(row.id)] = row.identity_name
            plan_name_to_identity[row.name] = row.identity_name
            plan_id_to_credits[str(row.id)] = int(row.reward_credits)
            plan_name_to_credits[row.name] = int(row.reward_credits)
            
        logs_stmt = select(hour_expr.label("hour"), UserLog.extra_info).where(
            UserLog.operation_type == "recharge",
            func.date(UserLog.created_at) >= start_date
        )
        logs_result = await db.execute(logs_stmt)
        
        hourly_data = {
            str(h).zfill(2): {
                "recharged_credits": 0,
                "inner_disciples": 0,
                "core_disciples": 0,
                "true_disciples": 0
            } for h in range(24)
        }
        
        import json
        for row in logs_result:
            hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
            info = row.extra_info or ""
            
            try:
                data = json.loads(info)
                if data.get("is_gift"):
                    continue
                    
                plan_name = data.get("plan")
                plan_id = str(data.get("plan_id", ""))
                
                credits_added = 0
                if plan_name:
                    credits_added = plan_name_to_credits.get(plan_name, 0)
                elif plan_id:
                    credits_added = plan_id_to_credits.get(plan_id, 0)
                elif "ORDER:" in info:
                    order_id = data.get("order_id", "")
                    parts = order_id.split(":")
                    if len(parts) >= 3:
                        credits_added = plan_id_to_credits.get(parts[2], 0)
                        
                hourly_data[hour_str]["recharged_credits"] += credits_added
                
                identity_name = data.get("identity")
                if not identity_name:
                    if plan_name:
                        identity_name = plan_name_to_identity.get(plan_name)
                    elif plan_id:
                        identity_name = plan_id_to_identity.get(plan_id)
                    elif "ORDER:" in info:
                        order_id = data.get("order_id", "")
                        parts = order_id.split(":")
                        if len(parts) >= 3:
                            identity_name = plan_id_to_identity.get(parts[2])
                            
                if identity_name:
                    if "内门" in identity_name:
                        hourly_data[hour_str]["inner_disciples"] += 1
                    elif "核心" in identity_name:
                        hourly_data[hour_str]["core_disciples"] += 1
                    elif "真传" in identity_name:
                        hourly_data[hour_str]["true_disciples"] += 1
                        
            except Exception as e:
                pass
                
        return hourly_data
    except Exception as e:
        logger.error(f"Error getting cumulative finance hourly stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hourly")
async def get_hourly_stats(date_str: str = None, db: AsyncSession = Depends(get_db)):
    """Get hourly generation stats for a specific date (YYYY-MM-DD)"""
    try:
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = date.today()
            
        dialect = db.bind.dialect.name
        hour_expr = get_hour_expr(History.created_at, dialect)
        
        hourly_stmt = select(hour_expr.label("hour"), func.count(History.id).label("count")).where(func.date(History.created_at) == target_date).group_by(hour_expr).order_by(hour_expr)
        hourly_result = await db.execute(hourly_stmt)
        
        hourly_distribution = {str(h).zfill(2): 0 for h in range(24)}
        for row in hourly_result:
            hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
            hourly_distribution[hour_str] = row.count
            
        return hourly_distribution
    except Exception as e:
        logger.error(f"Error getting hourly stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/type_distribution")
async def get_type_distribution(date_str: str = None, db: AsyncSession = Depends(get_db)):
    """Get generation type distribution for a specific date (YYYY-MM-DD)"""
    try:
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = date.today()
            
        type_stmt = select(History.type, func.count(History.id)).where(func.date(History.created_at) == target_date).group_by(History.type)
        type_result = await db.execute(type_stmt)
        type_distribution = {row.type or "unknown": row.count for row in type_result}
        
        return type_distribution
    except Exception as e:
        logger.error(f"Error getting type distribution stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/type_distribution/cumulative")
async def get_cumulative_type_distribution(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Get cumulative generation type distribution for the last N days"""
    try:
        start_date = date.today() - timedelta(days=days-1)
        type_stmt = select(History.type, func.count(History.id)).where(func.date(History.created_at) >= start_date).group_by(History.type)
        type_result = await db.execute(type_stmt)
        type_distribution = {row.type or "unknown": row.count for row in type_result}
        return type_distribution
    except Exception as e:
        logger.error(f"Error getting cumulative type distribution stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hourly/cumulative")
async def get_cumulative_hourly_stats(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Get cumulative hourly generation stats for the last N days"""
    try:
        start_date = date.today() - timedelta(days=days-1)
        dialect = db.bind.dialect.name
        hour_expr = get_hour_expr(History.created_at, dialect)
        hourly_stmt = select(hour_expr.label("hour"), func.count(History.id).label("count")).where(func.date(History.created_at) >= start_date).group_by(hour_expr).order_by(hour_expr)
        hourly_result = await db.execute(hourly_stmt)
        
        hourly_distribution = {str(h).zfill(2): 0 for h in range(24)}
        for row in hourly_result:
            hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
            hourly_distribution[hour_str] = row.count
            
        return hourly_distribution
    except Exception as e:
        logger.error(f"Error getting cumulative hourly stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_stats_history(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Get historical stats for charts (last N days)"""
    try:
        video_types = [
            'video', 'video_undress', 'custom_video', 'perfect_video_insert', 
            'video_pro', 'doggy_style', 'blowjob', 'undress_tongue', 
            'closeup_blowjob', 'face_show', 'face_tongue', 'fuck', 
            'penetration', 'penetration_step1', 'penetration_step2', 'masturbation',
            'face_video_step1', 'face_video_step2'
        ]
        cost_case = case(
            (History.type.in_(video_types), 6),
            else_=2
        )

        start_date = date.today() - timedelta(days=days-1)
        
        user_stmt = select(func.date(User.created_at).label("date"), func.count(User.id).label("count")).where(func.date(User.created_at) >= start_date, User.is_channel_member == True).group_by(func.date(User.created_at)).order_by(func.date(User.created_at))
        user_result = await db.execute(user_stmt)
        user_history = {}
        for row in user_result:
            date_val = row.date if isinstance(row.date, str) else row.date.strftime("%Y-%m-%d")
            user_history[date_val] = row.count
        
        user_all_stmt = select(func.date(User.created_at).label("date"), func.count(User.id).label("count")).where(func.date(User.created_at) >= start_date).group_by(func.date(User.created_at)).order_by(func.date(User.created_at))
        user_all_result = await db.execute(user_all_stmt)
        user_all_history = {}
        for row in user_all_result:
            date_val = row.date if isinstance(row.date, str) else row.date.strftime("%Y-%m-%d")
            user_all_history[date_val] = row.count

        total_users_before_stmt = select(func.count(User.id)).where(func.date(User.created_at) < start_date)
        total_users_before_result = await db.execute(total_users_before_stmt)
        cumulative_users = total_users_before_result.scalar() or 0
        
        current_cumulative = cumulative_users
        daily_growth_rates = {}
        
        for i in range(days):
            current_date_obj = start_date + timedelta(days=i)
            date_str = current_date_obj.strftime("%Y-%m-%d")
            new_users_today = user_all_history.get(date_str, 0)
            total_users_today = current_cumulative + new_users_today
            
            if current_cumulative > 0:
                growth_rate = new_users_today / current_cumulative
            else:
                growth_rate = 0 if new_users_today == 0 else 1.0
                
            daily_growth_rates[date_str] = round(growth_rate * 100, 2)
            current_cumulative = total_users_today

        gen_stmt = select(func.date(History.created_at).label("date"), func.count(History.id).label("count")).where(func.date(History.created_at) >= start_date).group_by(func.date(History.created_at)).order_by(func.date(History.created_at))
        gen_result = await db.execute(gen_stmt)
        gen_history = {}
        for row in gen_result:
            date_val = row.date if isinstance(row.date, str) else row.date.strftime("%Y-%m-%d")
            gen_history[date_val] = row.count

        active_stmt = select(func.date(History.created_at).label("date"), func.count(func.distinct(History.user_id)).label("count")).where(func.date(History.created_at) >= start_date).group_by(func.date(History.created_at)).order_by(func.date(History.created_at))
        active_result = await db.execute(active_stmt)
        active_history = {}
        for row in active_result:
            date_val = row.date if isinstance(row.date, str) else row.date.strftime("%Y-%m-%d")
            active_history[date_val] = row.count

        web_active_stmt = select(func.date(History.created_at).label("date"), func.count(func.distinct(History.user_id)).label("count")).where(func.date(History.created_at) >= start_date, History.source == 'web').group_by(func.date(History.created_at)).order_by(func.date(History.created_at))
        web_active_result = await db.execute(web_active_stmt)
        web_active_history = {}
        for row in web_active_result:
            date_val = row.date if isinstance(row.date, str) else row.date.strftime("%Y-%m-%d")
            web_active_history[date_val] = row.count

        checkin_stmt = select(func.date(CheckinHistory.checkin_date).label("date"), func.count(CheckinHistory.id).label("count")).where(func.date(CheckinHistory.checkin_date) >= start_date).group_by(func.date(CheckinHistory.checkin_date)).order_by(func.date(CheckinHistory.checkin_date))
        checkin_result = await db.execute(checkin_stmt)
        checkin_history = {}
        for row in checkin_result:
            date_val = row.date if isinstance(row.date, str) else row.date.strftime("%Y-%m-%d")
            checkin_history[date_val] = row.count

        consumed_stmt = select(func.date(History.created_at).label("date"), func.sum(cost_case).label("count")).where(func.date(History.created_at) >= start_date).group_by(func.date(History.created_at)).order_by(func.date(History.created_at))
        consumed_result = await db.execute(consumed_stmt)
        consumed_history = {}
        for row in consumed_result:
            date_val = row.date if isinstance(row.date, str) else row.date.strftime("%Y-%m-%d")
            consumed_history[date_val] = row.count
            
        # Daily TON and Stars Recharge History
        # We now calculate the actual TON and Stars spent, not the credits granted.
        
        # 1. Map plan names/ids to prices and identities
        plans_result = await db.execute(text('SELECT id, name, identity_name, price_ton, price_stars, price_rmb, reward_credits FROM membership_plans'))
        plan_ton_prices = {}
        plan_stars_prices = {}
        plan_rmb_prices = {}
        plan_name_to_ton = {}
        plan_name_to_rmb = {}
        plan_id_to_identity = {}
        plan_name_to_identity = {}
        plan_id_to_credits = {}
        plan_name_to_credits = {}
        for row in plans_result:
            plan_ton_prices[str(row.id)] = float(row.price_ton)
            plan_stars_prices[str(row.id)] = int(row.price_stars)
            plan_rmb_prices[str(row.id)] = float(row.price_rmb)
            plan_name_to_ton[row.name] = float(row.price_ton)
            plan_name_to_rmb[row.name] = float(row.price_rmb)
            plan_id_to_identity[str(row.id)] = row.identity_name
            plan_name_to_identity[row.name] = row.identity_name
            plan_id_to_credits[str(row.id)] = int(row.reward_credits)
            plan_name_to_credits[row.name] = int(row.reward_credits)
            
        # 2. Fetch all raw recharge logs
        logs_stmt = select(func.date(UserLog.created_at).label("date"), UserLog.extra_info).where(UserLog.operation_type == "recharge")
        logs_result = await db.execute(logs_stmt)
        
        ton_history = {}
        stars_history = {}
        rmb_history = {}
        
        inner_history = {}
        core_history = {}
        true_history = {}
        
        recharged_credits_history = {}
        
        ton_before = 0.0
        stars_before = 0
        rmb_before = 0.0
        recharged_credits_before = 0
        
        import json
        for row in logs_result:
            date_val = row.date if isinstance(row.date, str) else row.date.strftime("%Y-%m-%d")
            
            is_before = False
            if isinstance(row.date, str):
                log_date = datetime.strptime(row.date, "%Y-%m-%d").date()
                if log_date < start_date:
                    is_before = True
            else:
                if row.date < start_date:
                    is_before = True
                    
            info = row.extra_info or ""
            
            try:
                data = json.loads(info)
                # Ignore manual gifts
                if data.get("is_gift"):
                    continue
                    
                # Track Disciple Identities
                plan_name = data.get("plan")
                plan_id = str(data.get("plan_id", ""))
                
                identity_name = data.get("identity") # RMB typically has it
                if not identity_name:
                    if plan_name:
                        identity_name = plan_name_to_identity.get(plan_name)
                    elif plan_id:
                        identity_name = plan_id_to_identity.get(plan_id)
                    elif "ORDER:" in info:
                        order_id = data.get("order_id", "")
                        parts = order_id.split(":")
                        if len(parts) >= 3:
                            identity_name = plan_id_to_identity.get(parts[2])
                            
                if identity_name and not is_before:
                    if "内门" in identity_name:
                        inner_history[date_val] = inner_history.get(date_val, 0) + 1
                    elif "核心" in identity_name:
                        core_history[date_val] = core_history.get(date_val, 0) + 1
                    elif "真传" in identity_name:
                        true_history[date_val] = true_history.get(date_val, 0) + 1
                        
                # Track Recharge Credits
                credits_added = 0
                if plan_name:
                    credits_added = plan_name_to_credits.get(plan_name, 0)
                elif plan_id:
                    credits_added = plan_id_to_credits.get(plan_id, 0)
                elif "ORDER:" in info:
                    order_id = data.get("order_id", "")
                    parts = order_id.split(":")
                    if len(parts) >= 3:
                        credits_added = plan_id_to_credits.get(parts[2], 0)
                        
                if is_before:
                    recharged_credits_before += credits_added
                else:
                    recharged_credits_history[date_val] = recharged_credits_history.get(date_val, 0) + credits_added
                    
                # Check for RMB
                if "rmb_payment" in info:
                    plan_name = data.get("plan")
                    rmb_spent = 0.0
                    if plan_name:
                        rmb_spent = plan_name_to_rmb.get(plan_name, 0.0)
                    if is_before:
                        rmb_before += rmb_spent
                    else:
                        rmb_history[date_val] = rmb_history.get(date_val, 0.0) + rmb_spent

                # Check for Stars
                elif "telegram_stars" in info or "stars" in info.lower():
                    plan_id = str(data.get("plan_id", ""))
                    stars_spent = plan_stars_prices.get(plan_id, 0)
                    if is_before:
                        stars_before += stars_spent
                    else:
                        stars_history[date_val] = stars_history.get(date_val, 0) + stars_spent
                    
                # Check for TON
                elif "ORDER:" in info:
                    plan_name = data.get("plan")
                    ton_spent = 0.0
                    if plan_name:
                        ton_spent = plan_name_to_ton.get(plan_name, 0.0)
                    else:
                        # Try to extract plan_id from ORDER:{user_id}:{plan_id}:{timestamp}
                        order_id = data.get("order_id", "")
                        parts = order_id.split(":")
                        if len(parts) >= 3:
                            plan_id = parts[2]
                            ton_spent = plan_ton_prices.get(plan_id, 0.0)
                            
                    if is_before:
                        ton_before += ton_spent
                    else:
                        ton_history[date_val] = ton_history.get(date_val, 0.0) + ton_spent
                    
            except Exception as e:
                logger.error(f"Error parsing log info {info}: {e}")
        
        current_ton_cumulative = ton_before
        current_stars_cumulative = stars_before
        current_rmb_cumulative = rmb_before
        current_recharged_credits_cumulative = recharged_credits_before

        rates = await get_exchange_rates()
        ton_to_usdt = rates["ton_to_usdt"]
        rmb_to_usdt = rates["rmb_to_usdt"]
        stars_to_usdt = rates["stars_to_usdt"]

        history_data = []
        for i in range(days):
            current_date = start_date + timedelta(days=i)
            date_str = current_date.strftime("%Y-%m-%d")
            
            ton_today = ton_history.get(date_str, 0.0)
            stars_today = stars_history.get(date_str, 0)
            rmb_today = rmb_history.get(date_str, 0.0)
            recharged_credits_today = recharged_credits_history.get(date_str, 0)
            
            usdt_today = (ton_today * ton_to_usdt) + (stars_today * stars_to_usdt) + (rmb_today * rmb_to_usdt)
            usdt_today = round(usdt_today, 2)
            
            current_ton_cumulative += ton_today
            current_stars_cumulative += stars_today
            current_rmb_cumulative += rmb_today
            current_recharged_credits_cumulative += recharged_credits_today
            
            current_usdt_cumulative = (current_ton_cumulative * ton_to_usdt) + (current_stars_cumulative * stars_to_usdt) + (current_rmb_cumulative * rmb_to_usdt)
            current_usdt_cumulative = round(current_usdt_cumulative, 2)
            
            history_data.append({
                "date": date_str,
                "new_users": user_history.get(date_str, 0),
                "new_users_all": user_all_history.get(date_str, 0),
                "growth_rate": daily_growth_rates.get(date_str, 0),
                "generations": gen_history.get(date_str, 0),
                "active_users": active_history.get(date_str, 0),
                "web_active_users": web_active_history.get(date_str, 0),
                "checkins": checkin_history.get(date_str, 0),
                "consumed_credits": consumed_history.get(date_str, 0),
                "ton_recharge": ton_today,
                "stars_recharge": stars_today,
                "rmb_recharge": round(rmb_today, 2),
                "usdt_recharge": usdt_today,
                "cumulative_ton": round(current_ton_cumulative, 2),
                "cumulative_stars": current_stars_cumulative,
                "cumulative_rmb": round(current_rmb_cumulative, 2),
                "cumulative_usdt": current_usdt_cumulative,
                "recharged_credits": recharged_credits_today,
                "cumulative_recharged_credits": current_recharged_credits_cumulative,
                "inner_disciples": inner_history.get(date_str, 0),
                "core_disciples": core_history.get(date_str, 0),
                "true_disciples": true_history.get(date_str, 0)
            })
            
        return history_data
    except Exception as e:
        logger.error(f"Error getting history stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
