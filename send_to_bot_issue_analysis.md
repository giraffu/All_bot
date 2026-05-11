# Web 端“发送至私聊”失败问题分析与修复方案

## 1. 现象描述
在 Web 端点击“发送至私聊”时，前端弹出错误提示：`发送失败，请确保您在 Telegram 中已允许机器人发送消息`。
但实际上用户已经在 Telegram 中启动过机器人（`/start`），并没有拉黑机器人。这是一个典型的错误提示“误报”。

## 2. 案发过程分析（Root Cause）

经过排查代码执行链路，该问题的根本原因在于**内网穿透与异常捕获不够严谨**：

1. **内网 URL 无法被 Telegram 访问**：
   当用户请求 `/users/history/{task_id}/send-to-bot` 接口时，后端使用 `storage.get_presigned_url()` 生成了一个 MinIO 的临时下载链接。由于 MinIO 配置使用的是内网 IP（如 `192.168.1.115:9000`），生成的也是内网 URL。
2. **Telegram API 下载失败**：
   后端将这个内网 URL 放在 JSON 的 `video` / `photo` 字段中发送给 Telegram Local Bot API 服务器。由于 Telegram API 服务器无法访问内网 IP，下载失败，返回了 HTTP 400 错误（报错信息包含 `failed to get HTTP URL content`）。
3. **背锅的异常捕获**：
   在 `src/web_api/routers/users.py` 的 `send_history_to_bot` 函数中，对 400/403 错误的捕获逻辑如下：
   ```python
   if e.response.status_code in [400, 403]:
       error_msg = e.response.text
       if "wrong file identifier/HTTP URL specified" in error_msg:
           raise HTTPException(status_code=400, detail="发送失败：无法访问该文件链接...")
       
       # 核心漏洞：其他所有的 400 错误全部走到这里，提示用户拉黑了机器人
       raise HTTPException(
           status_code=403,
           detail="发送失败，请确保您在 Telegram 中已允许机器人发送消息",
       )
   ```
   因为 Telegram 这次返回的报错没有精确命中 `wrong file identifier...`，所以抛出了兜底的错误，误导了用户。

## 3. 修复方案 (Proposed Fixes)

要彻底修复这个问题，需要进行两方面的改造：

### 方案 A：修复 URL 访问域（推荐）
在生成给 Telegram 抓取的链接时，必须保证是**公网可访问的 URL**。
- 如果配置了 `R2_PUBLIC_DOMAIN`，优先拼接 R2 的 CDN 链接（例如 `https://r2.aivison.it.com/...`）。
- 或者使用 `MINIO_PUBLIC_URL` 生成公网链接。
*注：目前系统中已有 `src/web_api/routers/gallery.py` 中的 `get_media_url` 函数用于生成公网 URL，可以直接复用该逻辑，替换掉 `storage.get_presigned_url`。*

### 方案 B：改用 Local Telegram API 进行大文件流直传（更稳健，选定方案）
既然我们有 Local Telegram API 服务器（即 `69.63.220.115:8081`，由于其没有上传大小限制，适合大视频传输），如果直接通过公网 URL 让 Local API 去抓取，可能会受限于外网带宽或者 URL 无法访问的问题。

更稳健的做法是：
1. **内存下载**：让 FastAPI 后端通过内网直接从 MinIO 下载文件到内存（使用 `storage.get_file_bytes`）。
2. **文件流上传**：使用 `httpx` 将下载好的文件字节流以 `multipart/form-data` 的形式（例如传递 `files={"video": ("video.mp4", file_bytes, "video/mp4")}`），直接 POST 给 Local Telegram API 服务器的 `sendVideo` 或 `sendPhoto` 接口。
3. **免去公网依赖**：这种方式既利用了 Local API 绕过 50MB 限制的优势，又完全摆脱了对公网下载 URL（和域名解析）的依赖，极大提高了发送成功率。

### 补充：完善异常捕获
修改 `send_history_to_bot` 中的错误处理逻辑，补充对 `failed to get HTTP URL content` 的识别：
```python
if "wrong file identifier" in error_msg or "failed to get HTTP URL content" in error_msg:
    raise HTTPException(
        status_code=400,
        detail="发送失败：Telegram 无法访问该文件链接，文件可能已被清理或存在网络限制"
    )
```

## 4. 涉及修改的文件
- `src/web_api/routers/users.py` (主要修改 `send_history_to_bot` 函数)