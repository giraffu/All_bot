import base64
import logging
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import httpx
from db import init_db, save_message
from dotenv import load_dotenv
from langgraph_client import check_intent, get_langgraph_reply
from telegram import File, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

# ==========================================
# 缓存系统：记录群组内最近发送的图片 (chat_id -> {user_id -> {"file_id": xxx, "timestamp": xxx}})
# 用于实现：用户先发图，然后再发文字问“咒语是什么”
# ==========================================
recent_photos_cache = defaultdict(dict)
PHOTO_CACHE_EXPIRE = 60 * 5  # 图片缓存过期时间 (5分钟)


def update_photo_cache(chat_id: int, user_id: int, file_id: str):
    recent_photos_cache[chat_id][user_id] = {
        "file_id": file_id,
        "timestamp": time.time(),
    }


def get_cached_photo(chat_id: int, user_id: int) -> str:
    user_cache = recent_photos_cache.get(chat_id, {}).get(user_id)
    if user_cache:
        if time.time() - user_cache["timestamp"] <= PHOTO_CACHE_EXPIRE:
            return user_cache["file_id"]
    return None


# ==========================================
# 猴子补丁 (Monkey Patch): 修复 PTB 自定义文件服务器路径拼接 Bug
# 避免 url 变成 http://ip:8082bot<token>/var/lib/...
# ==========================================
async def custom_download_as_bytearray(
    self, _out=None, custom_path=None, read_timeout=120.0, *args, **kwargs
):
    """自定义下载逻辑，强制使用直连并修正 URL"""
    try:
        # 获取原始文件路径 (例如: /var/lib/telegram-bot-api/...)
        raw_path = self.file_path
        if raw_path.startswith("http"):
            # 如果 PTB 已经错误地拼接了 URL，我们提取出它的真实路径
            import urllib.parse

            parsed = urllib.parse.urlparse(raw_path)
            raw_path = parsed.path

        fixed_url = _build_local_file_url(raw_path)
        # 处理 bot token 被错误拼接的情况
        if f"{TELEGRAM_LOCAL_FILE_BASE_URL}/bot{BOT_TOKEN}/" in fixed_url:
            fixed_url = fixed_url.replace(f"bot{BOT_TOKEN}/", "")
        if f"{TELEGRAM_LOCAL_FILE_BASE_URL}bot{BOT_TOKEN}/" in fixed_url:
            fixed_url = fixed_url.replace(f"bot{BOT_TOKEN}/", "")

        logging.info(f"正在从 Local API Server 下载文件: {fixed_url}")

        # 强制直连，绕过代理
        async with httpx.AsyncClient(proxy=None, timeout=read_timeout) as client:
            response = await client.get(fixed_url)
            response.raise_for_status()
            return bytearray(response.content)

    except Exception as e:
        logging.error(f"自定义下载文件失败: {e}")
        raise e


# 替换原生方法
File.download_as_bytearray = custom_download_as_bytearray


# 配置日志
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# 加载环境变量
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_LOCAL_BOT_API_BASE_URL = os.getenv(
    "TELEGRAM_LOCAL_BOT_API_BASE_URL",
    "http://69.63.220.115:8081/bot",
).rstrip("/")
TELEGRAM_LOCAL_FILE_BASE_URL = os.getenv(
    "TELEGRAM_LOCAL_FILE_BASE_URL",
    "http://69.63.220.115:8082",
).rstrip("/")
# 支持多个群组 ID，逗号分隔解析为整数列表
allowed_groups_str = os.getenv("ALLOWED_GROUP_IDS", "")
ALLOWED_GROUP_IDS = (
    [int(gid.strip()) for gid in allowed_groups_str.split(",")]
    if allowed_groups_str
    else []
)

# 代理配置
PROXY_URL = os.getenv("PROXY_URL")


def _normalize_local_bot_api_base_url(raw_url: str) -> str:
    normalized = str(raw_url or "").strip().rstrip("/")
    if not normalized:
        return ""
    return normalized if normalized.endswith("/bot") else f"{normalized}/bot"


def _build_local_file_url(raw_path: str) -> str:
    path = str(raw_path or "")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{TELEGRAM_LOCAL_FILE_BASE_URL}{path}"


@dataclass(frozen=True)
class GroupMessageContext:
    message: Any
    raw_text: str
    has_photo: bool
    chat_type: str
    chat_id: int
    user_id: int
    username: str
    bot_username: str
    user_text: str
    is_asking_prompt: bool
    is_reply_to_bot: bool
    is_mentioned: bool
    reply_photo_file_id: str | None


