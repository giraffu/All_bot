# AllBot 系统模块、依赖与扩展地图

本文是跨模块设计的 canonical 导航图，按“用户入口、核心业务、任务执行、AI
能力、管理监控、独立平台、基础设施”七个板块描述稳定职责。具体业务规则仍以
领域代码、对应 Skill 和专项文档为准；worker 数量、节点占用、部署版本与迁移
进度属于运行态，不在本文固化。

## 1. 总体链路与控制边界

```text
Telegram / Public Web / 独立 Bot
              │  平台身份、素材、展示协议
              ▼
       Web API / Bot adapters
              │  internal_user_id + domain command
              ▼
 Core / application services ── 账本、History、Gallery、submission intent
              │  registry_task_id ↔ backend_task_id
              ▼
       Central API / QueueManager
              │  claim、heartbeat、status、complete、cancel
              ▼
 Worker Agent / Prompt Worker / Relay ──► ComfyUI / model provider
              │                              │
              └──────── result asset ────────┘
                             ▼
                    R2 / History / archive
                             ▼
                 Web polling / Bot completion
```

系统同时存在三条不同的边界，不能按“都是 API”或“都是任务”强行合并：

- 用户面：认证、权限、展示、输入收集和用户可理解的错误；主入口是 Bot/Web。
- 业务面：任务、计费、社区、媒体与状态补偿；公开 seam 是 core facade、application
  service 和显式 provider/dependencies。
- 执行面：Central 队列、Worker 协议、workflow 与 GPU；使用 backend task ID 和
  执行状态，不直接决定用户资产或身份。

## 2. 用户入口

| 模块 | 稳定职责 | 代码入口 | 下游与边界 |
| --- | --- | --- | --- |
| Telegram 主 Bot | 菜单、FSM、素材收集、callback、任务完成通知 | `src/bot_main.py`、`src/handlers/main_bot_handler_registry.py` | 将 Telegram 身份映射为 `internal_user_id`；不在 handler 内复制扣费、退款或队列状态机 |
| 公共 Web | 登录、工作台、Gallery、历史、资产与任务展示 | `frontend/src/` | 只消费 Web API；运行时配置先于 Router/Pinia/API transport 装配，任务主路径使用 polling |
| Web API | 用户 BFF、JWT、任务、History、Gallery、上传和支付展示面 | `src/web_api/main.py`、`src/web_api/routers/` | router 保持薄；业务进入 core/service，不能承担 Worker 协议或 QueueManager 内部状态 |
| QQCC 官方 Bot | 官方场景配置驱动的快捷生成与 Gallery 轻入口 | `qqcc_bot/main.py` | 复用统一身份、计费和任务 facade；场景配置不是新的任务状态机 |
| 用户私有 Bot | 多租户 webhook、owner 配置与访客任务归属 | `qqcc_private_bot/worker.py`、`src/web_api/routers/private_bots.py` | owner 只拥有配置/启停权限，不能替访客付费；token 和 webhook secret 属于凭据边界 |
| 客服 Bot | 工单收集、通知、回复与状态流转 | `support_bot/main.py`、`src/services/support_ticket_*` | 独立 Bot 生命周期；业务记录通过服务层与 Dashboard 协作 |
| 付费群审核 Bot | 入群资格读取、申请处理与轻量审核 | `paid_group_guard_bot/main.py` | 只读用户/订单资格，不执行支付履约或直接修改资产 |
| 群管理 Bot | 独立群消息治理与管理命令 | `standalone_group_manage_bot/main.py` | 与主 Bot/FSM 隔离，避免 handler 与 token 串用 |

入口新增能力时，先判断调用者身份、权限、ID、错误语义和副作用。用户功能默认
进入 Web API 或相应 Bot adapter；只有 Worker/Central 协议进入 `backend/app`。

## 3. 核心业务

