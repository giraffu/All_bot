import sys
import os
from pathlib import Path
import logging

# Add project root to sys.path to import src modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# Change working directory to project root so database file is found correctly
os.chdir(str(PROJECT_ROOT))

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, case, Integer, Float
from sqlalchemy.orm import selectinload
from typing import List, Optional, Any, Dict
import httpx
from datetime import datetime, date, timedelta

# Import from existing bot codebase
from src.database.core import get_db, init_db
from src.database.models import User, History, Referral, TemplateContribution, CheckinHistory, UserLog
from src.services.image_service import image_service
from src.services.log_service import LogService
from src.services.storage import storage
from config import API_BASE, STATUS_ENDPOINT, MINIO_BUCKET, MINIO_TEMPLATE_BUCKET
from dashboard.backend.auth import auth_router, get_current_user, oauth2_scheme

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

app = FastAPI(title="TeleBot Dashboard API")

# Include Auth Router
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])


@app.on_event("startup")
async def startup_event():
    """Ensure database tables are created on startup"""
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

# Note: Local static files mounting removed in favor of MinIO presigned URLs

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from pydantic import BaseModel
from fastapi import Request
import fastapi.responses

# Security middleware
@app.middleware("http")
async def check_auth_header(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        # Exclude public endpoints
        public_paths = ["/api/auth/login", "/api/health", "/api/status"]
        if request.url.path not in public_paths:
            try:
                # FastAPI's Request doesn't have Depends easily in middleware,
                # let's extract the token manually
                auth_header = request.headers.get("Authorization")
                if not auth_header or not auth_header.startswith("Bearer "):
                    return fastapi.responses.JSONResponse(
                        status_code=401,
                        content={"detail": "Not authenticated"}
                    )
                token = auth_header.split(" ")[1]
                await get_current_user(token)
            except Exception as e:
                return fastapi.responses.JSONResponse(
                    status_code=401,
                    content={"detail": "Could not validate credentials"}
                )
    return await call_next(request)

# Pydantic models for request bodies
class UpdateCreditsRequest(BaseModel):
    credits: int

class HistoryResponse(BaseModel):
    id: int
    user_id: int
    task_id: Optional[str]
    type: Optional[str]
    prompt: Optional[str]
    input_file: Optional[str]
    output_file: Optional[str]
    input_file_url: Optional[str] = None
    output_file_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class HistoryWithUserResponse(HistoryResponse):
    username: Optional[str] = None
    full_name: Optional[str] = None

class HistoryListResponse(BaseModel):
    items: List[HistoryWithUserResponse]
    total: int

class TemplateContributionResponse(BaseModel):
    id: int
    user_id: int
    username: Optional[str]
    full_name: Optional[str]
    file_path: str
    file_type: str
    is_reviewed: bool
    created_at: datetime
    preview_url: str

    class Config:
        from_attributes = True

class LogResponse(BaseModel):
    id: int
    user_id: int
    username: Optional[str] = None
    operation_type: str
    credit_change: int
    current_balance: int
    created_at: str  # LogService returns isoformat string
    extra_info: Optional[Dict[str, Any]] = None

class LogListResponse(BaseModel):
    items: List[LogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

@app.get("/")
async def root():
    return {"message": "TeleBot Dashboard Backend is Running", "status": "ok"}

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/logs", response_model=LogListResponse)
async def get_logs(
    user_id: Optional[int] = None,
    operation_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
):
    """
    Get user operation logs with filtering and pagination.
    Dates should be in YYYY-MM-DD format.
    """
    try:
        start_dt = None
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                pass
        
        end_dt = None
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                # Include the whole day
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
            except ValueError:
                pass

        result = await LogService.get_logs(
            user_id=user_id,
            operation_type=operation_type,
            start_date=start_dt,
            end_date=end_dt,
            page=page,
            page_size=page_size
        )
        
        # Ensure items conform to response model
        # LogService returns items as dicts, which is fine for Pydantic if keys match.
        # Just need to make sure `extra_info` is handled correctly (it's already a dict in service)
        
        return result
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def get_hour_expr(col, dialect_name):
    if dialect_name == 'postgresql':
        return func.extract('hour', col)
    return func.strftime('%H', col)

def get_days_diff_expr(col, dialect_name):
    if dialect_name == 'postgresql':
        return func.extract('day', func.now() - col)
    return func.julianday('now') - func.julianday(col)

@app.get("/api/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics"""
    try:
        # Cost calculation logic
        # 6 credits: video, video_undress, custom_video, perfect_video_insert, video_pro, doggy_style, blowjob, 
        #           undress_tongue, closeup_blowjob, face_show, face_tongue, fuck, penetration, 
        #           penetration_step1, penetration_step2, masturbation
        # 2 credit: others (image, undress, face_swap, random_faceswap, etc.)
        video_types = [
            'video', 'video_undress', 'custom_video', 'perfect_video_insert', 
            'video_pro', 'doggy_style', 'blowjob', 'undress_tongue', 
            'closeup_blowjob', 'face_show', 'face_tongue', 'fuck', 
            'penetration', 'penetration_step1', 'penetration_step2', 'masturbation'
        ]
        cost_case = case(
            (History.type.in_(video_types), 6),
            else_=2
        )

        # Total users (Channel Members)
        result = await db.execute(select(func.count(User.id)).where(User.is_channel_member == True))
        total_users = result.scalar()

        # Total users (All)
        result_all = await db.execute(select(func.count(User.id)))
        total_db_users = result_all.scalar() or 0

        # Total history/generations
        result = await db.execute(select(func.count(History.id)))
        total_generations = result.scalar()

        # Total credits in circulation
        result = await db.execute(select(func.sum(User.credits)))
        total_credits = result.scalar() or 0
        
        # Total temporary ingot
        result = await db.execute(select(func.sum(User.temp_credits)))
        total_temporary_ingot = result.scalar() or 0

        # Total active credits in circulation (only users with generation_count > 0)
        result = await db.execute(select(func.sum(User.credits)).where(User.generation_count > 0))
        total_active_credits = result.scalar() or 0
        
        # Total active temporary ingot (only users with generation_count > 0)
        result = await db.execute(select(func.sum(User.temp_credits)).where(User.generation_count > 0))
        total_active_temporary_ingot = result.scalar() or 0

        # Total referrals
        result = await db.execute(select(func.count(Referral.id)))
        total_referrals = result.scalar() or 0

        # Total consumed credits
        result = await db.execute(select(func.sum(cost_case)))
        total_consumed_credits = result.scalar() or 0
        
        # Total template contributions
        result = await db.execute(select(func.count(TemplateContribution.id)))
        total_template_contributions = result.scalar() or 0
        
        # Total approved template contributions
        result = await db.execute(select(func.count(TemplateContribution.id)).where(TemplateContribution.is_reviewed == True))
        total_approved_contributions = result.scalar() or 0
        
        # Today's stats
        today = date.today()
        
        # Today's users
        result = await db.execute(
            select(func.count(User.id)).where(func.date(User.created_at) == today, User.is_channel_member == True)
        )
        today_users = result.scalar() or 0

        # Today's users (All/Virtual - includes non-members)
        result = await db.execute(
            select(func.count(User.id)).where(func.date(User.created_at) == today)
        )
        today_users_all = result.scalar() or 0
        
        # Today's generations
        result = await db.execute(
            select(func.count(History.id)).where(func.date(History.created_at) == today)
        )
        today_generations = result.scalar() or 0

        # Today's active users (unique users in History)
        result = await db.execute(
            select(func.count(func.distinct(History.user_id))).where(func.date(History.created_at) == today)
        )
        today_active_users = result.scalar() or 0

        # Today's consumed credits
        result = await db.execute(
            select(func.sum(cost_case)).where(func.date(History.created_at) == today)
        )
        today_consumed_credits = result.scalar() or 0

        # Today's check-ins (users who checked in today)
        result = await db.execute(
            select(func.count(User.id)).where(User.last_checkin == today)
        )
        today_checkins = result.scalar() or 0

        # Today's type distribution
        today_dist_stmt = (
            select(History.type, func.count(History.id))
            .where(func.date(History.created_at) == today)
            .group_by(History.type)
        )
        today_dist_result = await db.execute(today_dist_stmt)
        today_type_distribution = {row.type or "unknown": row.count for row in today_dist_result}
        
        # Total type distribution
        total_dist_stmt = (
            select(History.type, func.count(History.id))
            .group_by(History.type)
        )
        total_dist_result = await db.execute(total_dist_stmt)
        total_type_distribution = {row.type or "unknown": row.count for row in total_dist_result}
        
        # Today's hourly distribution
        # Extract hour from created_at. In SQLite: strftime('%H', created_at)
        dialect = db.bind.dialect.name
        hour_expr = get_hour_expr(History.created_at, dialect)
        
        hourly_stmt = (
            select(hour_expr.label("hour"), func.count(History.id).label("count"))
            .where(func.date(History.created_at) == today)
            .group_by(hour_expr)
            .order_by(hour_expr)
        )
        hourly_result = await db.execute(hourly_stmt)
        
        # Initialize all 24 hours with 0
        today_hourly_distribution = {str(h).zfill(2): 0 for h in range(24)}
        
        for row in hourly_result:
            # Handle both string ('01') and integer (1) from different dialects
            hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
            today_hourly_distribution[hour_str] = row.count

        # Generation Count Distribution
        # 0, 1, 2, 3, 4, 5, 6-10, 11-20, 21-50, 51-100, 101-200, 201-500, 501-1000, 1000+
        # Handle None as 0 using coalesce or handling in case
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
        
        gen_dist_stmt = (
            select(gen_case.label('range'), func.count(User.id).label('count'))
            .group_by(gen_case)
        )
        gen_dist_result = await db.execute(gen_dist_stmt)
        
        # Define order for frontend consistency
        gen_distribution_order = [
            '0', '1', '2', '3', '4', '5', 
            '6-10', '11-20', '21-50', '51-100', 
            '101-200', '201-500', '501-1000', '1000+'
        ]
        
        gen_distribution = {k: 0 for k in gen_distribution_order}
        
        for row in gen_dist_result:
            if row.range in gen_distribution:
                gen_distribution[row.range] = row.count

        # Avg Daily Generation Distribution
        # logic: generation_count / max(1, (now - created_at).days)
        # SQLite: cast(julianday('now') - julianday(created_at) as integer)
        # Note: julianday returns float days.
        
        days_diff = get_days_diff_expr(User.created_at, dialect)
        # Ensure at least 1 day to avoid division by zero
        days_valid = case((days_diff < 1, 1), else_=days_diff)
        
        avg_daily = func.cast(func.coalesce(User.generation_count, 0), Float) / days_valid
        
        # Ranges: 0, 0-1, 1-3, 3-5, 5-10, 10-20, 20+
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
        
        avg_dist_stmt = (
            select(avg_case.label('range'), func.count(User.id).label('count'))
            .group_by(avg_case)
        )
        avg_dist_result = await db.execute(avg_dist_stmt)
        
        avg_distribution_order = ['0', '0-1', '1-3', '3-5', '5-10', '10-20', '20+']
        avg_distribution = {k: 0 for k in avg_distribution_order}
        
        for row in avg_dist_result:
            if row.range in avg_distribution:
                avg_distribution[row.range] = row.count

        # Credit Consumption Distribution
        # Note: We need to calculate total consumed credits per user.
        # Since User model doesn't store total consumed credits (only current credits),
        # we need to join User with History and sum the costs.
        # This can be expensive for large datasets.
        # Alternative: If User model had a 'total_consumed_credits' field, it would be faster.
        # For now, we will perform a subquery aggregation.
        
        # Subquery to calculate total consumed credits per user
        user_consumed_subquery = (
            select(History.user_id, func.sum(cost_case).label('total_consumed'))
            .group_by(History.user_id)
            .subquery()
        )
        
        # We need to include users with 0 consumption too (users not in history)
        # But for distribution, 0 is a category.
        
        # Join User with subquery
        # COALESCE(subquery.total_consumed, 0)
        
        # However, selecting from User and joining might be slow if we just want distribution.
        # Let's try to do it in one go if possible, or just use the subquery results + count of users with no history.
        
        # Let's use a Common Table Expression (CTE) or subquery approach for cleaner code
        # But SQLAlchemy asyncio support for CTEs depends on the driver.
        # Let's stick to a slightly more complex query or two steps.
        
        # Step 1: Distribution of users who have consumed credits (from History aggregation)
        # Step 2: Users with 0 consumption = Total Users - Users with >0 consumption
        
        # Ranges: 0, 1-10, 11-50, 51-100, 101-500, 501-1000, 1000-5000, 5000+
        
        # It's better to update User model to have total_consumed_credits for performance in the future.
        # For now, let's execute the aggregation.
        
        # Calculate consumption for each user
        consumption_stmt = (
            select(History.user_id, func.sum(cost_case).label('consumed'))
            .group_by(History.user_id)
        )
        
        # This returns rows of (user_id, consumed). We can wrap this to count distribution.
        # But we can't easily do a distribution on a grouped result in one standard SQL without nested selects.
        # Nested select:
        
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
            else_='0' # Should not happen for this subquery as sum > 0 usually, but safety
        )
        
        credit_dist_stmt = (
            select(credit_dist_case.label('range'), func.count().label('count'))
            .group_by(credit_dist_case)
        )
        
        credit_dist_result = await db.execute(credit_dist_stmt)
        
        credit_distribution_order = [
            '0', '1-10', '11-50', '51-100', '101-500', 
            '501-1000', '1001-5000', '5000+'
        ]
        
        credit_distribution = {k: 0 for k in credit_distribution_order}
        
        users_with_consumption = 0
        for row in credit_dist_result:
            if row.range in credit_distribution:
                credit_distribution[row.range] = row.count
                users_with_consumption += row.count
        
        # Users with 0 consumption
        credit_distribution['0'] = total_db_users - users_with_consumption
        if credit_distribution['0'] < 0: credit_distribution['0'] = 0 # Safety

        # Avg Daily Credit Consumption Distribution
        # logic: total_consumed / max(1, (now - created_at).days)
        # This requires joining the consumed_sub with User table to get created_at
        
        # join consumed_sub with User
        # calc avg daily
        
        # This query is getting complex. 
        # avg_daily_credit = consumed_col / max(1, (now - User.created_at))
        
        avg_credit_query = (
            select(
                consumed_col,
                User.created_at
            )
            .join(User, User.id == consumed_sub.c.user_id)
        )
        
        # We might need to fetch this and process in python if SQL is too complex for the ORM/Driver combo without raw SQL
        # Or construct the case statement with the join.
        
        days_diff_sub = get_days_diff_expr(User.created_at, dialect)
        days_valid_sub = case((days_diff_sub < 1, 1), else_=days_diff_sub)
        
        avg_daily_credit = func.cast(consumed_col, Float) / days_valid_sub
        
        avg_credit_case = case(
            (avg_daily_credit <= 0, '0'), # Should be handled by 0 consumption logic separately
            ((avg_daily_credit > 0) & (avg_daily_credit <= 1), '0-1'),
            ((avg_daily_credit > 1) & (avg_daily_credit <= 5), '1-5'),
            ((avg_daily_credit > 5) & (avg_daily_credit <= 10), '5-10'),
            ((avg_daily_credit > 10) & (avg_daily_credit <= 20), '10-20'),
            ((avg_daily_credit > 20) & (avg_daily_credit <= 50), '20-50'),
            (avg_daily_credit > 50, '50+'),
            else_='0'
        )
        
        avg_credit_dist_stmt = (
            select(avg_credit_case.label('range'), func.count().label('count'))
            .select_from(User)
            .join(consumed_sub, User.id == consumed_sub.c.user_id)
            .group_by(avg_credit_case)
        )
        
        avg_credit_dist_result = await db.execute(avg_credit_dist_stmt)
        
        avg_credit_distribution_order = ['0', '0-1', '1-5', '5-10', '10-20', '20-50', '50+']
        avg_credit_distribution = {k: 0 for k in avg_credit_distribution_order}
        
        users_with_avg_credit = 0
        for row in avg_credit_dist_result:
            if row.range in avg_credit_distribution:
                avg_credit_distribution[row.range] = row.count
                users_with_avg_credit += row.count
                
        # Users with 0 avg consumption (same as 0 consumption)
        avg_credit_distribution['0'] = total_db_users - users_with_avg_credit
        if avg_credit_distribution['0'] < 0: avg_credit_distribution['0'] = 0

        # Credit Holding Distribution
        # Ranges: 0, 1-10, 11-50, 51-100, 101-500, 501-1000, 1001-5000, 5000+
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
        
        holding_dist_stmt = (
            select(holding_case.label('range'), func.count(User.id).label('count'))
            .group_by(holding_case)
        )
        holding_dist_result = await db.execute(holding_dist_stmt)
        
        holding_distribution_order = [
            '0', '1-10', '11-50', '51-100', '101-500', '501-1000', '1001-5000', '5000+'
        ]
        
        holding_distribution = {k: 0 for k in holding_distribution_order}
        
        for row in holding_dist_result:
            if row.range in holding_distribution:
                holding_distribution[row.range] = row.count

        return {
            "total_users": total_users,
            "total_generations": total_generations,
            "total_credits": total_credits,
            "total_temporary_ingot": total_temporary_ingot,
            "total_active_credits": total_active_credits,
            "total_active_temporary_ingot": total_active_temporary_ingot,
            "total_referrals": total_referrals,
            "total_consumed_credits": total_consumed_credits,
            "total_template_contributions": total_template_contributions,
            "total_approved_contributions": total_approved_contributions,
            "today_users": today_users,
            "today_users_all": today_users_all,
            "today_generations": today_generations,
            "today_active_users": today_active_users,
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
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats/hourly")
async def get_hourly_stats(date_str: str = None, db: AsyncSession = Depends(get_db)):
    """Get hourly generation stats for a specific date (YYYY-MM-DD)"""
    try:
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = date.today()
            
        dialect = db.bind.dialect.name
        hour_expr = get_hour_expr(History.created_at, dialect)
        
        hourly_stmt = (
            select(hour_expr.label("hour"), func.count(History.id).label("count"))
            .where(func.date(History.created_at) == target_date)
            .group_by(hour_expr)
            .order_by(hour_expr)
        )
        hourly_result = await db.execute(hourly_stmt)
        
        # Initialize all 24 hours with 0
        hourly_distribution = {str(h).zfill(2): 0 for h in range(24)}
        
        for row in hourly_result:
            hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
            hourly_distribution[hour_str] = row.count
            
        return hourly_distribution
    except Exception as e:
        logger.error(f"Error getting hourly stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats/type_distribution")
async def get_type_distribution(date_str: str = None, db: AsyncSession = Depends(get_db)):
    """Get generation type distribution for a specific date (YYYY-MM-DD)"""
    try:
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = date.today()
            
        # Type distribution
        type_stmt = (
            select(History.type, func.count(History.id))
            .where(func.date(History.created_at) == target_date)
            .group_by(History.type)
        )
        type_result = await db.execute(type_stmt)
        type_distribution = {row.type or "unknown": row.count for row in type_result}
        
        return type_distribution
    except Exception as e:
        logger.error(f"Error getting type distribution stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats/type_distribution/cumulative")
async def get_cumulative_type_distribution(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Get cumulative generation type distribution for the last N days"""
    try:
        start_date = date.today() - timedelta(days=days-1)
        
        # Type distribution
        type_stmt = (
            select(History.type, func.count(History.id))
            .where(func.date(History.created_at) >= start_date)
            .group_by(History.type)
        )
        type_result = await db.execute(type_stmt)
        type_distribution = {row.type or "unknown": row.count for row in type_result}
        
        return type_distribution
    except Exception as e:
        logger.error(f"Error getting cumulative type distribution stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bot/queue")
async def get_bot_queue():
    """Get current bot queue status from image service"""
    try:
        status = await image_service.get_queue_info()
        return status or {
            "total_active_tasks": 0,
            "img2img_active_tasks": 0,
            "img2video_active_tasks": 0
        }
    except Exception as e:
        logger.error(f"Error getting bot queue status: {e}")
        return {
            "total_active_tasks": 0,
            "img2img_active_tasks": 0,
            "img2video_active_tasks": 0,
            "error": str(e)
        }

@app.get("/api/stats/hourly/cumulative")
async def get_cumulative_hourly_stats(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Get cumulative hourly generation stats for the last N days"""
    try:
        start_date = date.today() - timedelta(days=days-1)
        
        dialect = db.bind.dialect.name
        hour_expr = get_hour_expr(History.created_at, dialect)
        
        # Aggregate count by hour across all days in range
        hourly_stmt = (
            select(hour_expr.label("hour"), func.count(History.id).label("count"))
            .where(func.date(History.created_at) >= start_date)
            .group_by(hour_expr)
            .order_by(hour_expr)
        )
        hourly_result = await db.execute(hourly_stmt)
        
        # Initialize all 24 hours with 0
        hourly_distribution = {str(h).zfill(2): 0 for h in range(24)}
        
        for row in hourly_result:
            hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
            hourly_distribution[hour_str] = row.count
            
        return hourly_distribution
    except Exception as e:
        logger.error(f"Error getting cumulative hourly stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats/history")
async def get_stats_history(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Get historical stats for charts (last N days)"""
    try:
        # Cost calculation logic (same as get_stats)
        video_types = [
            'video', 'video_undress', 'custom_video', 'perfect_video_insert', 
            'video_pro', 'doggy_style', 'blowjob', 'undress_tongue', 
            'closeup_blowjob', 'face_show', 'face_tongue', 'fuck', 
            'penetration', 'penetration_step1', 'penetration_step2', 'masturbation'
        ]
        cost_case = case(
            (History.type.in_(video_types), 6),
            else_=2
        )

        # Calculate start date (N days ago)
        start_date = date.today() - timedelta(days=days-1)
        
        # Daily new users
        user_stmt = (
            select(func.date(User.created_at).label("date"), func.count(User.id).label("count"))
            .where(func.date(User.created_at) >= start_date, User.is_channel_member == True)
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
        )
        user_result = await db.execute(user_stmt)
        user_history = {}
        for row in user_result:
            # SQLite func.date returns string "YYYY-MM-DD"
            date_val = row.date
            if not isinstance(date_val, str):
                date_val = date_val.strftime("%Y-%m-%d")
            user_history[date_val] = row.count
        
        # Daily new users (All/Virtual)
        user_all_stmt = (
            select(func.date(User.created_at).label("date"), func.count(User.id).label("count"))
            .where(func.date(User.created_at) >= start_date)
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
        )
        user_all_result = await db.execute(user_all_stmt)
        user_all_history = {}
        for row in user_all_result:
            date_val = row.date
            if not isinstance(date_val, str):
                date_val = date_val.strftime("%Y-%m-%d")
            user_all_history[date_val] = row.count

        # Calculate daily user growth rate
        # Growth Rate = (Current Day Users - Previous Day Users) / Previous Day Users
        # We need total cumulative users up to each day to calculate growth of total user base?
        # Or growth of daily new users?
        # User request: "Current Day Users - Yesterday Users / Yesterday Users"
        # Usually implies Total User Base Growth Rate.
        # Let's calculate Cumulative Users for each day first.
        
        # Get total users count before start_date
        total_users_before_stmt = select(func.count(User.id)).where(func.date(User.created_at) < start_date)
        total_users_before_result = await db.execute(total_users_before_stmt)
        cumulative_users = total_users_before_result.scalar() or 0
        
        user_growth_rate_history = {}
        
        # We need to iterate from start_date to today
        # But to calc growth for start_date, we need (start_date - 1) total users.
        # So we already have cumulative_users (which is total up to start_date-1).
        
        current_cumulative = cumulative_users
        previous_cumulative = cumulative_users
        
        # We need to process day by day to build cumulative count
        # user_all_history contains 'new users' for each day in range
        
        # To handle the first day's growth rate correctly, we need the "yesterday" of start_date
        # which is covered by previous_cumulative.
        
        # Wait, if previous_cumulative is 0, growth rate is undefined (or 100% if new users > 0).
        
        daily_growth_rates = {}
        
        for i in range(days):
            current_date_obj = start_date + timedelta(days=i)
            date_str = current_date_obj.strftime("%Y-%m-%d")
            
            new_users_today = user_all_history.get(date_str, 0)
            
            # Total users at end of today
            total_users_today = current_cumulative + new_users_today
            
            # Growth Rate calculation:
            # (Total Today - Total Yesterday) / Total Yesterday
            # = New Users Today / Total Yesterday
            
            if current_cumulative > 0:
                growth_rate = new_users_today / current_cumulative
            else:
                growth_rate = 0 if new_users_today == 0 else 1.0 # 100% growth if starting from 0
                
            daily_growth_rates[date_str] = round(growth_rate * 100, 2) # Percentage
            
            # Update cumulative for next iteration
            current_cumulative = total_users_today

        # Daily generations
        gen_stmt = (
            select(func.date(History.created_at).label("date"), func.count(History.id).label("count"))
            .where(func.date(History.created_at) >= start_date)
            .group_by(func.date(History.created_at))
            .order_by(func.date(History.created_at))
        )
        gen_result = await db.execute(gen_stmt)
        gen_history = {}
        for row in gen_result:
            date_val = row.date
            if not isinstance(date_val, str):
                date_val = date_val.strftime("%Y-%m-%d")
            gen_history[date_val] = row.count

        # Daily active users
        active_stmt = (
            select(func.date(History.created_at).label("date"), func.count(func.distinct(History.user_id)).label("count"))
            .where(func.date(History.created_at) >= start_date)
            .group_by(func.date(History.created_at))
            .order_by(func.date(History.created_at))
        )
        active_result = await db.execute(active_stmt)
        active_history = {}
        for row in active_result:
            date_val = row.date
            if not isinstance(date_val, str):
                date_val = date_val.strftime("%Y-%m-%d")
            active_history[date_val] = row.count

        # Daily check-ins
        checkin_stmt = (
            select(func.date(CheckinHistory.checkin_date).label("date"), func.count(CheckinHistory.id).label("count"))
            .where(func.date(CheckinHistory.checkin_date) >= start_date)
            .group_by(func.date(CheckinHistory.checkin_date))
            .order_by(func.date(CheckinHistory.checkin_date))
        )
        checkin_result = await db.execute(checkin_stmt)
        checkin_history = {}
        for row in checkin_result:
            date_val = row.date
            if not isinstance(date_val, str):
                date_val = date_val.strftime("%Y-%m-%d")
            checkin_history[date_val] = row.count

        # Daily consumed credits
        consumed_stmt = (
            select(func.date(History.created_at).label("date"), func.sum(cost_case).label("count"))
            .where(func.date(History.created_at) >= start_date)
            .group_by(func.date(History.created_at))
            .order_by(func.date(History.created_at))
        )
        consumed_result = await db.execute(consumed_stmt)
        consumed_history = {}
        for row in consumed_result:
            date_val = row.date
            if not isinstance(date_val, str):
                date_val = date_val.strftime("%Y-%m-%d")
            consumed_history[date_val] = row.count
        
        # Fill in missing dates with zero
        history_data = []
        for i in range(days):
            current_date = start_date + timedelta(days=i)
            date_str = current_date.strftime("%Y-%m-%d")
            history_data.append({
                "date": date_str,
                "new_users": user_history.get(date_str, 0),
                "new_users_all": user_all_history.get(date_str, 0),
                "growth_rate": daily_growth_rates.get(date_str, 0),
                "generations": gen_history.get(date_str, 0),
                "active_users": active_history.get(date_str, 0),
                "checkins": checkin_history.get(date_str, 0),
                "consumed_credits": consumed_history.get(date_str, 0)
            })
            
        return history_data
    except Exception as e:
        logger.error(f"Error getting history stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/users")
async def get_users(skip: int = 0, limit: int = 10000, db: AsyncSession = Depends(get_db)):
    """Get user list with referral counts"""
    try:
        # Optimized query using denormalized columns
        stmt = (
            select(User)
            .options(selectinload(User.inviter_user))
            .order_by(desc(User.created_at))
            .offset(skip)
            .limit(limit)
        )

        result = await db.execute(stmt)
        users = result.scalars().all()
        users_with_counts = []
        
        for user in users:
            # Convert SQLAlchemy model to dict
            user_dict = {c.name: getattr(user, c.name) for c in user.__table__.columns}
            
            # Ensure temporary_ingot is mapped from temp_credits
            user_dict['temporary_ingot'] = getattr(user, 'temp_credits', 0)
            
            # Use denormalized columns directly
            user_dict["referral_count"] = user.referral_count or 0
            user_dict["last_activity"] = user.last_activity
            user_dict["generation_count"] = user.generation_count or 0
            user_dict["checkin_count"] = user.checkin_count or 0
            
            # Add contribution stats
            user_dict["total_contributions"] = int(user.total_contributions or 0)
            user_dict["approved_contributions"] = int(user.approved_contributions or 0)
            # Add channel_joined (using new column)
            user_dict["channel_joined"] = bool(user.is_channel_member) if hasattr(user, "is_channel_member") else False
            
            # Add inviter info
            if user.inviter_user:
                user_dict["inviter_info"] = {
                    "id": user.inviter_user.id,
                    "username": user.inviter_user.username,
                    "full_name": user.inviter_user.full_name
                }
            else:
                user_dict["inviter_info"] = None
                
            users_with_counts.append(user_dict)
            
        return users_with_counts
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history/all", response_model=HistoryListResponse)
async def get_all_history(page: int = 1, page_size: int = 20, type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Get all history with pagination and optional type filter"""
    try:
        offset = (page - 1) * page_size
        
        # Base query for count with join to match stmt
        count_stmt = (
            select(func.count(History.id))
            .join(User, History.user_id == User.id)
        )
        
        # Get items with user info
        stmt = (
            select(History, User.username, User.full_name)
            .join(User, History.user_id == User.id)
            .order_by(desc(History.created_at))
        )

        # Apply type filter if provided
        if type and type != "all":
            count_stmt = count_stmt.where(History.type == type)
            stmt = stmt.where(History.type == type)
        
        # Count total
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # Apply pagination
        stmt = stmt.offset(offset).limit(page_size)
        result = await db.execute(stmt)
        
        items = []
        for row in result:
            history = row[0]
            username = row[1]
            full_name = row[2]
            
            # Convert SQLAlchemy model to dict and add user info
            item_dict = {c.name: getattr(history, c.name) for c in history.__table__.columns}
            item_dict["username"] = username
            item_dict["full_name"] = full_name
            
            # Handle input files
            if history.input_file:
                urls = []
                for f in history.input_file.split('|'):
                    if f.startswith('template:'):
                        # Handle template files: template:quick_face/filename.png
                        # Remove prefix
                        template_path = f[9:]
                        # Template paths in DB might be full paths or relative
                        # Usually it is relative like "quick_face/filename.png"
                        # We need to get presigned URL from template bucket
                        urls.append(storage.get_presigned_url(template_path, bucket=MINIO_TEMPLATE_BUCKET))
                    else:
                        basename = os.path.basename(f.replace('\\', '/'))
                        obj_name = f"{history.user_id}/input_images/{basename}"
                        urls.append(storage.get_presigned_url(obj_name))
                item_dict['input_file_url'] = '|'.join(urls)
                
            if history.output_file:
                basename = os.path.basename(history.output_file)
                obj_name = f"{history.user_id}/output_images/{basename}"
                item_dict['output_file_url'] = storage.get_presigned_url(obj_name)
            
            items.append(item_dict)
            
        return {"items": items, "total": total}
    except Exception as e:
        logger.error(f"Error getting all history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history/{user_id}", response_model=List[HistoryResponse])
async def get_user_history(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get history for a specific user"""
    try:
        stmt = select(History).where(History.user_id == user_id).order_by(desc(History.created_at)).limit(100)
        result = await db.execute(stmt)
        history = result.scalars().all()
        
        # Convert to dict and add presigned URLs
        items = []
        for h in history:
            item_dict = {c.name: getattr(h, c.name) for c in h.__table__.columns}
            
            # Handle input files (could be multiple separated by '|')
            if h.input_file:
                urls = []
                for f in h.input_file.split('|'):
                    if f.startswith('template:'):
                        template_path = f[9:]
                        urls.append(storage.get_presigned_url(template_path, bucket=MINIO_TEMPLATE_BUCKET))
                    else:
                        basename = os.path.basename(f.replace('\\', '/'))
                        obj_name = f"{h.user_id}/input_images/{basename}"
                        urls.append(storage.get_presigned_url(obj_name))
                item_dict['input_file_url'] = '|'.join(urls)
                
            if h.output_file:
                basename = os.path.basename(h.output_file)
                # Same logic for output
                obj_name = f"{h.user_id}/output_images/{basename}"
                item_dict['output_file_url'] = storage.get_presigned_url(obj_name)
                
            items.append(item_dict)
            
        return items
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a user and all their associated data from the database"""
    try:
        # Check if user exists
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Due to relationships and foreign keys, we need to delete associated data
        # CheckinHistory, History, Referral, TemplateContribution, Conversation, SessionState
        
        # 1. Delete CheckinHistory
        from src.database.models import CheckinHistory, Referral, SessionState, Conversation
        from sqlalchemy import delete
        
        await db.execute(delete(CheckinHistory).where(CheckinHistory.user_id == user_id))
        
        # 2. Delete History
        await db.execute(delete(History).where(History.user_id == user_id))
        
        # 3. Delete Referrals (where user is either inviter or invitee)
        await db.execute(delete(Referral).where((Referral.inviter_id == user_id) | (Referral.invitee_id == user_id)))
        
        # 4. Delete TemplateContributions
        await db.execute(delete(TemplateContribution).where(TemplateContribution.user_id == user_id))
        
        # 5. Delete Conversations
        await db.execute(delete(Conversation).where(Conversation.user_id == user_id))
        
        # 6. Delete SessionState
        await db.execute(delete(SessionState).where(SessionState.user_id == user_id))
        
        # 8. Finally delete the user
        await db.delete(user)
        
        await db.commit()
        return {"message": f"User {user_id} and all associated data deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/users/{user_id}/credits")
async def update_user_credits(user_id: int, request: UpdateCreditsRequest, db: AsyncSession = Depends(get_db)):
    """Update user credits"""
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        user.credits = request.credits
        await db.commit()
        return {"status": "ok", "credits": user.credits}
    except Exception as e:
        logger.error(f"Error updating credits: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/users/{user_id}/history")
async def clear_user_history(user_id: int, db: AsyncSession = Depends(get_db)):
    """Clear user history (database records and files)"""
    try:
        # 1. Get all history records to find file paths
        stmt = select(History).where(History.user_id == user_id)
        result = await db.execute(stmt)
        history_records = result.scalars().all()
        
        # 2. Delete physical files from MinIO
        for record in history_records:
            if record.input_file:
                for f in record.input_file.split('|'):
                    basename = os.path.basename(f)
                    obj_name = f"{user_id}/input_images/{basename}"
                    try:
                        storage.client.remove_object("bot-data", obj_name)
                    except Exception as fe:
                        logger.warning(f"Failed to delete input file {obj_name}: {fe}")
            
            if record.output_file:
                basename = os.path.basename(record.output_file)
                obj_name = f"{user_id}/output_images/{basename}"
                try:
                    storage.client.remove_object("bot-data", obj_name)
                except Exception as fe:
                    logger.warning(f"Failed to delete output file {obj_name}: {fe}")
        
        # 3. Delete database records
        from sqlalchemy import delete
        await db.execute(delete(History).where(History.user_id == user_id))
        
        # 4. Reset user stats
        user_stmt = select(User).where(User.id == user_id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if user:
            user.generation_count = 0
            user.last_activity = None

        await db.commit()
        
        return {"status": "ok", "message": f"Cleared history for user {user_id}"}
    except Exception as e:
        logger.error(f"Error clearing history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status")
async def get_system_status():
    """Check status of ComfyUI backend"""
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(STATUS_ENDPOINT, timeout=5.0)
            return {"comfyui": "online" if response.status_code == 200 else "error", "details": response.json() if response.status_code == 200 else str(response.status_code)}
    except Exception as e:
        return {"comfyui": "offline", "error": str(e)}

# --- Template Contribution Management ---

@app.get("/api/templates/contributions", response_model=List[TemplateContributionResponse])
async def get_template_contributions(db: AsyncSession = Depends(get_db)):
    """Get all template contributions with user info"""
    try:
        stmt = (
            select(TemplateContribution, User.username, User.full_name)
            .join(User, TemplateContribution.user_id == User.id)
            .order_by(desc(TemplateContribution.created_at))
        )
        result = await db.execute(stmt)
        
        contributions = []
        for row in result:
            contribution = row[0]
            username = row[1]
            full_name = row[2]
            
            # Create response object
            # Handle both Windows and Linux paths
            filename = os.path.basename(contribution.file_path.replace('\\', '/'))
            
            # Determine preview URL based on review status
            # Now we use MinIO presigned URL
            if contribution.is_reviewed:
                if contribution.file_type == 'video':
                    obj_name = f"video_nice/{filename}"
                else:
                    obj_name = f"quick_face/{filename}"
                preview_url = storage.get_presigned_url(obj_name, bucket=MINIO_TEMPLATE_BUCKET)
            else:
                # Unreviewed templates are also in MINIO_TEMPLATE_BUCKET, but in 'temps/' directory
                obj_name = f"temps/{filename}"
                preview_url = storage.get_presigned_url(obj_name, bucket=MINIO_TEMPLATE_BUCKET)

            res = TemplateContributionResponse(
                id=contribution.id,
                user_id=contribution.user_id,
                username=username,
                full_name=full_name,
                file_path=contribution.file_path,
                file_type=contribution.file_type or "photo",
                is_reviewed=contribution.is_reviewed,
                created_at=contribution.created_at,
                preview_url=preview_url
            )
            contributions.append(res)
            
        return contributions
    except Exception as e:
        logger.error(f"Error getting contributions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/templates/contributions/{contribution_id}/approve")
async def approve_contribution(contribution_id: int, db: AsyncSession = Depends(get_db)):
    """Approve a contribution: move in MinIO and mark as reviewed"""
    try:
        stmt = select(TemplateContribution).where(TemplateContribution.id == contribution_id)
        result = await db.execute(stmt)
        contribution = result.scalar_one_or_none()
        
        if not contribution:
            raise HTTPException(status_code=404, detail="Contribution not found")
            
        filename = os.path.basename(contribution.file_path.replace('\\', '/'))
        source_obj = f"temps/{filename}"
        
        # Target path: video_nice or quick_face (no templates/ prefix)
        if contribution.file_type == 'video':
            target_obj = f"video_nice/{filename}"
        else:
            target_obj = f"quick_face/{filename}"
            
        # Move object in MinIO (Copy then Remove)
        # Both source and target are in MINIO_TEMPLATE_BUCKET now
        try:
            from minio.commonconfig import CopySource
            # Storage client's raw minio client
            storage.client.copy_object(
                MINIO_TEMPLATE_BUCKET,
                target_obj,
                CopySource(MINIO_TEMPLATE_BUCKET, source_obj)
            )
            storage.client.remove_object(MINIO_TEMPLATE_BUCKET, source_obj)
        except Exception as se:
            logger.warning(f"Failed to move in MinIO: {se}")
        
        # Update database
        contribution.is_reviewed = True
        contribution.file_path = str(target_obj) # Update to new path
        
        # Award credits to the user (20 for video, 10 for photo) and increment approval count
        reward_amount = 20 if contribution.file_type == 'video' else 10
        user_stmt = select(User).where(User.id == contribution.user_id)
        user_result = await db.execute(user_stmt)
        user = user_result.scalar_one_or_none()
        if user:
            user.credits += reward_amount
            user.approved_contributions = (user.approved_contributions or 0) + 1
            
        await db.commit()
        
        return {"status": "ok", "message": f"Contribution approved, moved to template library, and {reward_amount} credits awarded"}
    except Exception as e:
        logger.error(f"Error approving contribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/templates/contributions/{contribution_id}")
async def delete_contribution(contribution_id: int, db: AsyncSession = Depends(get_db)):
    """Reject/Delete a contribution: delete from MinIO and database record"""
    try:
        stmt = select(TemplateContribution).where(TemplateContribution.id == contribution_id)
        result = await db.execute(stmt)
        contribution = result.scalar_one_or_none()
        
        if not contribution:
            raise HTTPException(status_code=404, detail="Contribution not found")
            
        # Delete from MinIO
        filename = os.path.basename(contribution.file_path.replace('\\', '/'))
        bucket = MINIO_TEMPLATE_BUCKET
        
        if contribution.is_reviewed:
            obj_name = f"video_nice/{filename}" if contribution.file_type == 'video' else f"quick_face/{filename}"
        else:
            obj_name = f"temps/{filename}"
            
        try:
            storage.client.remove_object(bucket, obj_name)
        except Exception as se:
            logger.warning(f"Failed to delete from MinIO: {se}")
            
        # Delete from DB
        from sqlalchemy import delete
        await db.execute(delete(TemplateContribution).where(TemplateContribution.id == contribution_id))
        await db.commit()
        
        return {"status": "ok", "message": "Contribution deleted"}
    except Exception as e:
        logger.error(f"Error deleting contribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system/status")
async def get_system_status_proxy():
    """Proxy system status request to ComfyUI Middleware"""
    try:
        url = f"{API_BASE}/system/status"
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                return response.json()
            else:
                # Fallback or error
                return {
                    "queue_size": 0,
                    "queue_by_type": {},
                    "active_workers": 0,
                    "comfy_online": False,
                    "error": f"Middleware returned {response.status_code}"
                }
    except Exception as e:
        logger.error(f"Error proxying system status: {e}")
        return {
            "queue_size": 0,
            "queue_by_type": {},
            "active_workers": 0,
            "comfy_online": False,
            "error": str(e)
        }

@app.get("/api/status/{task_id}")
async def get_task_status_proxy(task_id: str):
    """Proxy task status request to ComfyUI Middleware"""
    try:
        url = f"{API_BASE}/status/{task_id}"
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail="Task not found or error")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/image/{task_id}")
async def get_task_image_proxy(task_id: str):
    """Proxy image download request to ComfyUI Middleware"""
    try:
        url = f"{API_BASE}/image/{task_id}"
        
        client = httpx.AsyncClient(trust_env=False)
        req = client.build_request("GET", url, timeout=30.0)
        r = await client.send(req, stream=True)
        
        if r.status_code != 200:
            await r.aclose()
            await client.aclose()
            raise HTTPException(status_code=r.status_code, detail="Image not found")
            
        async def iter_file():
            try:
                async for chunk in r.aiter_bytes():
                    yield chunk
            finally:
                await r.aclose()
                await client.aclose()

        return StreamingResponse(
            iter_file(),
            media_type=r.headers.get("content-type")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying image: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/video/{task_id}")
async def get_task_video_proxy(task_id: str):
    """Proxy video download request to ComfyUI Middleware"""
    try:
        url = f"{API_BASE}/video/{task_id}"
        
        client = httpx.AsyncClient(trust_env=False)
        req = client.build_request("GET", url, timeout=60.0)
        r = await client.send(req, stream=True)
        
        if r.status_code != 200:
            await r.aclose()
            await client.aclose()
            raise HTTPException(status_code=r.status_code, detail="Video not found")

        async def iter_file():
            try:
                async for chunk in r.aiter_bytes():
                    yield chunk
            finally:
                await r.aclose()
                await client.aclose()

        return StreamingResponse(
            iter_file(),
            media_type=r.headers.get("content-type")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8043)
