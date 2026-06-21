# AllBot Domain Context

本文件是 AllBot 的共享领域词汇表，只记录术语含义，不记录实现方案、部署步骤、事故流水或代码细节。具体实现仍以对应 `.codex/skills/*/SKILL.md` 与 `/docs/子模块_*.md` 为准。

## 用户与身份
- **internal_user_id**：AllBot 内部统一用户标识。核心层只使用该标识流转，不直接依赖 Telegram、Web 或第三方平台对象。
- **Telegram user id**：Telegram 平台用户标识，只在 Bot 表示层、登录验签、付费群审核等适配层出现。
- **password_version**：用户密码会话版本。改密后用于让旧 token 失效。
- **会员身份**：用户权益状态，由支付履约、后台赠送或 affiliate 兑换等结算路径改变。

## 资产与商业化
- **灵石**：AllBot 内部消耗型余额，写入和转移必须通过账本入口，不能绕过审计。
- **支付履约**：把 RMB、TON、Telegram Stars 等外部支付结果转换为灵石、会员或 affiliate 副作用的幂等结算过程。
- **Affiliate 余额**：推广返佣余额，可兑换灵石或会员权益，必须保留流水。
- **标准邀请奖励**：邀请关系带来的阶段性灵石奖励，按注册、入群、首次生成阶段补差额。

## 生成任务
- **registry_task_id**：AllBot 运行态注册表中的任务 ID，面向 Web/Bot 查询、取消、历史和权限语义。
- **backend_task_id**：执行面任务 ID，面向 Central API、QueueManager、worker pop/status/complete/cancel 等执行语义。
- **生成任务主链**：从 Web/Bot 提交，经 task core、Central、worker、ComfyUI、结果回流、历史持久化和媒体可见化形成的一条业务链。
- **Web side-effect monitor**：Web 提交成功后的异步收口者，负责成功历史、失败退款、取消退款和 runtime cleanup。
- **任务黄金路径**：最小但端到端可验证的成功/失败/取消/结果可见回归集合。

## 媒体与社区
- **Gallery 投稿**：用户把可公开的 History 结果发布到社区广场的行为。
- **apply-context**：从 Gallery 帖子还原可复用生成上下文的服务端入口。
- **提示词解锁**：用户消耗灵石查看完整 prompt，并给作者入账的幂等交易。
- **R2 可见热集**：Web/Gallery/History 用户可见媒体在 R2 中应可读的对象集合。
- **legacy MinIO**：历史对象存储兼容来源，只保留迁移、回滚和旧外链排障语义。

## 执行与运维
- **Worker Agent**：从 Central 拉取任务、准备输入、调用 ComfyUI、上传结果并回报状态的进程。
- **ComfyUI Runtime**：实际加载模型并执行 workflow 的运行时，可以是宿主机、LAN AIO 或 RunPod 容器。
- **workflow 事实源**：当前运行时 workflow 资产以 `workers/comfy_agent/workflows` 和同步后的 `remote_workers/` bundle 为准。
- **LAN AIO**：局域网 GPU 上的 all-in-one runtime 形态，将 ComfyUI、relay/agent 和模型同步收在受控容器链路里。
- **RunPod 手动池**：云正式备用或临时扩容的手动 GPU worker 池，默认不自动按生产队列扩容。
- **云测试控制面**：研发、联调、缺陷修复和配置验证的默认发布目标。
- **云正式控制面**：生产控制面，任何正式发布、重建或生产 RunPod mutation 都需要用户明确确认。

## 架构词汇
- **Module**：有 interface 和 implementation 的能力单元。
- **Interface**：调用方必须知道的完整使用契约，不只是类型签名。
- **Seam**：可以替换行为而不改调用点的位置。
- **Adapter**：填入 seam 的具体实现。
- **Deep module**：小 interface 承载较多行为，让调用者少知道、维护者集中修改。
- **Provider/dependencies seam**：AllBot core 层和测试优先使用的显式依赖注入方式。
