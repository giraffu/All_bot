# 高级视频提示词大模型优化实现方案 (Prompt Optimization Plan)

## 1. 核心设计原则 (模块化与解耦)
为了满足后续无缝扩展到 Web 端的需求，整个功能必须做到**业务逻辑与接入层（Telegram/FastAPI）完全分离**：
1. **独立服务类**：创建一个纯净的 `PromptOptimizerService`，不引入任何 `telegram.Update` 或 FastAPI `Request` 对象。
2. **标准出入参**：该服务仅接收纯文本（用户输入的原始提示词）和图片的 Base64 编码字符串，返回优化后的字符串。
3. **复用性**：Telegram Bot 和未来的 Web BFF 接口只需负责收集数据并调用该服务。

---

## 2. LLM 接入层设计 (`src/services/prompt_optimizer_service.py`)

### 2.1 接口配置
由于 Bot 运行在 Docker 容器内，而 LM Studio 部署在宿主机本地，网络通信采用宿主机映射：
- **API Base URL**: `http://host.docker.internal:1234/v1` （或者在 `.env` 中配置为 `LLM_API_BASE`）
- **模型名称**: `qwen3.5-35b-a3b-uncensored-hauhaucs-aggressive`
- **客户端库**: 建议使用 `httpx.AsyncClient` 配合 OpenAI Vision 标准请求体格式发送异步请求。

### 2.2 System Prompt 设计
根据业务需求，将规则固化为 System Prompt 约束 LLM 的输出：
```text
You are an expert AI video generation prompt engineer.
Your task is to optimize the user's video generation prompt based on the provided initial image and the user's original idea.

Requirements:
1. The output MUST be entirely in English.
2. You must systematically describe the following elements:
   - The character's features based on the initial image.
   - The background environment.
   - The actions to be performed.
   - Camera movement (e.g., pan, zoom, tracking).
   - The words spoken by the character (if any).
3. Do NOT include any conversational filler, explanations, or greetings. Output ONLY the optimized prompt.
```

### 2.3 核心方法签名示例
```python
class PromptOptimizerService:
    @staticmethod
    async def optimize_video_prompt(user_prompt: str, image_base64: str) -> str:
        # 1. 组装 OpenAI Vision API 格式的 payload
        # 2. 发起 HTTP 请求到 LM Studio
        # 3. 提取 content 并返回
        pass
```

---

## 3. Telegram Bot FSM 层改造 (`ltx_video_fsm.py`)

### 3.1 UI 变更
在用户发送完初始提示词后（`receive_prompt` 函数），构建两个并排的按钮：
- `[✅ 确定生成]` (保持原有回调 `confirm_ltx_video`)
- `[🪄 智能优化提示词]` (新增回调 `optimize_ltx_video`)

### 3.2 交互流转 (新增 `optimize_prompt_handler`)
1. **状态响应**：用户点击优化按钮后，拦截该 Callback。
2. **友好提示**：立刻 `edit_message_text` 为：“⏳ *大模型正在为您分析图片并优化提示词，这可能需要几十秒，请稍候...*” （因为 35B 模型推理需要一定时间）。
3. **数据处理**：读取 `fsm_data['image_path']` 将本地图片转为 Base64，连同 `fsm_data['prompt']` 传给 `PromptOptimizerService`。
4. **结果更新**：LLM 返回结果后，更新 `fsm_data['prompt'] = optimized_prompt`。
5. **重绘 UI**：重新编辑消息，展示优化后的英文提示词，并附带按钮 `[✅ 确定生成]`（或者加上 `[🔄 再次优化]`）。

---

## 4. 未来 Web BFF 端扩展设计 (Web API)

当需要将此功能开放给 Vue3 前端时，由于底层 `PromptOptimizerService` 已完全解耦，只需极少的代码即可完成：

**路由设计 (`src/web_api/routers/utils.py`)**:
```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.services.prompt_optimizer_service import PromptOptimizerService

router = APIRouter()

class OptimizeRequest(BaseModel):
    prompt: str
    image_base64: str

@router.post("/optimize-prompt")
async def api_optimize_prompt(request: OptimizeRequest):
    try:
        optimized = await PromptOptimizerService.optimize_video_prompt(
            request.prompt, request.image_base64
        )
        return {"optimized_prompt": optimized}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```
前端只需要发送 JSON 即可获取同样的 LLM 优化能力，保持全端体验一致。

---

## 5. 容错与并发控制 (Edge Cases & Concurrency)

### 5.1 并发控制策略 (Semaphore)
根据提供的系统监控数据，当前 Qwen 3.5 35B 模型仅加载就占用了约 34% 的 VRAM（约 22GB），剩余显存容量有限。
当多个用户同时请求 Vision 任务时，KV Cache 的爆发性增长极易导致 OOM (Out of Memory) 或大幅降低推理速度。

**建议并发数**：控制在 **2 - 3** 个并发请求比较安全。
**实现方式**：
在 `PromptOptimizerService` 内部引入 `asyncio.Semaphore` 来实现全局级别的限流。

```python
import asyncio

class PromptOptimizerService:
    # 限制同时调用大模型的并发数为 2
    _semaphore = asyncio.Semaphore(2)

    @staticmethod
    async def optimize_video_prompt(user_prompt: str, image_base64: str) -> str:
        # 当超过 2 个用户同时请求时，其他用户将在此处排队等待
        async with PromptOptimizerService._semaphore:
            # 1. 组装 payload
            # 2. 发起 HTTP 请求到 LM Studio
            # 3. 提取内容返回
            pass
```

**用户体验优化**：
如果用户在排队，他们看到的依然是“⏳ *大模型正在为您分析图片并优化提示词，这可能需要几十秒，请稍候...*”的提示，不会报错。只要限流得当，用户只会感觉推理变慢了一点，但系统不会崩溃。

### 5.2 其他容错处理
1. **超时与宕机防御**：设置 LLM 请求的超时时间（如 `timeout=120.0`，考虑到排队时间，超时应设置得长一些）。如果 LM Studio 未开启或响应超时，需捕获 `httpx.RequestError` 或 `asyncio.TimeoutError`，并提示用户：“⚠️ *大模型服务当前繁忙或不可用，请直接点击确定生成。*”，恢复原有 UI。
2. **图片过大限制**：在进行 Base64 编码前，若发现用户上传的原图过大（如分辨率超过 1024x1024 或体积 >5MB），可先在内存中进行简单的等比例缩放压缩（如 resize 到最大边长 1024px），这能显著降低本地 LLM 处理 Vision 任务的显存压力。