# cspell: disable
import os
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dotenv import load_dotenv

load_dotenv()

BOT_TYPE = os.getenv("BOT_TYPE", "TEST").upper()


def _get_env_value(name: str, default: str | None = None) -> str | None:
    """Allow TEST mode to read *_TEST overrides without affecting prod."""
    if BOT_TYPE == "TEST":
        test_value = os.getenv(f"{name}_TEST")
        if test_value not in (None, ""):
            return test_value
    return os.getenv(name, default)

# --- Bot Configuration ---
TELEGRAM_API_BASE_URL = os.getenv("TELEGRAM_API_BASE_URL", "http://69.63.220.115:8081")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_TOKEN_TEST = os.getenv("BOT_TOKEN_TEST") or os.getenv("BOT_TOKEN_test")
FILE_BOT_TOKEN = os.getenv("FILE_BOT_TOKEN")

# --- Telethon Configuration ---
TELETHON_API_ID = os.getenv("TELETHON_API_ID")
TELETHON_API_HASH = os.getenv("TELETHON_API_HASH")
PHONE = os.getenv("PHONE")
PASSWORD = os.getenv("PASSWORD")
GROUP_ID = os.getenv("GROUP_ID")

# --- Proxy Configuration ---
# Default to empty if not set, let bot detect or use system proxy
PROXY_URL = os.getenv("PROXY_URL")

# TON Payment Configuration
VITE_MERCHANT_ADDRESS = _get_env_value(
    "VITE_MERCHANT_ADDRESS", "UQAluW2wxRCDsJIKGH59jB07xODgEbStdUPEj9AjI88d9l-s"
)
WEBAPP_URL = _get_env_value("WEBAPP_URL", "https://pay.aivison.it.com/")
MINI_APP_URL = _get_env_value("MINI_APP_URL", "https://web.aivison.it.com/")
MINI_APP_VERSION = _get_env_value("MINI_APP_VERSION")


def append_version_query(base_url: str, version: str | None = None) -> str:
    if not version:
        return base_url

    parsed = urlparse(base_url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items["v"] = version
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def build_versioned_mini_app_url(
    base_url: str | None = None,
    version: str | None = None,
) -> str:
    resolved_base_url = base_url or MINI_APP_URL or "https://web.aivison.it.com/"
    resolved_version = MINI_APP_VERSION if version is None else version
    return append_version_query(resolved_base_url, resolved_version)

# --- Database Configuration ---
# Only PostgreSQL is supported
DATABASE_URL = _get_env_value("DATABASE_URL")
if not DATABASE_URL or DATABASE_URL.startswith("sqlite"):
    # Fallback or error if not provided?
    # Better to default to a sensible Postgres URL or raise error.
    # For now, let's assume env var is set, or provide a default local PG
    DATABASE_URL = _get_env_value(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/bot_db"
    )

DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))

# --- MinIO Configuration ---
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "192.168.1.115:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "chuzeyu")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "@Cv1347968277")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "bot-data")
MINIO_RESULT_BUCKET = os.getenv("MINIO_RESULT_BUCKET", "comfyui-temp")
MINIO_TEMPLATE_BUCKET = os.getenv("MINIO_TEMPLATE_BUCKET", "bot-template")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_PUBLIC_URL = os.getenv("MINIO_PUBLIC_URL", f"http://{MINIO_ENDPOINT}")
IMGPROXY_URL = os.getenv("IMGPROXY_URL", "http://localhost:8080")

# --- Legacy object storage migration/rollback access ---
# Runtime Web/Dashboard reads keep this disabled by default. One-off migration
# scripts can enable it to copy historical objects from local MinIO into R2.
LEGACY_MINIO_ENDPOINT = os.getenv("LEGACY_MINIO_ENDPOINT")
LEGACY_MINIO_ACCESS_KEY = os.getenv("LEGACY_MINIO_ACCESS_KEY")
LEGACY_MINIO_SECRET_KEY = os.getenv("LEGACY_MINIO_SECRET_KEY")
LEGACY_MINIO_BUCKET = os.getenv("LEGACY_MINIO_BUCKET", "bot-data")
LEGACY_MINIO_RESULT_BUCKET = os.getenv(
    "LEGACY_MINIO_RESULT_BUCKET", "comfyui-temp"
)
LEGACY_MINIO_SECURE = os.getenv("LEGACY_MINIO_SECURE", "false").lower() == "true"
LEGACY_MINIO_PUBLIC_URL = os.getenv("LEGACY_MINIO_PUBLIC_URL", "")
LEGACY_MINIO_READ_FALLBACK_ENABLED = (
    os.getenv("LEGACY_MINIO_READ_FALLBACK_ENABLED", "false").lower() == "true"
)