| 能力 | 事实源与公开 seam | 持久状态 | 关键不变量 |
| --- | --- | --- | --- |
| 用户认证与权限 | `src/core/auth_core*`、`src/services/auth_user_repository.py`、`src/web_api/services/auth_api_service.py` | users、身份绑定、`password_version` | Telegram/Web/私有 Bot 最终统一为 `internal_user_id`；改密使旧 JWT 失效 |
| 任务提交与状态 | `src/core/task_application.py`、`TaskSubmissionCommand/Policy`、`SubmissionJournal` | active task、submission intent、History | `registry_task_id` 与 `backend_task_id` 不混用；提交歧义进入 reconciliation，不提前退款 |
| 取消、恢复与退款 | `src/core/task_core_finalization.py`、task control services | 终态、退款账本、due index | 终态与退款幂等；取消需要区分排队、运行和已完成竞态 |
| 计费、支付、会员、返佣 | `src/core/billing_core*`、`src/billing_core_provider_setup.py`、payment/affiliate services | 灵石账本、订单、会员、affiliate ledger | 入口不能直接改余额；履约、退款、返佣有唯一业务键和可重放结果 |
| Gallery 社区 | `src/core/gallery_*`、`src/services/gallery_*`、`src/web_api/services/gallery_*` | post、interaction、comment、report、unlock | 投稿通过 `history_id` 绑定来源；互动使用数据库唯一约束/原子计数；legacy owner fallback 仅是登记兼容 |
| 媒体与对象存储 | `src/core/media_urls.py`、`src/services/storage*`、History/media resolver | R2 key、History、thumbnail、archive outbox | DB 事务与远端探测分离；持久 key 可恢复，预签 URL 只是短期展示值 |
| Telegram FSM | `src/handlers/fsm/`、handler registry、lifecycle supervisor | Telegram conversation/user data、临时文件 | 全局退出可达；callback 唯一注册；临时文件最终清理；语言同步不污染业务 core |
| 提示词优化 | `src/prompt_optimizer/`、`src/web_api/services/prompt_optimization_service.py`、`workers/prompt_optimizer/` | profile/template ref、hash、文本结果 TTL | 提交固定 profile/template 版本与 hash；媒体 ownership/大小由 `prompt_media_policy.py` 统一校验 |

Core Isolation 是硬边界：`src/core/` 只依赖内部类型和显式 capability，不接收
Telegram `Update`、FastAPI `Request/APIRouter` 或 SQLAlchemy/HTTP/R2 实现对象。
provider 注册由各应用入口完成，core import 不应产生运行时装配副作用。

## 4. 任务执行

| 模块 | 职责 | 入口/事实源 | 失败与恢复边界 |
| --- | --- | --- | --- |
| Central API | Worker 认证、任务领取、状态/完成回写、系统执行视图 | `backend/app/main.py`、`backend/app/routers/agent.py` | 不直接履约用户资产；完成事件由业务 finalizer 持久化 |
| QueueManager | pending/running、heartbeat、取消、zombie 和 worker 视图 | `backend/app/queue_manager.py` | Redis 是执行态；History/账本才是业务持久事实 |
| Task Control Worker | submission reconciliation、Web finalizer、zombie sweep 的独立宿主 | `src/task_control_worker.py`、`src/services/task_control_worker.py` | 每项服务独立 leader lease；环境切换前旧宿主仍可能保留 |
| ComfyUI Worker Agent | 输入准备、workflow patch、Comfy 执行、结果物化、上传和回报 | `workers/comfy_agent/agent_main.py` 及 phase modules | agent 是 lifecycle shell；阶段 helper 不反向拥有计费/用户状态 |
| Prompt Optimizer Worker | 多模态输入解析、provider 调用、结构化文本结果 | `workers/prompt_optimizer/worker_main.py` | 只执行固定的 profile/template snapshot |
| Worker Relay | Central 与受限 LAN/RunPod 节点间的任务/状态桥接 | `workers/local_relay/relay_main.py`、`workers/runpod_runtime/runpod_relay/relay_main.py` | relay 不改变任务语义；鉴权、租约和重复回报必须可重试 |
| RunPod/LAN GPU | 承载 profile 对应的 ComfyUI/Worker artifact | `src/domain_config/worker_pool_registry.py`、`deploy/module-catalog.json`、fleet/provider ledger | Git 只保存声明式能力；实际节点、占用和 current/cache 从实时 provider/XDG 读取 |

### 4.1 状态与 ID

- `registry_task_id`：业务注册身份，用于 active task、账本、History 和用户查询。
- `backend_task_id`：Central 执行身份，用于 pending/running、Worker status 和 cancel。
- `client_request_id`：入口幂等键，不替代任一任务 ID。
- 多阶段任务保留一个根业务身份；阶段 ID、continuation/checkpoint 是内部执行细节。
- `dispatching/reconciling` 表示提交结果尚不确定，只有获得确定终态才能结算或退款。

