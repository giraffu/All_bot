# Compat / Seam 当前退出表

机器可校验的事实源是 `config/compat_registry.json`：每个条目必须包含入口、
owner、telemetry key、替代入口、无命中观测窗口和历史数据退出条件。
`scripts/validate_compat_registry.py` 验证 schema、唯一性和声明为
`compat_hit_log` 的真实埋点。本表只是人工导航摘要，不重复机器字段。

本表只跟踪仍在运行或仍需运行态确认的兼容层。已删除、已下沉和已完成条目
保存在
[`docs/archive/knowledge-base-cleanup-20260727/`](archive/knowledge-base-cleanup-20260727/)，
不再进入默认上下文。

## 状态定义

- `active-compat`：仍有受支持调用方或历史数据，暂不能删除。
- `runtime-verification-required`：代码调用已收敛，但需环境/数据观测后删除。
- `test-seam`：有明确 fake/环境差异，作为可替换 seam 保留。

## 当前条目

| 对象 | 状态 | 责任域 | 运行时调用方 | 当前用途 | 退出信号 | 最近复核（静态） |
| --- | --- | --- | --- | --- | --- | --- |
| `image_to_video_fsm.start_custom_video` | active-compat | TG FSM | `/custom_video`、旧菜单与 callback handler | 保持已发消息和旧入口可达 | 产品入口与已发 callback 不再使用旧名 | 2026-07-27 |
| Web task status SSE route | active-compat | Public Web | 旧 Web/第三方客户端 | 保留旧实时状态协议；官方 Web 已用 polling | `compat.web.task_status_sse` 连续 30 天无命中 | 2026-08-18 |
| `MODE_IMAGE_TO_VIDEO = MODE_VIDEO_LORA` | active-compat | Task engine | task constants、提交与 History 恢复 | 归一历史任务值和 payload | 数据与调用方全部改用 canonical type | 2026-07-27 |
| QQCC Wan22 单模型字段与旧模型名 | active-compat | QQCC | `qqcc_config_service`、quick-video continuation | 读取升级前场景和 payload | 官方/私有配置迁移且观察窗口无旧字段 | 2026-07-27 |
| QQCC `next_scene_id` 容错归一 | active-compat | QQCC | `qqcc_config_service`、`qqcc_video_scene_chain_service` | 安全加载旧或损坏配置 | 支持中的 checkpoint 重存且回滚点退出 | 2026-07-27 |
| `video_insert` / `video_edit` | active-compat | Task engine | Central simple routes、task registry、Worker mapping | 接受旧 endpoint、队列和 worker alias | 队列与访问日志确认旧类型清零 | 2026-07-27 |
| Central legacy media completion | active-compat | Task engine | 未携带 `result_asset` 的旧 Worker | 在显式配置门禁内完成旧媒体任务 | 所有媒体 Worker 使用资产契约、门禁关闭且遥测连续 30 天为零 | 2026-09-06 |
| Order 历史内部用户列语义 | runtime-verification-required | Billing/Auth | Order ORM、支付创建与校验 service | 兼容生产 schema 的历史身份列 | 目标 migration/head 与 ORM 契约一致 | 2026-07-27 |
| `ORDER:` / `ORDER_V2:` 双载荷 | active-compat | Billing | `order_v2_service`、`payment_validator` | 解析旧支付 callback | 旧通道和展示调用方完全退出 | 2026-07-27 |
| legacy user adopt 分支 | runtime-verification-required | Identity | `user_persistence_service` | 收口早期内部 ID/TG ID 混用记录 | 数据审计确认无可收养历史用户 | 2026-07-27 |
| Gallery `free_edit_v2_group` 查询别名 | active-compat | Gallery | `gallery_feed_queries`、前端展示映射 | 服务升级前客户端 | 支持中的客户端只发送 v3 group 且日志清零 | 2026-07-27 |
| Gallery History owner fallback | runtime-verification-required | Gallery | `gallery_history_link` | 为 `history_id=NULL` 的旧帖子按 `(task_id,user_id)` 安全读取 | 活跃帖子外键补齐、歧义行处理完且遥测连续 30 天为零 | 2026-09-06 |
| `process_and_submit_task` callback facade | runtime-verification-required | Task engine | 兼容测试/集成调用 | 旧宽签名适配到 `TaskApplication` | 测试迁移且生产调用点持续为空 | 2026-09-06 |
| 宽成功持久化 facade | active-compat | Task engine | `task_service_completion`、兼容测试 | 适配 `TaskSuccessPersistenceCommand` | 生产调用和测试迁移到 command seam | 2026-09-06 |
| Web finalizer legacy Hash index | active-compat | Task engine | task-control-worker | 将旧 Hash 记录补入 due-time ZSET | 存量记录耗尽且 indexed metric 连续 30 天为零 | 2026-09-06 |
| presign hours 字段接收秒值 | runtime-verification-required | Gallery/Storage | 历史调用点 | 兼容大于 24 的秒数参数 | 调用点改为显式单位且旧签名 URL 全部过期 | 2026-09-06 |
| QQCC `buttons_per_row=null` | active-compat | QQCC | config normalization、Bot 菜单渲染 | 旧 checkpoint 固定分行 | 官方/私有配置迁移为显式列数 | 2026-07-27 |
| provider/dependencies fake | test-seam | Architecture/Test | public facade focused tests、环境 adapter | 替换外部行为而不改调用点 | 有价值的测试 seam，不进入兼容退出 | 2026-07-27 |

## 维护规则

- 新兼容层先登记 `config/compat_registry.json`，再写代码；门禁会拒绝
  只新增 `compat/legacy/alias` 标记却没更新 registry 的变更。
- `compat_hit_log` 只记 telemetry key 和入口，不记用户 payload、token、
  object key 或 callback 原文。普通文本 formatter 与 structured logger 都必须输出
  `event=compat_hit`、`telemetry_key` 和入口，避免出现无法归属的命中记录。
- 已删除代码不留在活跃表；删除证据进入归档或 Git 历史。
- 只有静态 `rg` 不足以删除数据/协议兼容；必须同时满足 registry
  中的连续无命中窗口和 `historical_data` 条件。
- 测试 seam 只有在 fake、环境差异或可替换 adapter 存在时保留；仅一行转发
  且无 interface 价值的浅壳应删除。
- 完成退出后同步专项文档、Skill 和审计矩阵，并运行 focused tests。