# --- Cloudflare R2 Configuration ---
R2_ENDPOINT = os.getenv("R2_ENDPOINT")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET = os.getenv("R2_BUCKET", "user-data")
R2_PUBLIC_DOMAIN = os.getenv("R2_PUBLIC_DOMAIN")
R2_MAX_POOL_CONNECTIONS = int(os.getenv("R2_MAX_POOL_CONNECTIONS", "100"))
R2_EXISTS_POSITIVE_TTL_SECONDS = int(
    os.getenv("R2_EXISTS_POSITIVE_TTL_SECONDS", "60")
)
R2_EXISTS_NEGATIVE_TTL_SECONDS = int(
    os.getenv("R2_EXISTS_NEGATIVE_TTL_SECONDS", "5")
)
R2_EXISTS_CACHE_MAX_ENTRIES = int(os.getenv("R2_EXISTS_CACHE_MAX_ENTRIES", "5000"))
R2_HEAD_SEMAPHORE_LIMIT = int(os.getenv("R2_HEAD_SEMAPHORE_LIMIT", "32"))
R2_HEAD_CONNECT_TIMEOUT_SECONDS = float(
    os.getenv("R2_HEAD_CONNECT_TIMEOUT_SECONDS", "2")
)
R2_HEAD_READ_TIMEOUT_SECONDS = float(os.getenv("R2_HEAD_READ_TIMEOUT_SECONDS", "3"))
R2_HEAD_MAX_ATTEMPTS = int(os.getenv("R2_HEAD_MAX_ATTEMPTS", "1"))

# --- API Configuration ---
# Default to the backend server IP
API_BASE = _get_env_value("API_BASE", "http://127.0.0.1:8003")
API_TOKEN = _get_env_value("API_TOKEN", "your_secure_token_here")  # Added based on changelog

# Endpoints constructed from API_BASE
IMG2IMG_ENDPOINT = f"{API_BASE}/comfy_img2img"
IMG2IMG_LORA_ENDPOINT = f"{API_BASE}/comfy_img2img_lora"
STATUS_ENDPOINT = f"{API_BASE}/status"
IMAGE_ENDPOINT = f"{API_BASE}/image"
VIDEO_ENDPOINT = f"{API_BASE}/video"
PERFECT_VIDEO_EDIT_ENDPOINT = f"{API_BASE}/perfect_video_edit"  # Unified endpoint
IMAGE_TO_VIDEO_ENDPOINT = f"{API_BASE}/image_to_video"
PERFECT_VIDEO_LORA_ENDPOINT = f"{API_BASE}/perfect_video_lora"
PERFECT_VIDEO_INSERT_ENDPOINT = f"{API_BASE}/perfect_video_insert"
FACE_SWAP_ENDPOINT = f"{API_BASE}/face_swap"
FACE_VIDEO_ENDPOINT = f"{API_BASE}/face_video"
I2I_PRO_ENDPOINT = f"{API_BASE}/i2i_pro"
I2I_DRAW_ENDPOINT = f"{API_BASE}/i2i_draw"
TXT2IMG_ENDPOINT = f"{API_BASE}/txt2img"
LTX_VIDEO_ENDPOINT = f"{API_BASE}/api/v1/ltx_video"
WAN22_VIDEO_V2_ENDPOINT = f"{API_BASE}/api/v1/wan22_video_v2"
SCAIL2_ACTION_TRANSFER_ENDPOINT = f"{API_BASE}/api/v1/scail2_action_transfer"
SCAIL2_VIDEO_REPLACEMENT_ENDPOINT = f"{API_BASE}/api/v1/scail2_video_replacement"

# --- LLM Configuration ---
LLM_API_URL = os.getenv("LLM_API_URL", "http://8.148.72.50:1234/v1/chat/completions")
LLM_MODEL_NAME = os.getenv(
    "LLM_MODEL_NAME", "huihui-qwen3-vl-30b-a3b-instruct-abliterated"
)

# --- Polling Configuration ---
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "2"))
POLL_TIMEOUT = int(os.getenv("POLL_TIMEOUT", "180"))

# --- Permission Configuration ---
REQUIRED_CHANNEL_ID = os.getenv("REQUIRED_CHANNEL_ID")
CHANNEL_INVITE_LINK = os.getenv("CHANNEL_INVITE_LINK")
REFUGE_GROUP_ID = os.getenv("REFUGE_GROUP_ID")
REFUGE_INVITE_LINK = os.getenv("REFUGE_INVITE_LINK")
ENABLE_PUBLIC_SHARE = os.getenv("ENABLE_PUBLIC_SHARE", "false").lower() == "true"

# --- Limit Configuration ---
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "10"))

# --- Redis Configuration ---
REDIS_URL = _get_env_value("REDIS_URL", "redis://:redispassword@127.0.0.1:6379/0")
REDIS_PREFIX = os.getenv("REDIS_PREFIX", "test_bot_")

# --- Admin Configuration ---
ADMIN_USERS = [int(u) for u in os.getenv("ADMIN_USERS", "").split(",") if u.strip()]
