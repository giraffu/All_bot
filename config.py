# cspell: disable
import os
from dotenv import load_dotenv

load_dotenv()

# --- Bot Configuration ---
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
VITE_MERCHANT_ADDRESS = os.getenv("VITE_MERCHANT_ADDRESS", "UQAluW2wxRCDsJIKGH59jB07xODgEbStdUPEj9AjI88d9l-s")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://pay.aivison.it.com/")

# --- Database Configuration ---
# Only PostgreSQL is supported
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL or DATABASE_URL.startswith("sqlite"):
    # Fallback or error if not provided?
    # Better to default to a sensible Postgres URL or raise error.
    # For now, let's assume env var is set, or provide a default local PG
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/bot_db")

# --- MinIO Configuration ---
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "192.168.1.115:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "chuzeyu")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "@Cv1347968277")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "bot-data")
MINIO_TEMPLATE_BUCKET = os.getenv("MINIO_TEMPLATE_BUCKET", "bot-template")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_PUBLIC_URL = os.getenv("MINIO_PUBLIC_URL", f"http://{MINIO_ENDPOINT}")
IMGPROXY_URL = os.getenv("IMGPROXY_URL", "http://localhost:8080")

# --- Cloudflare R2 Configuration ---
R2_ENDPOINT = os.getenv("R2_ENDPOINT")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET = os.getenv("R2_BUCKET", "user-data")
R2_PUBLIC_DOMAIN = os.getenv("R2_PUBLIC_DOMAIN")

# --- API Configuration ---
# Default to the backend server IP
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8003")
API_TOKEN = os.getenv("API_TOKEN", "your_secure_token_here")  # Added based on changelog

# Endpoints constructed from API_BASE
IMG2IMG_ENDPOINT = f"{API_BASE}/comfy_img2img"
STATUS_ENDPOINT = f"{API_BASE}/status"
IMAGE_ENDPOINT = f"{API_BASE}/image"
VIDEO_ENDPOINT = f"{API_BASE}/video"
PERFECT_VIDEO_EDIT_ENDPOINT = f"{API_BASE}/perfect_video_edit" # Unified endpoint
PERFECT_VIDEO_LORA_ENDPOINT = f"{API_BASE}/perfect_video_lora"
PERFECT_VIDEO_INSERT_ENDPOINT = f"{API_BASE}/perfect_video_insert"
FACE_SWAP_ENDPOINT = f"{API_BASE}/face_swap"
FACE_VIDEO_ENDPOINT = f"{API_BASE}/face_video"
I2I_PRO_ENDPOINT = f"{API_BASE}/i2i_pro"

# --- LLM Configuration ---
LLM_API_URL = os.getenv("LLM_API_URL", "http://8.148.72.50:1234/v1/chat/completions")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "huihui-qwen3-vl-30b-a3b-instruct-abliterated")

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
REDIS_URL = os.getenv("REDIS_URL", "redis://:redispassword@127.0.0.1:6379/0")
REDIS_PREFIX = os.getenv("REDIS_PREFIX", "test_bot_")

# --- Admin Configuration ---
ADMIN_USERS = [int(u) for u in os.getenv("ADMIN_USERS", "").split(",") if u.strip()]