## 5. AI 生成能力

能力目录不是分散在菜单或 worker `if` 分支中的手写列表。跨层 canonical 事实由
`src/domain_config/task_type_registry.py`、`task_pricing_catalog.py`、
`worker_pool_registry.py`、`workers/comfy_agent/workflows/mappings.json` 和 module
catalog 共同形成，并由契约测试检查。

| 能力族 | 公开任务/模式示例 | 执行特点 |
| --- | --- | --- |
| 图像生成与编辑 | img2img、LoRA、i2i_pro、文本生图、多图编辑 | 输入图片 ownership、prompt/LoRA 归一化后映射到图像 profile |
| 换脸与视频换脸 | face_swap、face_swap_v2、SCAIL-2 face swap | 人脸/视频素材校验、音频和结果资产类型由 workflow contract 决定 |
| Wan 图生视频 | `wan22_video_v2` 及兼容别名 | 分辨率、时长、LoRA 和链式 History 由领域配置统一归一化 |
| LTX 视频 | I2V、FLF2V、V2V audio、T2V 与人物一致性 | 人物/环境引用、首尾帧和两阶段 workflow 使用专用 domain config |
| LTX 2.5 高清化 | `ltx25_video_upscale` | 输入视频探测、目标尺寸、时长和价格由同一 plan 计算 |
| MiniMax H3 | T2V、I2V、FLF2V、REF2V | 四模式、参考图/视频、模型与附加项由 `minimax_h3.py` 约束 |
| 提示词优化 | `prompt_optimize` | 走独立文本 Worker，结果不是媒体 History 的替代物 |

新增模型能力必须完成一条纵切：领域注册与价格 → Bot/Web schema/输入 → task
facade → Central allowlist → worker profile/mapping/patcher → 结果资产 → History/Gallery
策略 → i18n/管理展示 → focused tests。只增加 workflow JSON 不构成完整能力。

## 6. 管理和监控

| 模块 | 稳定职责 | 边界 |
| --- | --- | --- |
| Dashboard | 用户、资产、订单、任务、worker、Gallery、客服和运营管理 | `dashboard/backend/` 聚合稳定 service；`dashboard/frontend/` 不复制底层状态机 |
| QQCC 配置后台 | 官方/私有场景、菜单、模型和链路配置 | `dashboard/backend/qqcc_config_main.py` 与对应前端；保存前完成 canonical normalization |
| Observer Bot | 管理通知、队列/Worker 告警、授权群采集和周期报告 | `observer_bot/` 独立进程、独立 token/逻辑库；不注册用户业务 handler |
| GPU Pool | profile、供给、节点/slot 调度和 LAN/RunPod adapter | `ops/gpu_pool_controller/`；声明式 catalog 与实时 ledger 分离 |
| 日志监控 | health、metrics、trace、日志采集与事故分诊 | 只读观测不自动授权重启、扩缩、取消或发布 |
| 任务清理 | finalizer、zombie、临时对象和过期状态清理 | 清理必须幂等、有租约，并区分执行态垃圾与业务历史 |

## 7. 独立平台

| 平台 | 目录/入口 | 与主系统关系 |
| --- | --- | --- |
| 3D 角色 Mini App | `avatar_miniapp/`、`src/avatar_miniapp/` | 独立 LAN 容器、fixture/GLB/VRM 与 CPU Blender 渲染；未来 GPU provider 通过 seam 接入 |
| 媒体增强平台 | `media_enhance_platform/` | 独立鉴权、点数账本、媒体生命周期、task/attempt 与 Worker HTTP contract，不复用 AllBot 用户账本 |
| LAN 资源管理平台 | `lan_resource_manager/` | 展示/操作 A–H、构建 runner 和 LAN 资源；mutation 仍受专用 operator/发布门禁 |
| 局域网图库 | `lan_media_gallery/`、`ops/icloud_photos_gallery_nas/` | 只读浏览与单向备份，不成为 AllBot R2/History 的业务写入口 |
| 本地数据分析平台 | `local_analytics_platform/` | 消费主库/shadow 派生数据；分析表与缓存不能反向成为交易事实源 |
| 提示词语义分析 | local analytics prompt routes/materializers | 词元、同义映射和模板候选治理；语义人工决策与刷新运行态分离 |
| 媒体归档系统 | `src/services/media_archive_*`、`ops/media_archive_*` | History 全量目录、archive/restore outbox、NAS MinIO 与 R2 冷清理门禁 |

