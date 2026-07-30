# cspell: disable
import os
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.runtime_environment import resolve_runtime_environment

ALLBOT_ENV, BOT_TYPE = resolve_runtime_environment()


def _get_env_value(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def _get_bool_env(name: str, default: str = "false") -> bool:
    return str(_get_env_value(name, default) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# --- Bot Configuration ---
TELEGRAM_API_BASE_URL = os.getenv("TELEGRAM_API_BASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")
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
MINI_APP_URL = _get_env_value("MINI_APP_URL")
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
    resolved_base_url = base_url or MINI_APP_URL
    if not resolved_base_url:
        raise ValueError("MINI_APP_URL is required")
    resolved_version = MINI_APP_VERSION if version is None else version
    return append_version_query(resolved_base_url, resolved_version)


def build_ton_payment_mini_app_url(
    base_url: str | None = None,
    version: str | None = None,
) -> str:
    resolved_base_url = base_url or MINI_APP_URL
    if not resolved_base_url:
        raise ValueError("MINI_APP_URL is required")

    parsed = urlparse(resolved_base_url)
    billing_path = f"{parsed.path.rstrip('/')}/billing"
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items.update({"method": "ton", "kind": "membership"})
    resolved_version = MINI_APP_VERSION if version is None else version
    if resolved_version:
        query_items["v"] = resolved_version
    return urlunparse(
        parsed._replace(path=billing_path, query=urlencode(query_items))
    )


def build_usdt_ton_payment_mini_app_url(
    *,
    kind: str,
    base_url: str | None = None,
    version: str | None = None,
) -> str:
    if kind not in {"membership", "credits"}:
        raise ValueError("USDT-TON billing kind must be membership or credits")
    resolved_base_url = base_url or MINI_APP_URL
    if not resolved_base_url:
        raise ValueError("MINI_APP_URL is required")

    parsed = urlparse(resolved_base_url)
    billing_path = f"{parsed.path.rstrip('/')}/billing"
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items.update({"method": "usdt-ton", "kind": kind})
    resolved_version = MINI_APP_VERSION if version is None else version
    if resolved_version:
        query_items["v"] = resolved_version
    return urlunparse(
        parsed._replace(path=billing_path, query=urlencode(query_items))
    )


# --- Database Configuration ---
# Only PostgreSQL is supported
DATABASE_URL = _get_env_value("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("sqlite"):
    raise ValueError("only PostgreSQL DATABASE_URL is supported")

DB_POOL_SIZE = int(os.environ["DB_POOL_SIZE"])
DB_MAX_OVERFLOW = int(os.environ["DB_MAX_OVERFLOW"])

# --- MinIO Configuration ---
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
MINIO_BUCKET = os.getenv("MINIO_BUCKET")
MINIO_RESULT_BUCKET = os.getenv("MINIO_RESULT_BUCKET")
MINIO_TEMPLATE_BUCKET = os.getenv("MINIO_TEMPLATE_BUCKET")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_PUBLIC_URL = os.getenv("MINIO_PUBLIC_URL")
IMGPROXY_URL = os.getenv("IMGPROXY_URL")

# --- Cloudflare R2 Configuration ---
R2_ENDPOINT = os.getenv("R2_ENDPOINT")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET = os.getenv("R2_BUCKET")
R2_PUBLIC_DOMAIN = os.getenv("R2_PUBLIC_DOMAIN")
R2_MAX_POOL_CONNECTIONS = int(os.environ["R2_MAX_POOL_CONNECTIONS"])
R2_EXISTS_POSITIVE_TTL_SECONDS = int(os.environ["R2_EXISTS_POSITIVE_TTL_SECONDS"])
R2_EXISTS_NEGATIVE_TTL_SECONDS = int(os.environ["R2_EXISTS_NEGATIVE_TTL_SECONDS"])
R2_EXISTS_CACHE_MAX_ENTRIES = int(os.environ["R2_EXISTS_CACHE_MAX_ENTRIES"])
R2_HEAD_SEMAPHORE_LIMIT = int(os.environ["R2_HEAD_SEMAPHORE_LIMIT"])
R2_HEAD_CONNECT_TIMEOUT_SECONDS = float(os.environ["R2_HEAD_CONNECT_TIMEOUT_SECONDS"])
R2_HEAD_READ_TIMEOUT_SECONDS = float(os.environ["R2_HEAD_READ_TIMEOUT_SECONDS"])
R2_HEAD_MAX_ATTEMPTS = int(os.environ["R2_HEAD_MAX_ATTEMPTS"])

# --- API Configuration ---
# Default to the backend server IP
API_BASE = _get_env_value("API_BASE")
API_TOKEN = _get_env_value("API_TOKEN")

# Endpoints constructed from API_BASE
IMG2IMG_ENDPOINT = f"{API_BASE}/comfy_img2img"
IMG2IMG_LORA_ENDPOINT = f"{API_BASE}/comfy_img2img_lora"
PORNMASTER_FLUX2_SINGLE_EDIT_ENDPOINT = (
    f"{API_BASE}/api/v1/pornmaster_flux2_single_edit"
)
PORNMASTER_FLUX2_MULTI_EDIT_ENDPOINT = f"{API_BASE}/api/v1/pornmaster_flux2_multi_edit"
PORNMASTER_FLUX2_EDIT_BF16_ENDPOINT = f"{API_BASE}/api/v1/pornmaster_flux2_edit_bf16"
PORNMASTER_FLUX2_MULTI_EDIT_BF16_ENDPOINT = (
    f"{API_BASE}/api/v1/pornmaster_flux2_multi_edit_bf16"
)
STATUS_ENDPOINT = f"{API_BASE}/status"
IMAGE_ENDPOINT = f"{API_BASE}/image"
VIDEO_ENDPOINT = f"{API_BASE}/video"
PERFECT_VIDEO_EDIT_ENDPOINT = f"{API_BASE}/perfect_video_edit"  # Unified endpoint
IMAGE_TO_VIDEO_ENDPOINT = f"{API_BASE}/image_to_video"
PERFECT_VIDEO_LORA_ENDPOINT = f"{API_BASE}/perfect_video_lora"
PERFECT_VIDEO_INSERT_ENDPOINT = f"{API_BASE}/perfect_video_insert"
FACE_SWAP_ENDPOINT = f"{API_BASE}/face_swap"
FACE_SWAP_V2_ENDPOINT = f"{API_BASE}/face_swap_v2"
FACE_VIDEO_ENDPOINT = f"{API_BASE}/face_video"
I2I_PRO_ENDPOINT = f"{API_BASE}/i2i_pro"
I2I_DRAW_ENDPOINT = f"{API_BASE}/i2i_draw"
TXT2IMG_ENDPOINT = f"{API_BASE}/txt2img"
LTX_VIDEO_ENDPOINT = f"{API_BASE}/api/v1/ltx_video"
LTX_VIDEO_FLF2V_ENDPOINT = f"{API_BASE}/api/v1/ltx_video_flf2v"
LTX_VIDEO_V2V_AUDIO_ENDPOINT = f"{API_BASE}/api/v1/ltx_video_v2v_audio"
LTX_T2V_ENDPOINT = f"{API_BASE}/api/v1/ltx_t2v"
LTX_T2V_IC_ENDPOINT = f"{API_BASE}/api/v1/ltx_t2v_ic"
CHARACTER_REFERENCE_BUILD_ENDPOINT = f"{API_BASE}/api/v1/character_reference_build"
WAN22_VIDEO_V2_ENDPOINT = f"{API_BASE}/api/v1/wan22_video_v2"
SCAIL2_ACTION_TRANSFER_ENDPOINT = f"{API_BASE}/api/v1/scail2_action_transfer"
SCAIL2_ACTION_TRANSFER_LONG_ENDPOINT = f"{API_BASE}/api/v1/scail2_action_transfer_long"
SCAIL2_VIDEO_REPLACEMENT_ENDPOINT = f"{API_BASE}/api/v1/scail2_video_replacement"
SCAIL2_FACE_SWAP_V2_ENDPOINT = f"{API_BASE}/api/v1/scail2_face_swap_v2"

# --- LLM Configuration ---
LLM_API_URL = os.getenv("LLM_API_URL")
LLM_MODEL_NAME = os.getenv(
    "LLM_MODEL_NAME", "huihui-qwen3-vl-30b-a3b-instruct-abliterated"
)

# --- Polling Configuration ---
POLL_INTERVAL = int(os.environ["POLL_INTERVAL"])
POLL_TIMEOUT = int(os.environ["POLL_TIMEOUT"])

# --- Permission Configuration ---
REQUIRED_CHANNEL_ID = os.getenv("REQUIRED_CHANNEL_ID")
CHANNEL_INVITE_LINK = os.getenv("CHANNEL_INVITE_LINK")
REFUGE_GROUP_ID = os.getenv("REFUGE_GROUP_ID")
REFUGE_INVITE_LINK = os.getenv("REFUGE_INVITE_LINK")
ENABLE_PUBLIC_SHARE = os.environ["ENABLE_PUBLIC_SHARE"].lower() == "true"
ENABLE_FREE_EDIT_V2 = _get_bool_env("ENABLE_FREE_EDIT_V2")
ENABLE_SCAIL2_LONG_ACTION_TRANSFER = _get_bool_env("ENABLE_SCAIL2_LONG_ACTION_TRANSFER")

# --- Limit Configuration ---
DAILY_LIMIT = int(os.environ["DAILY_LIMIT"])

# --- Redis Configuration ---
REDIS_URL = _get_env_value("REDIS_URL")
REDIS_PREFIX = os.getenv("REDIS_PREFIX")

# --- Admin Configuration ---
ADMIN_USERS = [int(u) for u in os.getenv("ADMIN_USERS", "").split(",") if u.strip()]
