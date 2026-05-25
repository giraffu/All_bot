from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LanguageToggleRuntimeResult:
    new_lang: str
    internal_user_id: int
    translator: Any
    reply_text: str
    reply_markup: Any


def normalize_supported_language_code(language_code: str | None) -> str:
    if not language_code:
        return "zh"
    normalized = language_code[:2]
    return normalized if normalized in {"zh", "en"} else "zh"


async def _read_cached_language_code(*, telegram_user_id: int, redis_client_obj) -> str | None:
    if not redis_client_obj or not redis_client_obj.redis:
        return None
    current_lang = await redis_client_obj.redis.get(f"allbot:user_lang:tg:{telegram_user_id}")
    if current_lang:
        return current_lang.decode("utf-8")
    return None


async def _persist_language_code(
    *,
    internal_user_id: int,
    telegram_user_id: int,
    new_lang: str,
    redis_client_obj,
) -> None:
    if not redis_client_obj or not redis_client_obj.redis:
        return
    await redis_client_obj.redis.set(f"allbot:user_lang:{internal_user_id}", new_lang)
    await redis_client_obj.redis.set(f"allbot:user_lang:tg:{telegram_user_id}", new_lang)


async def toggle_user_language_runtime(
    *,
    telegram_user,
    cached_language_code: str | None,
    redis_client_obj=None,
    get_or_create_user_by_telegram_func=None,
    session_factory=None,
    user_model=None,
    translator_factory=None,
    keyboard_builder=None,
    switch_message_builder=None,
) -> LanguageToggleRuntimeResult:
    if get_or_create_user_by_telegram_func is None:
        from src.core.user_core import get_or_create_user_by_telegram

        get_or_create_user_by_telegram_func = get_or_create_user_by_telegram
    if session_factory is None:
        from src.database.core import AsyncSessionLocal

        session_factory = AsyncSessionLocal
    if user_model is None:
        from src.database.models import User

        user_model = User
    if translator_factory is None:
        from src.i18n.translator import I18nTranslator

        translator_factory = I18nTranslator
    if keyboard_builder is None:
        from src.i18n.keyboards import get_main_menu_keyboard

        keyboard_builder = get_main_menu_keyboard
    if switch_message_builder is None:
        from src.handlers.message_handler_menu import build_switch_lang_message

        switch_message_builder = build_switch_lang_message
    if redis_client_obj is None:
        from src.services.redis_client import redis_client as _redis_client

        redis_client_obj = _redis_client

    current_lang = cached_language_code
    if not current_lang:
        current_lang = await _read_cached_language_code(
            telegram_user_id=telegram_user.id,
            redis_client_obj=redis_client_obj,
        )

    current_lang = normalize_supported_language_code(
        current_lang or getattr(telegram_user, "language_code", None)
    )
    new_lang = "en" if current_lang == "zh" else "zh"

    internal_user, _ = await get_or_create_user_by_telegram_func(
        telegram_user.id,
        telegram_user.username,
        telegram_user.full_name,
    )
    async with session_factory() as session:
        db_user = await session.get(user_model, internal_user.id)
        if db_user:
            db_user.language_code = new_lang
            await session.commit()

    await _persist_language_code(
        internal_user_id=internal_user.id,
        telegram_user_id=telegram_user.id,
        new_lang=new_lang,
        redis_client_obj=redis_client_obj,
    )
    return LanguageToggleRuntimeResult(
        new_lang=new_lang,
        internal_user_id=internal_user.id,
        translator=translator_factory(new_lang),
        reply_text=switch_message_builder(new_lang),
        reply_markup=keyboard_builder(new_lang),
    )
