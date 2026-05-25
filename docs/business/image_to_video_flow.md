# 图生视频 (Image-to-Video) 业务流与架构分析

本文档描述当前系统中的图生视频链路，包括 LTX-Video、自定义视频、快捷视频与相关 Telegram / Web 任务流。

## 一、 当前业务主链

```mermaid
sequenceDiagram
    actor User as Telegram 用户
    participant FSM as Bot 交互层
    participant Entry as Bot entrypoints / bot_task_service
    participant Flow as run_bot_task_application
    participant Core as task_core facade
    participant Backend as Central API / Queue / Worker
    participant Store as MinIO

    User->>FSM: 发送图生视频命令
    FSM-->>User: 提示上传图片、选择设置、输入提示词
    FSM->>Entry: 进入视频 entrypoint
    Entry->>Flow: 组装 BotTaskFlowContext 五段式上下文
    Flow->>Core: process_and_submit_task(...)
    Core->>Backend: 派发 registry_task_id / backend_task_id
    Flow-->>User: 前台进度通知 / 排队状态
    Backend->>Store: 上传视频结果
    Flow->>Store: 下载/发送视频结果
    Flow-->>User: 返回 MP4 与分享/交互按钮
```

### 当前关键事实
- FSM 不再直接长轮询 `task_core`；真实主链是 `entrypoint -> run_bot_task_application(...) -> task_core facade`。
- Bot 视频主链的取消态当前通过 `BotTaskCancelled` 收口，而不是字符串 sentinel。
- `quick_video_fsm.py` 已不再通过构造假的 `Update/Message` 适配旧接口。

## 二、 数据流向

```mermaid
graph TD
    subgraph ClientLayer [用户端]
        U_IMG[参考图片]
        U_TXT[提示词]
        U_CFG[分辨率/时长/模式]
    end

    subgraph BotLayer [Bot 侧]
        TMP[临时文件服务]
        FSM_CTX[FSM 上下文]
        ENTRY[视频 entrypoint]
        FLOW[Bot task flow]
    end

    subgraph CoreLayer [Core]
        FACADE[task_core facade]
        DEPS[provider / dependencies]
    end

    subgraph Backend [后端执行]
        CENTRAL[Central API]
        WORKER[Comfy Workers]
        STATUS[运行态事件 / 状态]
    end

    subgraph Storage [存储]
        MINIO[MinIO 结果桶]
    end

    U_IMG --> TMP
    U_TXT --> FSM_CTX
    U_CFG --> FSM_CTX
    TMP --> ENTRY
    FSM_CTX --> ENTRY
    ENTRY --> FLOW
    FLOW --> FACADE
    FACADE --> DEPS
    DEPS --> CENTRAL --> WORKER
    WORKER --> MINIO
    WORKER --> STATUS
    STATUS --> FLOW
    FLOW --> MINIO
```

## 三、 分层说明
### 3.1 交互层
- `ltx_video_fsm.py`、`image_to_video_fsm.py`、`quick_video_fsm.py` 等负责分步收集参数。
- 全局菜单打断通过 `is_global_menu_command(...)` 统一识别。
- 当前主 FSM 普遍使用 `conversation_timeout=300`。

### 3.2 Bot 任务流层
- 视频任务入口主要位于：
  - `task_service_entrypoints_video.py`
  - `task_service_entrypoints_specialized.py`
  - `task_service_entrypoints_generation.py`
- 这些入口负责构造 `BotTaskFlowContext`，再进入 `run_bot_task_application(...)`。
- `bot_task_service.py` 当前是薄兼容 facade，不应再被视为厚业务层。

### 3.3 Core 提交与监控层
- `task_core.py` 负责统一提交语义。
- `task_dispatcher.py` 基于 strategy 生成 workflow / payload。
- Web 任务完成后由 `task_core_web_monitor.py` 承接 side effect；Bot 则由 `run_bot_task_application(...)` 负责前台监控与展示。

## 四、 计费与资源约束
- 视频任务计费是动态的，通常由分辨率与时长组合决定。
- 过高画质与过长时长组合仍可能触发 guardrail，避免显存溢出或节点拥塞。
- 任何取消/失败路径都必须与并发锁释放和必要退款一并考虑。

## 五、 结果发送与清理
- Bot 完成后会发送 MP4、caption、reply markup 与后续交互入口。
- 运行结束后需清理：
  - status message
  - 本地临时文件
  - runtime state / registry
  - 必要的锁与终态消息

## 六、 测试要求
- 覆盖参数收集、菜单打断、超时退出。
- 覆盖视频 entrypoint 到 `run_bot_task_application(...)` 的上下文装配。
- 覆盖取消、失败、成功三条主分支。
- 若修改视频成本计算、requested_duration 或结果发送语义，需同步回归 focused tests 与黄金路径集。
