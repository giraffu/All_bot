# 全系统真实用户旅程验收计划

## 1. 目标与模式

本计划从真实 Web/Bot 提交任务，检查身份、计费、Central/Worker、媒体、社区和通知闭环。自动化测试不能代替它；它也不是压力、故障注入或迁移演练。

| 模式 | 时机 | 范围 |
| --- | --- | --- |
| `FULL-LITE` | 大版本或共享契约变化 | 预检、主干和全部适用切片 |
| `CORE-SPINE` | 发布后快速确认 | 身份、便宜任务、状态/结果、账本、History/媒体 |
| `LOCAL-SLICE` | 边界明确的小更新 | 受影响切片及其上游身份、下游结果和副作用 |

改变双 ID、终态、扣退款、对象耐久语义或影响不明时，升级为 `FULL-LITE`。

默认在测试环境串行执行。重启、配置、迁移、Cloudflare/GPU/LAN 或真实支付需另行授权。本文不包含可直接执行脚本。

## 2. 数据与资源预算

最多使用访客、普通用户、余额不足用户和管理员。Telegram/Web 统一身份应落到同一 `internal_user_id`。素材用无敏感小图和数秒低清视频；特殊素材按需准备。

- 并发为一，前一任务终态并留证后再提交。
- 每种执行契约只做一个最短样本；共享 workflow 别名只验展示和映射。
- 图片充当主干样本；视频按变化的 profile 选代表。
- LTX 2.5、SCAIL、长视频和人物多阶段默认 gated；直接变化且获授权才执行。
- 支付默认只验方案、建单、状态和安全失败；真实履约需沙箱或明确授权。
- 复用结果验 History、Gallery、应用和通知。

开始前限定任务数、灵石和能力族；超预算停止新增任务。预算不是通过标准。

## 3. 预检与停止条件

记录环境、Git SHA、artifact digest、入口、开关、task registry、账号和切片。确认队列、Worker、存储与外部依赖可观测。

release 不明、test 可能进入正式 Worker、账号指向正式支付/对象桶时记 `blocked`。串号/越权、重复任务/扣退款、success 后原件丢失、意外付款、环境混用、OOM/Xid 或长期无终态时立即停止。

## 4. 共享主干 `ACC-SPINE`

1. 从真实 Web 或 Bot 进入，确认用户和权限。
2. 用最便宜图片能力提交一次，记录 `client_request_id`、`registry_task_id` 和可观测的 `backend_task_id`，不得混用。
3. 确认状态按实际经历进入终态；刷新页面或重入会话仍可找到任务。
4. success 只在产物耐久后出现；结果和 History 可回查，签名 URL 不充当永久对象身份。
5. 账本只扣一次；通知与 History 终态一致。
6. 复用结果完成一个无 GPU 下游读取并记录清理决定。

## 5. 入口与任务切片

### `ACC-ENTRY` 公共 Web、鉴权和权限

- 公共页、运行时配置、导航与能力可见性正确。
- Telegram/Web 登录、密码绑定/版本失效和 JWT 续用符合契约。
- 访客、过期凭据和无权资源被安全拒绝。
- Telegram/Web 身份统一；不同用户不串 `internal_user_id`。

### `ACC-TG` Telegram 主 Bot/FSM

- `/start`、菜单、签到/队列和语言正常。
- 各类素材进入正确状态；错误输入可恢复。
- callback 不重复；全局取消退出 FSM 并清临时素材。
- 提交反馈和终态通知与 Web、History 一致。

### `ACC-QQCC` 官方与私有 Bot

- 快捷生成、Wan、Gallery 只展示启用能力。
- 私有 Bot 的 owner、访客任务、计费和 webhook 不串租户。
- 官方/私有更新入口不重复消费。正式专属 Bot 仅有隔离 token/环境时执行，否则 gated。

### `ACC-TASK` 状态、取消和恢复

- 合法响应统一；非法参数、余额不足、并发限制和隐藏能力返回正确错误。
- 相同 `client_request_id` 重试不重复生成/扣费。
- 可稳定制造 pending 时验取消、锁释放和一次退款；否则记 blocked。
- running 取消区分“已请求”和执行端确认，不提前退款。
- success/failed/cancelled 与 History fallback 在 Web、轮询/SSE、Bot 一致；恢复查看不新建任务。

## 6. 执行与 AI 能力切片

### `ACC-EXEC` Central、Worker、R2

从用户侧确认 Central 选对 profile、claim 不重复；Worker 使用快照对应的 workflow/模型，patcher 不伤非目标节点。产物耐久后才 success；失败补偿正确，不留长期任务或孤儿 staging。

### `ACC-CAPABILITY` 代表能力

运行时 task registry、入口可见性和 Worker profile 是当次事实源：