def _build_group_message_context(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> GroupMessageContext | None:
    message = update.message
    if not message:
        return None

    raw_text = message.text or message.caption or ""
    has_photo = bool(message.photo)
    from_user = message.from_user
    user_id = from_user.id if from_user else 0
    username = (from_user.first_name if from_user else None) or "未知弟子"
    bot_username = context.bot.username
    reply_to_message = message.reply_to_message
    reply_from_user = getattr(reply_to_message, "from_user", None)
    reply_photo_file_id = (
        reply_to_message.photo[-1].file_id
        if reply_to_message and reply_to_message.photo
        else None
    )

    return GroupMessageContext(
        message=message,
        raw_text=raw_text,
        has_photo=has_photo,
        chat_type=message.chat.type,
        chat_id=message.chat_id,
        user_id=user_id,
        username=username,
        bot_username=bot_username,
        user_text=raw_text.replace(f"@{bot_username}", "").strip(),
        is_asking_prompt=bool(
            re.search(r"(咒语|提示词|反推|焚诀|焚决|prompt)", raw_text, re.IGNORECASE)
        ),
        is_reply_to_bot=bool(
            reply_from_user and reply_from_user.id == context.bot.id
        ),
        is_mentioned=f"@{bot_username}" in raw_text,
        reply_photo_file_id=reply_photo_file_id,
    )


async def _should_skip_group_message(env: GroupMessageContext) -> bool:
    if env.has_photo:
        update_photo_cache(env.chat_id, env.user_id, env.message.photo[-1].file_id)

    if not env.raw_text and not env.has_photo:
        return True

    if env.chat_type not in ["group", "supergroup"]:
        await env.message.reply_text(
            "师弟，大师姐这会儿正忙着呢，有什么问题去群里大家一起讨论呀~"
        )
        return True

    if ALLOWED_GROUP_IDS and env.chat_id not in ALLOWED_GROUP_IDS:
        logging.info(f"忽略非专属群组消息: {env.chat_id}")
        return True

    return False


async def _is_help_seeking_message(env: GroupMessageContext) -> bool:
    if env.is_mentioned or env.is_reply_to_bot:
        return True

    if env.is_asking_prompt:
        if (
            env.has_photo
            or env.reply_photo_file_id
            or get_cached_photo(env.chat_id, env.user_id)
        ):
            logging.info("收到图片并请求反推咒语，触发视觉大模型")
            return True
        return False

    if not env.has_photo and len(env.user_text) > 3:
        is_help_seeking = await check_intent(env.user_text)
        if is_help_seeking:
            logging.info(f"意图识别命中！用户正在求助: {env.user_text}")
        return is_help_seeking

    return False


def _resolve_target_photo_file_id(env: GroupMessageContext) -> str | None:
    if env.has_photo and (
        env.is_asking_prompt or env.is_mentioned or env.is_reply_to_bot
    ):
        return env.message.photo[-1].file_id
    if env.is_asking_prompt and env.reply_photo_file_id:
        return env.reply_photo_file_id
    if env.is_asking_prompt:
        return get_cached_photo(env.chat_id, env.user_id)
    return None


async def _download_photo_as_base64(
    *,
    bot,
    file_id: str | None,
) -> str | None:
    if not file_id:
        return None
    photo_file = await bot.get_file(file_id)
    file_bytes = await photo_file.download_as_bytearray()
    return base64.b64encode(file_bytes).decode("utf-8")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    chat_type = update.message.chat.type
    if chat_type in ["group", "supergroup"]:
        await update.message.reply_text(
            "师弟师妹们好呀~ 我是负责帮大家解惑的大师姐！修行（使用）上有什么不懂的，都可以直接问我哦~"
        )
    else:
        await update.message.reply_text(
            "哎呀，大师姐现在要在群里招待其他同门呢，私聊我就先不回啦~ 去群组里找我玩吧！"
        )


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    处理群组消息的核心逻辑：
    1. 拦截私聊
    2. 只响应被 @ 或者直接回复的消息
    3. 调用 LLM 获取并返回答案（支持文本和图片）
    """
    env = _build_group_message_context(update, context)
    if env is None or await _should_skip_group_message(env):
        return

    if not await _is_help_seeking_message(env):
        return

    user_text = env.user_text
    if not user_text and not env.has_photo:
        user_text = "师姐，我需要帮忙~"

    await context.bot.send_chat_action(chat_id=env.chat_id, action="typing")

    try:
        base64_image = await _download_photo_as_base64(
            bot=context.bot,
            file_id=_resolve_target_photo_file_id(env),
        )
    except Exception as e:
        logging.error(f"下载或转换图片失败: {e}")
        await env.message.reply_text(
            "师弟，这张图的灵力波动太强，我没看清，能再发一次吗？"
        )
        return

    # 核心调用 3：向 LangGraph 获取 LLM 智能回复，附带上下文记忆和可能存在的图片
    reply_text = await get_langgraph_reply(
        env.chat_id,
        env.username,
        user_text,
        base64_image,
    )

    # 核心返回 4：引用用户的原消息进行回复
    await env.message.reply_text(reply_text, reply_to_message_id=env.message.message_id)


async def silent_logger_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    静默记录群组所有消息
    """
    message = update.message
    if not message:
        return

    chat_id = message.chat_id

    # 仅记录指定群组的消息
    if ALLOWED_GROUP_IDS and chat_id not in ALLOWED_GROUP_IDS:
        return

    logging.info(
        f"收到静默日志记录请求: chat_id={chat_id}, msg_id={message.message_id}"
    )

    user = message.from_user
    if user:
        user_id = user.id
        username = user.first_name or "未知弟子"
        if user.username:
            username += f" (@{user.username})"
    else:
        user_id = 0
        username = "系统/频道"

    message_id = message.message_id

    message_type = "unknown"
    content = ""
    media_file_id = ""
    raw_data = message.to_dict()

    if message.text:
        message_type = "text"
        content = message.text
    elif message.photo:
        message_type = "photo"
        content = message.caption or ""
        media_file_id = message.photo[-1].file_id
    elif message.video:
        message_type = "video"
        content = message.caption or ""
        media_file_id = message.video.file_id
    elif message.document:
        message_type = "document"
        content = message.caption or ""
        media_file_id = message.document.file_id
    elif message.animation:
        message_type = "animation"
        content = message.caption or ""
        media_file_id = message.animation.file_id
    elif message.sticker:
        message_type = "sticker"
        content = message.caption or ""
        media_file_id = message.sticker.file_id

    # 处理包含链接的消息
    if message.entities or message.caption_entities:
        entities = message.entities or message.caption_entities
        has_url = any(e.type in ["url", "text_link"] for e in entities)
        if has_url:
            message_type = f"{message_type}_with_link"

    await save_message(
        chat_id=chat_id,
        message_id=message_id,
        user_id=user_id,
        username=username,
        message_type=message_type,
        content=content,
        media_file_id=media_file_id,
        raw_data=raw_data,
    )


async def post_init(application: Application):
    """初始化时调用"""
    await init_db()


def main():
    if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        logging.error("请先在 .env 文件中配置真实的 BOT_TOKEN！")
        return

    # 初始化应用
    builder = Application.builder().token(BOT_TOKEN).post_init(post_init)

    # 强制使用您的 Telegram Local API 服务器，以解决国内连不上的问题
    # 这和您的 tg-bot 主项目保持一致
    builder = builder.base_url(
        _normalize_local_bot_api_base_url(TELEGRAM_LOCAL_BOT_API_BASE_URL)
    )
    builder = builder.base_file_url(TELEGRAM_LOCAL_FILE_BASE_URL)
    logging.info(
        "已配置使用 Telegram Local API 服务器: bot_api=%s, file_api=%s",
        _normalize_local_bot_api_base_url(TELEGRAM_LOCAL_BOT_API_BASE_URL),
        TELEGRAM_LOCAL_FILE_BASE_URL,
    )

    # 如果配置了代理，则注入代理配置 (备用)
    if PROXY_URL:
        logging.info(f"正在使用代理连接 Telegram: {PROXY_URL}")
        # Telegram API 官方要求使用 httpx 作为请求引擎
        # 并配置合理的超时时间（大模型回复可能较慢）
        request = HTTPXRequest(proxy=PROXY_URL, connect_timeout=30.0, read_timeout=60.0)
        builder = builder.request(request)
    else:
        logging.warning(
            "未配置 PROXY_URL。如果您的服务器在国内，可能会报错 telegram.error.TimedOut"
        )
        # 即使没有代理，也稍微增加一点超时时间
        request = HTTPXRequest(connect_timeout=30.0, read_timeout=60.0)
        builder = builder.request(request)

    application = builder.build()

    # 注册 /start 命令
    application.add_handler(CommandHandler("start", start))

    # 监听文本和图片消息，交给 handle_group_message 过滤，用于 LLM 回复
    application.add_handler(
        MessageHandler(filters.TEXT | filters.PHOTO, handle_group_message), group=0
    )

    # 在 group=1 注册静默记录器，监听所有类型的消息
    application.add_handler(MessageHandler(filters.ALL, silent_logger_handler), group=1)

    logging.info("客服长老 Bot 已启动，正在静静监听群组消息...")
    # 启动轮询 (生产环境中，您也可以配置 Webhook)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