独立平台默认拥有自己的入口、状态和部署单元。只有确有共享不变量时复用窄协议
或领域配置，避免直接导入主 Web router、Telegram handler 或主系统数据库 session。

## 8. 基础设施与发布

| 能力 | Canonical 事实源 | 约束 |
| --- | --- | --- |
| PostgreSQL | SQLAlchemy models、`migrations/versions/` | schema 变化必须 Alembic；运行时只支持 PostgreSQL |
| Redis | task/billing service key builders、Central QueueManager | 业务 Redis 与 Worker Redis 的 URL/前缀不可混用 |
| R2 / imgproxy | storage/media services、module catalog | R2 保存持久对象；imgproxy 只做派生展示；预签 URL 不入持久事实 |
| Telegram Local API | Bot runtime bootstrap、compose contract | 文件端点和 Bot API endpoint 必须成对配置并按环境探测 |
| Cloudflare | DNS/Tunnel/Access/Pages/R2 配置与实时 API | Git 文档不证明实时 DNS、路由或 token 状态；任何 mutation 单独授权 |
| 不可变发布 | `deploy/module-catalog.json`、`scripts/release.py` | 从完整 SHA 本地构建，目标环境消费 digest-pinned artifact |
| A–H 工作区 | `scripts/manage_ai_workspaces.py` | 功能槽 claim → focused tests → commit/push → handoff；main 单写者集成 |

## 9. 当前治理结论与优先级

本轮全量静态审计确认：Core 直接依赖门禁正常，主链路具备明确 facade 和 provider
seam；主要风险已经从“入口完全混杂”转为“大型应用服务/Worker 函数复杂、跨层
导入环、兼容 seam 退出依赖运行态证据、独立平台测试隔离不足”。

| 优先级 | 现状 | 治理策略 |
| --- | --- | --- |
| High | task/service/web 仍形成大型 import SCC；Worker patcher、视频 plan、本地分析路由复杂度高 | 每次只沿一个公开行为切片提取 policy/phase seam，并用 focused tests 缩小 SCC；禁止机械拆文件 |
| High | 兼容 registry 中仍有 active/runtime-verification 项 | 只能按 telemetry、历史数据和观测窗口退出，不能凭静态“无调用”删除 |
| Medium | 根测试曾收集多个独立平台的同名测试模块并隐式连接本地 PostgreSQL | 根 `pytest.ini` 固定 `tests/` 与 importlib；外部服务测试显式标记 integration 并由环境 opt-in |
| Medium | Dashboard 与本地分析仍有超大 Vue/route 文件 | 按页面 capability、query command 和 presenter seam 纵切，不创建一行转发壳 |
| Low | 零散未使用 import、过期 A/B canary 和 stale test whitelist | 静态门禁持续清理；一次性 canary 进 evidence/archive，不留作长期入口 |

本轮已将 prompt 媒体 ownership/大小规则抽为 `prompt_media_policy.py`，消除 Prompt
Optimization 与 Reference Asset 的直接循环依赖；将 Web 提交输入晋升提取为独立
phase helper；删除与当前 LTX 人物一致性契约冲突且无外部引用的旧 A/B canary。

## 10. 后续扩展检查清单

1. 先选唯一业务 owner 和入口 adapter，定义 `internal_user_id`、业务 ID 与幂等键。
2. 把权限、价格、输入和状态不变量放进领域配置/core，不复制到 Bot/Web/Worker。
3. 通过小而深的 command/provider seam 连接基础设施；入口负责装配 adapter。
4. 明确提交歧义、超时、取消、重试、退款、结果上传失败的补偿路径。
5. 更新 task type、price、worker profile、workflow mapping、i18n 与管理展示事实源。
6. 先补 public facade/API/FSM/provider 行为测试，再补少量集成/运行时 canary。
7. 新兼容分支先登记 `config/compat_registry.json`；一次性迁移代码写退出条件。
8. 同步领域 Skill、专项文档、本文导航和知识矩阵，运行文档与契约检查。

更细入口归属见[入口职责矩阵](./入口职责矩阵_entry_responsibility_matrix.md)，
任务闭环见[生成任务全链路](./子模块_生成任务全链路_task_full_chain.md)，发布边界见
[Git 不可变发布](./子模块_Git不可变发布_git_immutable_release.md)。