| 能力族 | `FULL-LITE` 默认代表 | 增加样本条件 |
| --- | --- | --- |
| 文生图/单图编辑 | 最便宜模式各一 | workflow 同时变化 |
| 多图/LoRA/ControlNet | 一个模式 | 素材槽/模型变化 |
| 换脸 | 主入口一个 | 图片/视频链分别变化 |
| Wan 视频 | 最短视频 | profile/时长变化 |
| LTX | I2V 一个 | 其它子图变化 |
| MiniMax H3 | 改变模式一个 | 独立子图变化 |
| 多阶段/高清化/SCAIL | gated | 直接变化且获授权 |

别名有独立计费、素材、状态或后处理才算独立契约。

### `ACC-PROMPT` 提示词优化

文本/媒体能创建任务，profile/template revision 与快照一致；文本结果不误入 History/R2/Gallery，只扣一次。异常有明确终态，应用到生成入口时仍可确认 prompt 和费用。

## 7. 业务数据切片

### `ACC-BILLING` 计费、会员、支付、返佣

- 余额、账本原因、task reference 和价格一致；补偿只发生一次。
- 余额不足不能提交；重试/回调不重复入账。
- 签到、会员、affiliate 仅在受影响时用专用关系验证。
- 真实渠道履约默认 gated。

### `ACC-GALLERY` 社区

复用结果投稿并确认个人页/feed；在测试帖上验证赞踩切换、收藏、评论、举报和本人删除。提示词只解锁扣费一次；一键应用携带正确 context，生成独立任务。审核只操作测试内容。

### `ACC-MEDIA` 上传、History、归档

- 预签上传限制用户、类型、大小和 key；他人不能读私有对象。
- 原件、缩略图和 History 在签名刷新后仍可定位，数据库不保存临时签名 URL。
- success 时原件已耐久；缺失不能伪装成功。
- 删除、恢复、迁移和冷清理需授权；默认只读。

## 8. 管理与独立平台

### `ACC-ADMIN`

Dashboard 能读到测试用户、任务、账本、History、Worker 和 Gallery，权限正确。QQCC 配置用草稿验预览；通知、封禁、改余额、RunPod 和发布默认不执行。

### `ACC-INDEPENDENT`

- 3D Mini App：fixture、预览、CPU 路径；GPU provider gated。
- 媒体增强：登录、上传、点数、task/attempt、结果和补偿。
- LAN 资源平台：只读 current/cache/drift；takeover/recover 另授权。
- LAN 图库：白名单目录、缩略图和原件只读，不扩目录。
- 本地分析：新鲜度、核心统计、任务/账本口径；写入限测试数据。
- 媒体归档：目录/恢复状态只读；恢复、迁移、冷清理另授权。
- Support、付费群、群管理、Observer：有隔离 Bot/群才验，否则 gated。

`ACC-INFRA` 只通过用户结果观察 PostgreSQL、Redis、Central、R2/imgproxy 和 Telegram Local API；故障转移、恢复和容量另行演练。

## 9. 全量顺序与局部选择

`FULL-LITE` 顺序：预检 → 身份/Web → 主干图片 → Telegram/QQCC → 改变的图片/视频 profile → Prompt → 余额不足/幂等/安全取消 → Gallery/媒体/通知复用 → Dashboard/分析/独立平台读取 → 经授权的 gated 项 → 清理核账。

| 改动 | 必选切片 | 条件追加 |
| --- | --- | --- |
| Web 样式/文案 | `ENTRY` 受影响页 | 契约未变可免 GPU |
| JWT/权限 | `ENTRY`、`SPINE` | Bot/管理身份 |
| Task/Central/状态机 | `SPINE`、`TASK`、`EXEC`、`BILLING`、`MEDIA` | 图片及受影响视频 |
| workflow/model/patcher | `EXEC`、`CAPABILITY`、`MEDIA`、`BILLING` | 每个改变 profile 一个任务 |
| Telegram/QQCC | 对应 Bot、`TASK` | 通知、文件或租户 |
| 账本/支付 | `BILLING`、`ENTRY`、`SPINE` | 渠道履约 gated |
| Gallery/R2/History | `GALLERY`、`MEDIA` | 复用已有结果 |
| Dashboard/独立平台 | 对应子项 | 共享身份/任务/存储 |
| schema/env/发布 | 预检、`SPINE`、受影响域 | migration 另授权 |

## 10. 判定、证据、清理

状态只有 `pass`（入口、状态、副作用和证据均符合）、`fail`（可复现漂移）、`blocked`（依赖/容量/数据/授权缺失）、`not-applicable`（环境无该能力）。跳过不算通过。

每条记录包含 release/环境、用例、入口、脱敏 actor/双 ID、task type、状态时间、Worker/profile、结果引用、余额、通知、清理和判定。失败补最小复现。总报告汇总任务数、灵石、GPU 能力族和风险；关键项失败、阻塞或 gated 时不得写“全系统通过”。

结束时取消测试任务，删除测试社区数据，核对无意外未终态或 staging。账本不得人工调平；保留证据须标记。新经验修正切片和判定，不追加日期流水或执行脚本。
