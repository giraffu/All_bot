import os
import logging
import base64
import httpx
import time
from collections import defaultdict
from dotenv import load_dotenv
from telegram import Update, File
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from langgraph_client import get_langgraph_reply, check_intent
from db import init_db, save_message

import re

# ==========================================
# 缓存系统：记录群组内最近发送的图片 (chat_id -> {user_id -> {"file_id": xxx, "timestamp": xxx}})
# 用于实现：用户先发图，然后再发文字问“咒语是什么”
# ==========================================
recent_photos_cache = defaultdict(dict)
PHOTO_CACHE_EXPIRE = 60 * 5  # 图片缓存过期时间 (5分钟)

def update_photo_cache(chat_id: int, user_id: int, file_id: str):
    recent_photos_cache[chat_id][user_id] = {
        "file_id": file_id,
        "timestamp": time.time()
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
original_download_to_drive = File.download_to_drive

async def custom_download_as_bytearray(self, out=None, custom_path=None, read_timeout=120.0, *args, **kwargs):
    """自定义下载逻辑，强制使用直连并修正 URL"""
    try:
        # 获取原始文件路径 (例如: /var/lib/telegram-bot-api/...)
        raw_path = self.file_path
        if raw_path.startswith("http"):
            # 如果 PTB 已经错误地拼接了 URL，我们提取出它的真实路径
            import urllib.parse
            parsed = urllib.parse.urlparse(raw_path)
            raw_path = parsed.path
            
        # 修正拼接：强制指向 8082 端口
        fixed_url = f"http://69.63.220.115:8082{raw_path}"
        # 处理 bot token 被错误拼接的情况
        if f"8082bot{BOT_TOKEN}/" in fixed_url:
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
# 支持多个群组 ID，逗号分隔解析为整数列表
allowed_groups_str = os.getenv("ALLOWED_GROUP_IDS", "")
ALLOWED_GROUP_IDS = [int(gid.strip()) for gid in allowed_groups_str.split(",")] if allowed_groups_str else []

# 代理配置
PROXY_URL = os.getenv("PROXY_URL")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    chat_type = update.message.chat.type
    if chat_type in ['group', 'supergroup']:
        await update.message.reply_text("师弟师妹们好呀~ 我是负责帮大家解惑的大师姐！修行（使用）上有什么不懂的，都可以直接问我哦~")
    else:
        await update.message.reply_text("哎呀，大师姐现在要在群里招待其他同门呢，私聊我就先不回啦~ 去群组里找我玩吧！")

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    处理群组消息的核心逻辑：
    1. 拦截私聊
    2. 只响应被 @ 或者直接回复的消息
    3. 调用 LLM 获取并返回答案（支持文本和图片）
    """
    message = update.message
    if not message:
        return
    
    # 获取文本内容：可能是纯文本，也可能是图片的 caption
    raw_text = message.text or message.caption or ""
    has_photo = bool(message.photo)
    
    chat_type = message.chat.type
    # 核心拦截 1：只处理专属群组消息
    chat_id = message.chat_id
    
    user_id = message.from_user.id
    username = message.from_user.first_name or "未知弟子"

    if has_photo:
        # 用户发了图片，无论是否有文字，都先更新到缓存中（备用）
        update_photo_cache(chat_id, user_id, message.photo[-1].file_id)

    if not raw_text and not has_photo:
        return

    if chat_type not in ['group', 'supergroup']:
        await message.reply_text("师弟，大师姐这会儿正忙着呢，有什么问题去群里大家一起讨论呀~")
        return

    if ALLOWED_GROUP_IDS and chat_id not in ALLOWED_GROUP_IDS:
        logging.info(f"忽略非专属群组消息: {chat_id}")
        return

    # 核心判断 2：触发大师姐回复的条件
    bot_username = context.bot.username
    
    # 检查用户是否在询问反推咒语
    # 触发词汇：咒语、提示词、反推、焚诀、焚决、prompt 等
    is_asking_prompt = bool(re.search(r"(咒语|提示词|反推|焚诀|焚决|prompt)", raw_text, re.IGNORECASE))
    
    # 如果回复了某条包含图片的消息，也将其纳入考虑
    reply_photo_file_id = None
    if message.reply_to_message and message.reply_to_message.photo:
        reply_photo_file_id = message.reply_to_message.photo[-1].file_id

    is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id
    is_mentioned = f"@{bot_username}" in raw_text

    # 新增规则：使用大模型进行“意图识别”
    # 如果没有被 @，也没有被直接回复，调用本地 LLM 判断是否属于求助
    is_help_seeking = False
    
    # 纯净的文本内容，用于意图识别和传递给大模型
    user_text = raw_text.replace(f"@{bot_username}", "").strip()

    # 1. 明确的交互 (被 @ 或回复了 Bot)
    if is_mentioned or is_reply_to_bot:
        is_help_seeking = True
        
    # 2. 用户在索要咒语
    elif is_asking_prompt:
        if has_photo or reply_photo_file_id or get_cached_photo(chat_id, user_id):
            # 有图并且要咒语，直接触发
            is_help_seeking = True
            logging.info("收到图片并请求反推咒语，触发视觉大模型")
            
    # 3. 超过3个字的纯文本，使用大模型嗅探意图
    elif not has_photo and len(user_text) > 3:
        is_help_seeking = await check_intent(user_text)
        if is_help_seeking:
            logging.info(f"意图识别命中！用户正在求助: {user_text}")

    # 如果没有任何意图被命中，直接返回（静默记录器依然会工作）
    if not is_help_seeking:
        return

    # === 以下为确认需要回复的逻辑 ===
    if not user_text and not has_photo:
        user_text = "师姐，我需要帮忙~"

    # 发送“正在输入”状态（让群友觉得是真人在思考）
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    
    # 确定要发送给大模型的图片 file_id
    target_file_id = None
    if has_photo and (is_asking_prompt or is_mentioned or is_reply_to_bot):
        target_file_id = message.photo[-1].file_id
    elif is_asking_prompt and reply_photo_file_id:
        target_file_id = reply_photo_file_id
    elif is_asking_prompt and get_cached_photo(chat_id, user_id):
        target_file_id = get_cached_photo(chat_id, user_id)

    # 提取图片并转 Base64
    base64_image = None
    if target_file_id:
        try:
            # 获取最大分辨率的图片
            photo_file = await context.bot.get_file(target_file_id)
            # 下载到内存
            file_bytes = await photo_file.download_as_bytearray()
            # 转为 Base64
            base64_image = base64.b64encode(file_bytes).decode('utf-8')
        except Exception as e:
            logging.error(f"下载或转换图片失败: {e}")
            await message.reply_text("师弟，这张图的灵力波动太强，我没看清，能再发一次吗？")
            return

    # 核心调用 3：向 LangGraph 获取 LLM 智能回复，附带上下文记忆和可能存在的图片
    reply_text = await get_langgraph_reply(chat_id, username, user_text, base64_image)

    # 核心返回 4：引用用户的原消息进行回复
    await message.reply_text(reply_text, reply_to_message_id=message.message_id)

async def silent_logger_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    静默记录群组所有消息
    """
    message = update.message
    if not message:
        return
        
    chat_type = message.chat.type
    chat_id = message.chat_id
    
    # 仅记录指定群组的消息
    if ALLOWED_GROUP_IDS and chat_id not in ALLOWED_GROUP_IDS:
        return

    logging.info(f"收到静默日志记录请求: chat_id={chat_id}, msg_id={message.message_id}")

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
        has_url = any(e.type in ['url', 'text_link'] for e in entities)
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
        raw_data=raw_data
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
    builder = builder.base_url("http://69.63.220.115:8081/bot")
    builder = builder.base_file_url("http://69.63.220.115:8082")
    logging.info("已配置使用 Telegram Local API 服务器 (69.63.220.115)")
    
    # 如果配置了代理，则注入代理配置 (备用)
    if PROXY_URL:
        logging.info(f"正在使用代理连接 Telegram: {PROXY_URL}")
        # Telegram API 官方要求使用 httpx 作为请求引擎
        # 并配置合理的超时时间（大模型回复可能较慢）
        request = HTTPXRequest(
            proxy=PROXY_URL,
            connect_timeout=30.0,
            read_timeout=60.0
        )
        builder = builder.request(request)
    else:
        logging.warning("未配置 PROXY_URL。如果您的服务器在国内，可能会报错 telegram.error.TimedOut")
        # 即使没有代理，也稍微增加一点超时时间
        request = HTTPXRequest(
            connect_timeout=30.0,
            read_timeout=60.0
        )
        builder = builder.request(request)

    application = builder.build()

    # 注册 /start 命令
    application.add_handler(CommandHandler("start", start))
    
    # 监听文本和图片消息，交给 handle_group_message 过滤，用于 LLM 回复
    application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_group_message), group=0)

    # 在 group=1 注册静默记录器，监听所有类型的消息
    application.add_handler(MessageHandler(filters.ALL, silent_logger_handler), group=1)

    logging.info("客服长老 Bot 已启动，正在静静监听群组消息...")
    # 启动轮询 (生产环境中，您也可以配置 Webhook)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
