async def resolve_internal_user_id(user_id: int, username: str) -> int:
    from src.core import user_core

    internal_user, _ = await user_core.get_or_create_user_by_telegram(
        user_id, username
    )
    return internal_user.id
