# AllBot 系统架构总览

本文只描述稳定拓扑、核心闭环和职责边界。实时 worker/Pod 数量、主机容量、
某次迁移状态和事故记录不属于架构事实；分别读取资源画像、provider/XDG
运行态或 `docs/archive/`。

## 1. 系统形态

AllBot 是面向 Telegram 与 Web 的 AI 图片/视频生成平台，核心由五类模块组成：

| 层 | 主要职责 | 代表入口 |
| --- | --- | --- |
| 用户入口 | Telegram/Web 交互、认证、输入收集、展示 | `src/bot_main.py`、`src/web_api/main.py`、`qqcc_bot/main.py` |
| 业务编排 | 任务、计费、用户、Gallery 的公开 facade | `src/core/`、`src/services/` |
| 执行控制面 | 队列、Worker 协议、状态和调度 | `backend/app/` |
| 执行运行时 | 输入下载、workflow patch、ComfyUI、结果回报 | `workers/`、`remote_workers/` |
| 管理与运维 | Dashboard、不可变发布、GPU/LAN/RunPod operator | `dashboard/`、`scripts/release.py`、`ops/` |

正式与测试环境消费相同的不可变 artifact；数据库、Redis、token、bucket、域名
和开关由目标环境逐服务配置投影提供。

## 2. 分层边界

### 2.1 Core

- `src/core/` 使用内部 request/context、domain config 和显式
  provider/dependencies。
- core 不导入 Telegram `Update`、FastAPI `Request/APIRouter` 或具体基础设施
  客户端；平台入口先转换为内部 `internal_user_id`。
- 入口负责 provider 注册，core 不在 import 时自动装配运行态资源。
- facade 保持小 interface；复杂输入、扣费、submission、side effect 和清理
  放在实现层/builder。

### 2.2 入口与服务

- Telegram FSM 只负责平台状态、素材、回复和清理，任务计划进入 application
  service。
- Web router 保持薄，展示转换进入 presenter/service；对象存储探测不能与
  长数据库事务混合。
- `backend/app` 是 Central/Worker 执行面，不是普通 Web/BFF。用户 API 主入口
  是 `src/web_api`。
- Dashboard 编排管理视图，但不复制 QueueManager、billing 或 Gallery 的
  底层业务语义。

完整入口归属见
[入口职责矩阵](./入口职责矩阵_entry_responsibility_matrix.md)。

### 2.3 执行面

- Central 维护队列、worker heartbeat、status/complete 和控制面状态。
- Worker Agent 选择 workflow、准备输入、调用 ComfyUI、物化/上传结果并回报。
- ComfyUI Runtime 只加载模型并执行 JSON；workflow 事实源位于
  `workers/comfy_agent/workflows/`。
- GPU profile、LAN AIO、RunPod 是可替换执行 adapter，不改变用户任务 facade。

## 3. 核心闭环

### 3.1 生成任务

1. Bot/Web 将平台输入转换为内部 payload 和 `internal_user_id`。
2. task facade 完成权限、额度、扣费、输入准备、持久化和 Central submission。
3. Central 分配 backend task，Worker 执行 workflow 并上传当前 R2。
4. Web monitor、Bot completion 或恢复流程观察终态。
5. 成功写 History/extra outputs 并释放运行态；失败/取消按幂等账本退款。

必须区分 `registry_task_id` 与 `backend_task_id`。多阶段任务保持一个根业务
身份，中间执行 ID 和 continuation checkpoint 不对用户暴露。

详见
[生成任务全链路](./子模块_生成任务全链路_task_full_chain.md)、
[任务调度](./子模块_任务调度_task_scheduler.md) 和
[黄金路径](./子模块_任务黄金路径回归清单_task_golden_path.md)。

### 3.2 身份与资产

- Telegram/Web/私有 Bot 身份最终映射到 `internal_user_id`。
- JWT 使用 `password_version` 使改密后的旧会话失效。
- 灵石、支付、affiliate、会员和退款通过账本/履约 seam，不能由入口直接改余额。
- QQCC 私有 Bot owner 不替访客付费；租户只拥有配置和启停权限。

详见
[认证权限](./子模块_用户认证与权限_user_auth_permission.md) 和
[计费支付](./子模块_计费与支付_billing_payment.md)。

### 3.3 社区与媒体

- 生成 History 是 Gallery 投稿和 apply-context 的来源。
- 投稿、互动、评论、举报、提示词解锁保持数据库幂等与原子计数。
- 正式用户可见媒体使用当前 R2；legacy 对象存储只用于迁移、回滚和旧外链取证。
- 列表媒体解析在释放 DB 事务后执行，并复用 cache/singleflight。

详见 [社区与存储](./子模块_社区与存储_gallery_storage.md)。

## 4. 部署与运行态

- Git 中保存代码、声明式 catalog、artifact contract 和稳定 policy。
- release index/manifest 保存完整 SHA、digest/checksum、OCI revision 和验证证据。
- test/prod 只消费不可变产物与各自逐服务配置投影；云端不 rsync、现场 build
  或源码 bind mount。
- A–H worktree 通过不可变 handoff 进入单批次 main PR；共享 test 只有一个
  写入者，正式 mutation 每次单独确认。
- GPU/LAN/RunPod 当前态来自 provider、Central 和 XDG ledger，不写入本报告。

详见
[不可变发布](./子模块_Git不可变发布_git_immutable_release.md)、
[并发工作区](./子模块_并发AI开发与测试列车_concurrent_ai_workspaces.md)、
[GPU Pool](./子模块_GPU算力资源池控制器_gpu_pool_controller.md) 和
[资源画像](./子模块_系统资源与容量画像_resource_inventory.md)。

## 5. 知识维护

- 全局路由和授权只在 `AGENTS.md`。
- Skill 只保留触发、稳定入口、红线、按需阅读和最小验证。
- 专项文档描述当前契约/SOP；历史、canary、迁移和事故进入 archive/evidence。
- 共享术语进入 `docs/domain/CONTEXT.md`，难逆决策进入 ADR。
- 审计矩阵一份活跃资料一行，不追加变更流水。

任何入口、异常、超时、双 ID、provider、workflow、配置或发布语义变化，都要
同步对应 Skill/专项文档并运行：

```bash
python scripts/doc_quality_checker.py
```
