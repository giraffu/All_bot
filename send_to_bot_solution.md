# Web 端「发送给 Bot」功能实施方案

## 1. 背景与目标
为了彻底解决 Android 端 Telegram Web App 内置浏览器无法直接将视频（Blob）下载并保存到系统相册的限制，计划在 Web 端作品详情页新增「发送给 Bot」功能。
用户点击后，后端会将该作品（图片/视频）直接通过**主 Bot** 推送到用户的 Telegram 私聊窗口，用户可以在原生聊天界面中毫无障碍地保存文件。

## 2. 前端改造方案 (Vue 3)

### 2.1 UI 交互更新
- **位置**：在移动端/PC端的作品操作栏（如下载、收藏、删除旁）新增一个「发送给 Bot」的按钮。
- **图标**：使用 Telegram 风格的纸飞机图标（如 `SendOutlined` 或类似的纸飞机 SVG）。
- **文案**：转发给 Bot (Forward to Bot) 或 发送至聊天。

### 2.2 逻辑封装 (`useTaskInteraction.ts`)
在现有的 `useTaskInteraction` composable 中新增 `handleSendToBot` 方法。
**注意**：前端 `api` 实例已经配置了基础路径（Base URL），因此请求路径不需要加 `/api` 前缀，直接请求 `/users/history/...`。

```typescript
const handleSendToBot = async (record: any) => {
  // 防御性校验：没有生成文件的任务不能发送
  if (!record.output_file) {
    message.warning('该记录无文件可发送');
    return;
  }
  
  const hide = message.loading('正在发送至私聊...', 0);
  try {
    // 注意：不需要 /api 前缀，api 实例已经自带了
    await api.post(`/users/history/${record.task_id}/send-to-bot`);
    hide();
    message.success('已发送至您的私聊，请在 Telegram 中查收');
  } catch (error: any) {
    console.error(error);
    hide();
    // 读取后端抛出的具体错误信息
    message.error(error.response?.data?.detail || '发送失败，请确保机器人未被屏蔽');
  }
}

// 在 return 中导出
return {
  submittingTasks,
  submitToGallery,
  handleFavorite,
  handleDelete,
  handleDownload,
  handleSendToBot // <--- 新增
}
```

## 3. 后端改造方案 (FastAPI Web API)

### 3.1 新增 API 接口
为了符合当前项目的路由架构，接口新增在 `src/web_api/routers/users.py` 中：
- **Endpoint**: `POST /api/users/history/{task_id}/send-to-bot`
- **Auth**: 必须经过 JWT 鉴权，通过 `Depends(get_current_user)` 获取当前用户。

### 3.2 业务逻辑流转与实现
需要特别注意以下几点与现有架构的对齐：
1. **多渠道登录兼容**：系统支持 Google/Email 登录，必须校验 `current_user.telegram_id`。
2. **并发防刷**：使用 `redis_client.redis.set(..., nx=True, ex=10)` 实现 10 秒防刷锁。
3. **Bucket 动态解析**：复用现有的 Bucket 拆解逻辑（对齐 `favorite_history`），安全提取 `bucket_name` 和 `object_name`。

