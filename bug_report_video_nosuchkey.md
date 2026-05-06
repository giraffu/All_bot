# Web 端视频生成 NoSuchKey 及历史记录丢失问题分析报告

## 1. 问题反馈与现象
- **反馈用户**：彼端、枕川 待雾
- **问题现象**：在 Web 端进行视频生成（视频编辑等）时，有概率在生成结束后弹出一个长串路径的报错页面（显示 `NoSuchKey`，提示在云存储中找不到对应的 `.png` 文件）。同时，用户的“闪回瓶（历史记录）”中也没有生成该次任务的记录。

## 2. 问题根因分析

该问题由 **底层数据链路字段丢失**、**Web API 状态轮询逻辑缺陷** 和 **大文件处理超时机制** 共同导致。

### 2.1 致命盲点：底层链路 `task_type` 字段丢失（真正的根因）
在 `src/web_api/routers/tasks.py` 中，获取任务类型的方式如下：
```python
task_type = parsed.get("task_type", "edit")
is_video = task_type in ["face_video", "txt2video", "video_lora", "custom_video", "perfect_video_insert", "doggy_style", "blowjob", "undress_tongue", "closeup_blowjob", "ltx_video"]
ext = "mp4" if is_video else "png"
```
这段代码依赖 `parsed` 中存在 `task_type` 字段，而该数据来源于后端的 Redis Pub/Sub 广播（`comfy:task_events`）或 `/status` 接口。
**但实际上，后端根本没有下发这个字段**：
1. 底层队列管理器 (`backend/app/queue_manager.py`) 广播的 JSON 载荷里只有 `status`、`result_path` 和 `progress`。
2. `/status/{task_id}` 接口绑定的模型 `TaskStatusResponse` (`backend/app/models.py`) 也没有 `task_type` 字段。

**结果**：`parsed.get("task_type", "edit")` **永远只能拿到默认值 `"edit"`**。由于 `"edit"` 肯定不在视频列表中，所以无论什么视频任务，只要触发超时 Fallback，后缀名必定会被错误地赋值为 `.png`。

### 2.2 后缀名判断漏洞 (代码级)
即便 `task_type` 正常下发，原代码中硬编码的判断列表也存在缺陷：`video_edit` 及部分视频任务类型漏写在了这个列表中。这本身也是一个隐患。

### 2.3 为什么是“有概率”发生？(时序与超时机制)
当底层节点完成生成时，Web 接口会尝试去数据库的 `History` 表（闪回瓶）中读取真实的最终文件路径。
代码中设定了最多尝试 10 次，每次等待 0.5 秒（总计 5 秒）的轮询机制：
- **正常情况**：如果后端在 5 秒内成功把大视频文件传到了目标存储并写好了数据库，Web 接口就能读到正确的 `.mp4` 路径，此时网页显示正常。
- **触发 Bug（概率发生）**：视频文件通常较大，从临时桶下载再上传到目标桶的时间经常会超过 5 秒。一旦超过 5 秒还没写完数据库，Web 接口就会放弃等待，触发**兜底机制**，使用上述因为 2.1 导致的错误 `.png` 后缀拼接出一个默认下载链接扔给前端。前端请求不存在的文件，触发 `NoSuchKey`。

### 2.4 为什么闪回瓶没有记录？
报错发生时，后端的视频入库流程仍在进行中（已超过5秒）或最终失败。前端因为拿到了错误的链接并报错中断了体验，而只要入库流程没有完全走完，数据库里就不会有该记录，因此用户的“闪回瓶”里也看不到这次任务。

## 3. 解决方案建议

为了彻底解决此问题，必须打通底层的数据链路并消除硬编码，建议进行以下代码修复：

### 3.1 改造后端数据模型与队列管理器（打通链路）
1. **修改模型**：在 `backend/app/models.py` 的 `TaskStatusResponse` 中补充 `task_type: Optional[str] = None` 字段。
2. **修改队列广播**：在 `backend/app/queue_manager.py` 中，在 `complete_task` 等发布事件的地方，先从 Redis 中读取原有的 `type` 字段，并将其作为 `"task_type"` 注入到 `json.dumps` 广播出去的 Payload 中。并在 `get_task_status` 接口返回值中补充 `task_type`。

### 3.2 补全全局视频任务类型配置
在 `src/constants.py` 中，将缺失的视频类型补充到全局常量 `VIDEO_TASK_TYPES` 中：
```python
VIDEO_TASK_TYPES = [
    "doggy_style", "perfect_video_insert", "blowjob", "undress_tongue", 
    "closeup_blowjob", "custom_video", "face_video", "face_video_step1", 
    "face_video_step2", "video_lora", "ltx_video", 
    "video_edit", "perfect_video_edit" # 增加缺失的视频类型
]
```

### 3.3 消除 API 层的硬编码
在 `src/web_api/routers/tasks.py` 的 SSE 接口 (`task_status_stream`) 中，直接引入全局变量替换硬编码：
```python
from src.constants import VIDEO_TASK_TYPES

# 将原本的 3 处硬编码替换为：
is_video = task_type in VIDEO_TASK_TYPES
```

### 3.4 优化数据库轮询超时时间
视频文件体积大，5秒的上传和入库时间冗余过小。建议将 `range(10)` 的轮询次数适当增加到 30 次（15秒），以给大视频文件的传输留出足够的缓冲时间。
```python
for _ in range(30): # 从 10 修改为 30
    async with AsyncSessionLocal() as db:
        hist = (await db.execute(select(History).where(History.task_id == task_id))).scalars().first()
        if hist and hist.output_file and hist.output_file.startswith(str(current_user.id)):
            final_result_path = hist.output_file
            break
    await asyncio.sleep(0.5)
```
