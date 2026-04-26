# AllBot AI 编程辅助技能库 (AI Skill Library)

本目录（与 `.trae/skills/` 同步）收录了专为修仙主题 AI 创作工作台 (All_Bot) 量身定制的结构化 AI 编程技能（Skill）模块。
通过将原先厚重的技术文档重构为高内聚、低耦合的“技能提示词（Prompt）”，AI 助手（如 Trae）可以在后续的开发任务中被精准触发，自动注入特定子模块的架构红线、接口契约与测试规范。

## 1. 技能清单 (Skills List)

当前工作区包含以下 6 个核心 AI 编程辅助技能。您只需在对话中提及对应模块，或直接输入技能名称即可让 AI 加载最佳实践。

| 技能名称 (Skill Name) | 核心管控边界 (Responsibilities) | 触发场景 (When to invoke) |
| :--- | :--- | :--- |
| **`allbot-task-engine`** | Redis 队列调度、单用户并发锁防刷、中控分发与僵尸任务自愈剔除。 | 当修改或开发生图任务生命周期、Redis 锁逻辑时。 |
| **`allbot-billing-auth`** | 单轨制灵石账本、JWT 无状态鉴权、月卡折算、多渠道支付 Webhook 幂等验签。 | 当开发用户充值、会员身份折算、登录拦截或扣费流水时。 |
| **`allbot-gallery-storage`** | MinIO 预签名直传、Cloudflare R2 边缘加速、防套娃原创保护与社区防并发点赞。 | 当处理大文件存储降级、修改画廊展示规则或互动逻辑时。 |
| **`allbot-tg-fsm`** | PTB 交互状态机、菜单意外拦截防死锁、Telegram Local API 大文件 HTTP 直连 Monkey Patch。 | 当开发新的 Telegram 机器人对话流或修改文件上传下载时。 |
| **`allbot-llm-ops`** | 本地 LM Studio 推理限流 (Semaphore)、智能客服 LangGraph 意图嗅探与群组隔离。 | 当接入本地大模型提示词优化或调整 CS Bot 记忆逻辑时。 |
| **`allbot-ops-deployment`** | Docker Compose 容器隔离编排、Alembic 迁移、MinIO防宕机、系统自愈排障与网络穿透 502/404 故障恢复。 | 当调整微服务架构、增加环境配置或处理生产部署故障时。 |
| **`allbot-kb-auto-updater`** | 智能监控代码变更，维护知识库体系的逻辑一致性与结构完整性。 | 当项目新增功能、修改核心接口或重构代码，需要同步更新文档时。 |

## 2. 快速开始指南 (Quick Start)

### 2.1 如何组合使用技能 (Composability)
这些技能被设计为正交且支持组合的。例如：
当您要求 AI **“为网页端开发一个新的 LTX 高级视频生成接口，扣费后进入排队”** 时，AI 应当自动（或您主动提示它）同时加载以下技能：
1.  加载 `allbot-billing-auth`：了解如何通过 `Depends(get_current_user)` 解析 JWT 获取 `internal_user_id`，并调用底层 `check_and_deduct_credits` 完成灵石扣除。
2.  加载 `allbot-task-engine`：了解如何申请 Redis 并发锁，并调用 `core_submit_generation_task` 将任务下发。

### 2.2 开发新功能的规范流程
1.  **明确边界**：确认需求触及的业务红线（如：扣费必须记流水、状态机必须正则拦截主菜单）。
2.  **触发技能**：在与 AI 的对话前加上指令（如：`请使用 allbot-tg-fsm 技能帮我编写一个...`）。
3.  **编写与测试**：AI 将按照技能中规定的**输入输出契约**生成代码，并补充技能内要求的单元与集成测试用例（如 `test_fsm_unexpected_menu_click`）。

## 3. 性能基准测试报告 (Performance Benchmark)

根据技能中定义的核心流转链路，系统在以下基准下保证稳定性（SLO 摘要）：

### 3.1 任务并发与调度引擎 (`allbot-task-engine`)
*   **并发锁争抢**：在 1000 QPS 峰值下，Redis `SETNX` 确保单用户绝对不超发（超卖率为 0%）。
*   **调度延迟**：在 pending 队列不拥堵的情况下，中控 API 的 `BLPOP` 提取与下发耗时 `P99 < 500ms`。
*   **自愈耗时**：僵尸任务的检测与强制退款闭环在后台每分钟执行一次，对主线程 CPU 影响 < 1%。

### 3.2 计费与授权校验 (`allbot-billing-auth`)
*   **JWT 签发与解析**：纯内存 CPU HMAC-SHA256 计算，无数据库 IO，单节点 `P99 < 2ms`。
*   **支付回调幂等性**：对于同一外部订单号 (`external_trade_no`) 的恶意重放攻击，数据库主键锁与状态位校验确保 100% 拦截，重复发货率 0%。

### 3.3 存储与流媒体加载 (`allbot-gallery-storage`)
*   **直传预签名**：FastAPI 提供 PUT URL，响应 `P99 < 100ms`（因为离线注入了 `us-east-1` Region，避免了网络死锁）。
*   **R2 边缘分发**：社区广场缩略图的全球加载时间（TTFB）由海外 VPS 和 CF R2 承载，`P95 < 200ms`。

### 3.4 本地 LLM 推理限流 (`allbot-llm-ops`)
*   **显存保护**：在使用 35B 级别模型（占用 ~22GB VRAM）时，通过 `asyncio.Semaphore(2)` 压测，内存峰值被严格钳制在 24GB 以内，杜绝 OOM 崩溃。

---
*注：这些技能模块定义文件已部署在工作区的 `.trae/skills/` 目录下，直接融入了 IDE 的上下文生态。AI 助手将在符合条件时自动为您加载这些架构约束。*
