# 子模块: 交互状态机与回调路由 (FSM & Callback Handlers)

## 1. 目标与范围
本模块包含所有通过 Python-Telegram-Bot (PTB) 实现的有限状态机逻辑，以及基于装饰器注册的 callback 路由体系。

当前职责边界：
- FSM 负责分步收集图片、视频设置、提示词与确认信息。
- 全局菜单打断依赖统一黑盒路由，而不是散落的硬编码菜单判断。
- callback 路由负责把充值、广场、杂项等回调拆分到独立模块。
- 文件下载、临时目录创建与清理由服务层承接，不应在各 FSM 内重复实现。

## 2. 当前架构图

```mermaid
stateDiagram-v2
    [*] --> START : 点击某个 FSM 入口
    START --> WAITING_IMAGE : 发送图片要求
    WAITING_IMAGE --> WAITING_SETTINGS : 上传图片
    WAITING_IMAGE --> CANCEL : 主菜单打断 / /cancel
    WAITING_SETTINGS --> WAITING_PROMPT : 选择分辨率/时长/模型
    WAITING_SETTINGS --> CANCEL : 主菜单打断 / 超时
    WAITING_PROMPT --> WAITING_CONFIRMATION : 输入提示词 / 优化提示词
    WAITING_PROMPT --> CANCEL : 主菜单打断 / 超时
    WAITING_CONFIRMATION --> SUBMIT : 确认生成
    WAITING_CONFIRMATION --> CANCEL : 放弃生成
    SUBMIT --> [*] : 释放 FSM，移交 Bot task flow
    CANCEL --> [*] : 清理 user_data 与临时文件
```

## 3. 当前主链路
### 3.1 FSM 到 Bot 任务流
当前主链为：
- FSM / message handler
- 分域 entrypoints
- `task_service_entrypoints_generation.py`
- `task_service_entrypoints_specialized.py`
- `task_service_entrypoints_video.py`
- `run_bot_task_application(...)`

Bot flow 当前采用五段式上下文：
- `request`
- `presentation`
- `billing`
- `failure`
- `cleanup`

取消态使用 `BotTaskCancelled`，不再使用字符串 sentinel。

### 3.2 全局菜单黑盒退出
FSM 入口与过程中，当前推荐组合为：
- `I18nFilter(...)`
- `GLOBAL_REVERSE_MAP`
- `is_global_menu_command(...)`

在任意文字输入 handler 内，应优先判断 `is_global_menu_command(...)`，决定是否强制退出当前 FSM。
- 若多个 FSM 共享同一类取消/超时/意外输入退出逻辑，优先复用 `fsm_shared.py`，不要在各文件继续复制 `_t/cancel/timeout/unexpected_input` 样板。

### 3.3 Callback 路由
当前 callback 体系依赖：
- `@register_callback("prefix")` 前缀注册
- 按前缀长度降序匹配
- 主入口导入子模块以触发注册
- 未命中时统一 `safe_answer_query(...)` 兜底

### 3.4 SCAIL-2 视频生视频 FSM
正式 Bot 与测试 Bot 的主菜单中，原“视频换脸”位置已进入“视频生视频”二级菜单。二级菜单顺序固定为：
- 视频换人
- 动作迁移
- 视频换脸
- 返回主菜单

`视频换人`、`动作迁移` 和云测试 Bot 的 `视频换脸` 由
`src/handlers/fsm/scail2_video_fsm.py` 处理，状态流为：
- `WAIT_REFERENCE_IMAGE`：只接收参考图片
- `WAIT_MOTION_VIDEO`：接收 Telegram video 或 video document，驱动视频上限 40MB
- `WAIT_PROMPT`：接收正向提示词，或通过 inline button 跳过并使用 task type 默认提示词；空文本会提示用户点击跳过
- `WAIT_DURATION`：inline keyboard 只允许 `5秒 · 40灵石` 或 `8秒 · 80灵石`

该 FSM 不询问负面提示词，统一使用 `SCAIL2_DEFAULT_NEGATIVE_PROMPT`。提交时通过
`process_scail2_video_task(...)` 进入 Bot task flow，inputs 与 Web 保持一致：
`images=[reference_image_local_path, motion_video_local_path]`、`prompt`（可为空，服务层会补默认值）、`negative_prompt`、
`duration`、`resolution=512x896`。正常结束、取消、超时、非法文件、全局菜单打断或下载后发现超限时，
都必须清理临时文件和 `user_data["scail2_video_data"]`。旧 `face_video` FSM
业务逻辑暂不删除，但测试环境的“视频换脸”菜单与 `/video_swap` 不再默认进入旧 720p/1024p 流程。

## 4. 关键实现约束
### 4.1 FSM 超时
当前主 FSM 普遍采用：
- `conversation_timeout=300`

若后续调整超时值，必须同步更新：
- FSM 文档
- 相关 focused tests
- 若有对应 skill 文档，也需同步更新

### 4.2 临时文件服务
常规 FSM 文件下载与清理应优先复用 `fsm_temp_file_service.py`，避免各 FSM 自己拼装。

### 4.3 语言切换
语言切换当前不只是菜单文案变更，还涉及：
- 数据库语言字段更新
- Redis 缓存同步
- translator 运行时状态刷新

## 5. 测试要求
- 覆盖 FSM 超时与主菜单打断
- 覆盖完整参数收集后进入对应 Bot entrypoint 或 `run_bot_task_application(...)`
- 覆盖 callback prefix 路由与统一兜底
- 覆盖 SCAIL-2 入口 task type 映射、40MB 视频拦截、5s/8s 时长按钮、默认负面词和临时文件清理；测试环境还需覆盖 `scail2_face_swap_v2`。
- 若 PTB 某些配置会触发已知 warning，测试需显式说明它是“预期行为”还是“应修复行为”
