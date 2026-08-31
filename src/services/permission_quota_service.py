from src.quota import QuotaManager


class PermissionQuotaService:
    def __init__(self, quota_manager: QuotaManager, resolve_task_cost_func=None):
        self.quota_manager = quota_manager
        self.resolve_task_cost_func = resolve_task_cost_func

    async def check_quota(
        self,
        tg_id: int,
        username: str,
        full_name: str,
        cost: int = 1,
        *,
        task_type: str | None = None,
        client_type: str = "bot",
    ) -> bool:
        from src.core.exceptions import InsufficientCreditsError
        from src.core.user_core import get_or_create_user_by_telegram

        if task_type:
            resolve_task_cost = self.resolve_task_cost_func
            if resolve_task_cost is None:
                from src.services.task_pricing_config_service import (
                    resolve_runtime_task_cost,
                )

                resolve_task_cost = resolve_runtime_task_cost
            cost = await resolve_task_cost(
                task_type=task_type,
                inputs={},
                client_type=client_type,
                default_cost=cost,
            )

        internal_user, _ = await get_or_create_user_by_telegram(
            tg_id, username, full_name
        )
        internal_user_id = internal_user.id

        if not await self.quota_manager.check_credits(internal_user_id, cost):
            current = await self.quota_manager.get_credits(
                internal_user_id, username=username, full_name=full_name
            )
            raise InsufficientCreditsError(current=current, cost=cost)

        return True

    async def increment_quota(
        self,
        user_id: int,
        credits: int = 1,
        username: str | None = None,
        task_type: str = "generation",
    ):
        if credits <= 0:
            raise ValueError("credits must be positive")

        await self.quota_manager.add_credits(
            user_id, credits, username=username, task_type=task_type
        )

    async def refund_quota(
        self,
        user_id: int,
        credits: int,
        username: str | None = None,
        task_type: str = "refund",
    ):
        if credits <= 0:
            return

        await self.increment_quota(
            user_id=user_id,
            credits=credits,
            username=username,
            task_type=task_type,
        )

    async def is_user_exists(self, user_id: int) -> bool:
        return await self.quota_manager.is_user_exists(user_id)

    async def get_user_credits(self, tg_id: int, username: str, full_name: str) -> int:
        from src.core.user_core import get_or_create_user_by_telegram

        internal_user, _ = await get_or_create_user_by_telegram(
            tg_id, username, full_name
        )
        return await self.quota_manager.get_credits(internal_user.id)