**具体代码实现 (`users.py`)**：
```python
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import History, User
from src.services.redis_client import redis_client
from src.services.storage import storage
from config import TELEGRAM_API_BASE_URL, BOT_TOKEN
from src.web_api.dependencies import get_current_user
from src.database.core import AsyncSessionLocal

@router.post("/history/{task_id}/send-to-bot")
async def send_history_to_bot(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. 检查多渠道登录用户的 TG 绑定状态
    if not current_user.telegram_id:
        raise HTTPException(status_code=400, detail="您尚未绑定 Telegram 账号，无法发送至私聊")

    # 2. Redis 10秒防刷锁（严格对齐现有 redis_client 模式）
    lock_key = f"rate_limit:send_to_bot:{current_user.id}"
    is_locked = await redis_client.redis.set(lock_key, "1", nx=True, ex=10)
    if not is_locked:
        raise HTTPException(status_code=429, detail="操作过于频繁，请10秒后再试")

    # 3. 校验历史记录与文件存在性
    stmt = select(History).where(History.task_id == task_id, History.user_id == current_user.id)
    result = await db.execute(stmt)
    history = result.scalar_one_or_none()

    if not history:
        raise HTTPException(status_code=404, detail="未找到对应的任务记录")
    if not history.output_file:
        raise HTTPException(status_code=400, detail="该任务没有生成文件")

    # 4. 严谨提取 bucket 和 object_name (对齐本文件中 favorite_history 的逻辑)
    parts = history.output_file.split("/")
    if len(parts) > 1 and parts[0] in ["bot-data", "comfyui-temp"]:
        bucket_name = parts[0]
        object_name = "/".join(parts[1:])
    elif "comfyui-temp" not in history.output_file and "bot-data" not in history.output_file:
        bucket_name = "comfyui-temp" if not "/" in history.output_file else "bot-data"
        object_name = history.output_file
    else:
        bucket_name = "bot-data"
        object_name = history.output_file

    # 5. 生成预签名 URL 供 Telegram 抓取
    file_url = storage.get_presigned_url(object_name, expires_hours=1, bucket=bucket_name)
    if not file_url:
        raise HTTPException(status_code=500, detail="无法生成文件访问链接")

    # 6. 构造 Local API 请求并发送
    is_video = history.type and 'video' in history.type.lower()
    method = "sendVideo" if is_video else "sendPhoto"
    url = f"{TELEGRAM_API_BASE_URL}/bot{BOT_TOKEN}/{method}"
    
    # 截取 Prompt 前 100 字符作为 caption，避免太长导致发送失败
    caption = history.prompt[:100] + "..." if history.prompt and len(history.prompt) > 100 else history.prompt
    
    payload = {
        "chat_id": current_user.telegram_id,
        "caption": caption
    }
    if is_video:
        payload["video"] = file_url
    else:
        payload["photo"] = file_url

    async with httpx.AsyncClient() as client:
        try:
            # timeout 设置宽裕点，因为 Local API 需要去 MinIO 拉取大视频
            resp = await client.post(url, json=payload, timeout=30.0)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [400, 403]:
                # 用户拉黑机器人或者 Telegram 找不到该 Chat
                raise HTTPException(status_code=403, detail="发送失败，请确保您在 Telegram 中已允许机器人发送消息")
            import logging
            logging.getLogger(__name__).error(f"Telegram API Error: {e.response.text}")
            raise HTTPException(status_code=500, detail="发送失败，Telegram 服务器异常")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Send to bot request failed: {e}")
            raise HTTPException(status_code=500, detail="发送失败，网络连接异常")

    return {"status": "success", "message": "已发送至您的 Telegram 私聊"}
```

## 4. 异常处理机制 (红线与防御)

1. **并发防刷**：如上所述，通过 Redis `nx=True` 设置 10 秒级别的冷却锁，防止恶意点击导致 Bot 触发 Telegram 官方的全局限流（Flood Wait）。
2. **URL 可访问性**：传递给 Telegram API 的媒体 URL 采用 `storage.get_presigned_url`，确保证书和生命周期安全。
3. **多渠道登录拦截**：如果用户没有绑定 Telegram 账号（例如通过 Email/Google 登录），必须在入口处拦截并提示。
4. **Bot 屏蔽处理**：如果用户在 Telegram 中拉黑（Block）了该 Bot，调用发送接口会返回 `403 Forbidden` 或 `400 Bad Request`。后端需捕获 `httpx.HTTPStatusError` 并向前端返回 `HTTPException(status_code=403, detail="发送失败，请确保您在 Telegram 中已允许机器人发送消息")`。

## 5. 实施步骤建议
1. **后端 API 开发**：在 `users.py` 实现接口并编写核心逻辑。通过 Swagger 测试，确保 Bot 能成功往测试账号发送视频。
2. **前端 UI 接入**：在 `useTaskInteraction.ts` 中封装逻辑，并在组件中绑定按钮，确认样式和 Loading 交互体验。
3. **生产环境部署**：前后端一并发布，并在真机（特别是安卓机）上验证全链路文件保存体验。