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
| 执行运行时 | 输入下载、workflow patch、ComfyUI、结果回报 | canonical `workers/comfy_agent/`；LAN/RunPod 仅保留运行 adapter/config |
| 管理与运维 | Dashboard、独立模块发布、GPU/LAN/RunPod operator | `dashboard/`、`scripts/release.py`、`deploy/module-catalog.json`、`ops/` |

正式与测试环境都只消费精确、不可变的 artifact，但不要求两者天然使用同一
digest；目标 artifact 由操作者按模块和环境明确选择。数据库、Redis、token、
bucket、域名和开关由目标环境逐服务配置投影提供。

## 2. 分层边界

### 2.1 Core

目标边界是：`src/core/` 只使用内部 request/context、domain config 和显式
provider/dependencies，平台入口先转换为 `internal_user_id`。新代码不得把
Telegram `Update`、FastAPI `Request/APIRouter` 或基础设施 session 带进 core。

AST 门禁已禁止 `src/core/` 直接导入 `config`、`httpx`、PIL、SQLAlchemy、
`src.database`、`src.services`、FastAPI 和 Telegram。媒体路径与处理实现已迁到
`src/media_paths.py`、`src/media_processor.py`，SQLAlchemy 异常识别和 Redis key
操作由外层 adapter/capability 注入。Web、主 Bot、QQCC 和 Dashboard 启动入口
显式装配 `TaskApplication`；生产提交只使用 command/policy/journal。旧宽 facade
仅保留为强制显式 dependencies 的测试/兼容入口。部分 runtime builder 仍会延迟
导入基础设施 provider，因此不能把“core 已无间接基础设施装配”当成现状。

### 2.2 入口与服务

- Telegram FSM 只负责平台状态、素材、回复和清理，任务计划进入 application
  service。
- Web router 保持薄，展示转换进入 presenter/service；对象存储探测不能与
  长数据库事务混合。
- `backend/app` 是 Central/Worker 执行面，不是普通 Web/BFF。用户 API 主入口
  是 `src/web_api`。
- Dashboard 编排管理视图，但不复制 QueueManager、billing 或 Gallery 的
  底层业务语义。
- `task-control-worker` 是默认禁用的独立后台宿主；submission reconciliation、
  Web finalizer 和通用 zombie sweep 各自持有 leader lease。旧 Web/Bot/QQCC
  loop 默认仍开启，只有显式滚动切换后才退出原宿主。

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
- 投稿、互动、评论、举报、提示词解锁以数据库幂等与原子计数为目标；当前
  Gallery 投稿/like-dislike 的仓库迁移约束仍有缺口，不能只依据 ORM
  `UniqueConstraint` 假定所有环境已强制不变量。
- 正式用户可见媒体使用当前 R2；legacy 对象存储只用于迁移、回滚和旧外链取证。
- 列表媒体解析在释放 DB 事务后执行，并复用 cache/singleflight。

详见 [社区与存储](./子模块_社区与存储_gallery_storage.md)。

### 3.4 当前演进边界

- Web dispatch 已使用版本化 submission intent 区分确定拒绝与结果歧义；
  `dispatching/reconciling` 不猜测退款，恢复需满足连续 Central 404 门槛。
- Gallery 修复工具、partial unique indexes、advisory transaction lock 与计数重算
  已形成代码契约；真实环境修复仍必须先备份、dry-run 并单独授权。
- Worker runtime 已收口到 `workers/comfy_agent`，镜像 manifest 暴露源码与
  workflow mapping hash；任何 GPU profile rollout 仍需逐 profile canary。
- 后台职责的独立进程已作为 disabled artifact 交付，但环境启用、旧 loop 关闭
  和服务部署不是代码提交的隐式动作。

## 4. 部署与运行态

- Git 中保存代码、声明式 catalog、artifact contract 和稳定 policy。
- release index/manifest 保存完整 SHA、digest/checksum、OCI revision 和验证证据。
- test/prod 只消费不可变产物与各自逐服务配置投影；云端不 rsync、现场 build
  或源码 bind mount。
- A–H worktree 通过不可变 handoff 进入本机 main 单写者；协调器逐项合并并
  push main，不创建 PR、不运行 CI、不构建或部署环境。
- 操作者从完整 SHA 独立构建明确模块，再把精确 digest 部署到 test 或 prod；
  focused tests 和 test 人工结果不构成发布器资格状态。
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
python3 scripts/doc_quality_checker.py
```
