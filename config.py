# cspell: disable
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_TOKEN_TEST = os.getenv("BOT_TOKEN_test")
FILE_BOT_TOKEN = os.getenv("FILE_BOT_TOKEN")
TELETHON_API_ID = os.getenv("TELETHON_API_ID")
TELETHON_API_HASH = os.getenv("TELETHON_API_HASH")
GROUP_ID = os.getenv("GROUP_ID")
PHONE = os.getenv("PHONE")
PASSWORD = os.getenv("PASSWORD")
# Default to the previously hardcoded proxy if not set in env
PROXY_URL = os.getenv("PROXY_URL", "socks5://10.137.118.157:7890")

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8003")
IMG2IMG_ENDPOINT = f"{API_BASE}/comfy_img2img"
STATUS_ENDPOINT = f"{API_BASE}/status"
VIDEO_STATUS_ENDPOINT = f"{API_BASE}/video/status"
IMAGE_ENDPOINT = f"{API_BASE}/image"
VIDEO_ENDPOINT = f"{API_BASE}/video"
PERFECT_VIDEO_EDIT_ENDPOINT = "http://10.137.70.8:8003/perfect_video_edit"
PERFECT_VIDEO_INSERT_ENDPOINT = f"{API_BASE}/perfect_video_insert"
FACE_SWAP_ENDPOINT = f"{API_BASE}/face_swap"
QUEUE_POSITION_ENDPOINT = f"{API_BASE}/queue/position"


# LLM 配置
LLM_API_URL = os.getenv("LLM_API_URL", "http://8.148.72.50:1234/v1/chat/completions")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "huihui-qwen3-vl-30b-a3b-instruct-abliterated")

# 轮询配置
POLL_INTERVAL = 2      # 秒
POLL_TIMEOUT = 180     # 最大等待 3 分钟

# 权限控制
REQUIRED_CHANNEL_ID = os.getenv("REQUIRED_CHANNEL_ID")
CHANNEL_INVITE_LINK = os.getenv("CHANNEL_INVITE_LINK")

# 限额配置
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "10"))
