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
- **关注关系**：用户对其他创作者建立的社交连接；“我的关注”按 follower 方向查询，“我的粉丝”按 followee 方向查询，粉丝列表中的已关注状态表示当前用户是否回关。
- **apply-context**：从 Gallery 帖子还原可复用生成上下文的服务端入口。
- **提示词解锁**：用户消耗灵石查看完整 prompt，并给作者入账的幂等交易。
- **R2 可见热集**：Web/Gallery/History 用户可见媒体在 R2 中应可读的对象集合。
- **legacy MinIO**：历史对象存储兼容来源，只保留迁移、回滚和旧外链排障语义。

## 数据分析
- **本地数据分析平台**：独立于正式 Dashboard 的本地/LAN 只读分析服务，面向 shadow 数据做用户、灵石、充值、生成、提示词和媒体引用分析。
- **shadow 数据库**：从云正式数据同步到本地的只读分析/灾备数据库副本，不是正式写入主库。
- **Prompt Mart**：本地分析平台中预清洗、归一化和聚合 `history.prompt` 的提示词分析缓存层。
- **提示词瘦身**：从自然输入和源模板中筛选优秀 prompt 候选、剔除低质样本并保留人工审核阶段的分析流程。
- **提示词向量化**：把候选 prompt 写入基础 embedding 表并维护模型、覆盖、状态和续跑信息；当前不包含相似边、相似簇、近似族、语义场景或图谱派生分析。
- **提示词词义分析**：本地分析平台中围绕指定词元、同义映射、删除表、低频阈值和模板候选槽位做的 prompt 标签治理；只影响本地物化统计，不改原始 prompt。
- **自由P图拆解**：本地分析平台中固定面向 `edit` scope 的提示词浏览页，按分类标签筛真实 prompt、展示拆解后的 grouped tokens，并允许人工沉淀优秀模板。
- **从未活跃用户**：本地分析用户画像口径中，没有 `last_activity`、没有生成计数且没有历史生成记录的用户。
- **沉睡用户**：本地分析用户画像口径中，曾经有活跃或生成痕迹，但当前统计周期内没有 `last_activity` 或生成记录的用户。
- **本地分析登录保护**：本地数据分析平台的独立应用层登录，不复用正式 Web 用户体系；公网访问时还必须叠加 Cloudflare Access 或等价身份层。
- **Cloudflare 公网入口**：由 Cloudflare DNS、Tunnel、Access、Pages/R2 等能力承接的公网域名入口；管理/分析类入口必须有身份层保护，API token 只以宿主机密钥文件路径和权限边界记录。

## 执行与运维
- **Worker Agent**：从 Central 拉取任务、准备输入、调用 ComfyUI、上传结果并回报状态的进程。
- **ComfyUI Runtime**：实际加载模型并执行 workflow 的运行时，可以是宿主机、LAN AIO 或 RunPod 容器。
- **workflow 事实源**：当前运行时 workflow 资产以 `workers/comfy_agent/workflows` 和同步后的 `remote_workers/` bundle 为准。
- **LAN AIO**：局域网 GPU 上的 all-in-one runtime 形态，将 ComfyUI、relay/agent 和模型同步收在受控容器链路里。
- **RunPod 手动池**：云正式备用或临时扩容的 GPU worker 池，可由人工操作，也可由 Dashboard autoscaler 在门禁满足时提交 `add` / `down`。
- **Dashboard RunPod autoscaler**：由 Dashboard backend 根据队列等待、worker 健康、profile 阈值和 RunPod operation store 自动提交 RunPod `add` / `down` 的管理循环。
- **云测试控制面**：研发、联调、缺陷修复和配置验证的默认发布目标。
- **维护式更新**：先进入生成维护、等待队列、同步代码/env、执行目标环境重建子步骤、再恢复入口的部署方式；当前云测试日常更新不默认使用该路径，仅在整栈联动、迁移、排空验证或用户明确要求维护窗口时使用。
- **云测试快速更新**：云测试日常研发验证的默认部署方式，只同步必要代码并重建对应模块容器，不默认进入维护或排空队列。
- **云正式控制面**：生产控制面，任何正式发布、重建或生产 RunPod mutation 都需要用户明确确认。
- **Cloudflare 自动化令牌**：用于 AllBot Cloudflare 账号自动化的高权限 API token，只允许保存在宿主机受限权限文件中；聊天、文档、Git 和日志只记录路径、用途和权限边界，不记录明文。
- **本地正式灾备**：云正式整体不可用时，由本地主服务器临时接管正式入口的应急形态。
- **运行态快照**：某次探测得到的服务、worker、磁盘或网络状态，只代表当次现场，不等同于长期容量承诺。
- **实时知识库**：`README.md`、`AGENTS.md`、`docs/` 当前文档和 `.codex/skills/` 中用于指导后续开发、运维、排障的活跃知识。
- **归档/取证材料**：`docs/archive/` 与 `logs/` 中保存的历史证据、事故报告或 canary 记录，不作为当前 SOP。

## 架构词汇
- **Module**：有 interface 和 implementation 的能力单元。
- **Interface**：调用方必须知道的完整使用契约，不只是类型签名。
- **Seam**：可以替换行为而不改调用点的位置。
- **Adapter**：填入 seam 的具体实现。
- **Deep module**：小 interface 承载较多行为，让调用者少知道、维护者集中修改。
- **Provider/dependencies seam**：AllBot core 层和测试优先使用的显式依赖注入方式。
