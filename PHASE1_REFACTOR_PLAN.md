# Bot 系统重构与核心业务剥离方案 (Phase 1)

本文档详细规划了 Web 迁移计划的**第一阶段**：重构现有 Bot 系统。该阶段的核心目标是**在不破坏现有 Telegram Bot 功能的前提下，将底层数据库与核心业务逻辑完全解耦**，为后续 Web BFF 后端的接入铺平道路。

---

## 1. 核心目标与原则

*   **数据模型解绑**：打破 `users` 表主键与 Telegram User ID 的强绑定，建立统一的多平台账号体系。
*   **业务逻辑下沉**：将鉴权、扣费、并发锁检查等核心逻辑从 `src/handlers/` 和强耦合的 `task_service.py` 中抽离，形成纯粹的内部 API。
*   **零性能损耗**：重构后的调用依然在同一进程内，通过 Python 函数调用实现，不增加任何网络开销。
*   **平滑迁移**：通过 Alembic 进行数据库结构的增量修改，确保老用户的资产（灵石、历史记录、订单）不丢失、外键不断裂。

---

## 2. 数据库重构方案 (Database Migration)

这是风险最高、最关键的一步。由于现有的 `users.id` 是 Telegram ID，且被大量表（如 `orders`, `history`, `user_logs`, `worker_logs` 等）作为外键引用，我们不能直接粗暴地更改主键。

### 2.1 表结构变更设计 (`src/database/models.py`)

我们需要对 `User` 模型进行如下调整：

```python
class User(Base):
    __tablename__ = "users"

    # 1. 主键变为纯内部自增 ID (Internal System ID)
    # 注意：在迁移期间，我们为了保持外键不破坏，可以保留原 id 字段名，
    # 但其含义将从 "Telegram ID" 转变为 "Internal ID"。
    id = Column(BigInteger, primary_key=True, autoincrement=True) 

    # 2. 新增多平台登录映射字段
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=True) # 存储真实的 TG ID
    google_id = Column(String(255), unique=True, index=True, nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=True) # 用于 Web 端账号密码登录
    
    # ... 其他原有业务字段保持不变 (credits, user_group, current_identity, etc.)
```

### 2.2 Alembic 平滑迁移策略 (Two-Step Migration)

为了保证生产环境数据的安全，迁移必须分步骤在一次 Alembic revision 中完成（或者写原生 SQL 脚本辅助）：

1.  **新增列**：向 `users` 表添加 `telegram_id`, `google_id`, `email`, `hashed_password` 列。
2.  **数据复制 (Data Backfill)**：将现有的 `users.id` (目前存储的是 TG ID) 复制到新的 `telegram_id` 列中。
    *   *SQL 示例*: `UPDATE users SET telegram_id = id;`
3.  **主键含义转换**：此时，`id` 依然是主键，且现存用户的 `id` 值没有变（外键依然有效）。但从现在开始，`id` 的业务含义变成了“内部系统 ID”。新注册的用户，其 `id` 将由数据库序列自动生成，不再要求是 TG ID。
4.  **修改自增序列 (Sequence)**：如果当前 `users.id` 没有绑定 PostgreSQL 的自增序列（因为之前是外部传入的 TG ID），我们需要为它创建一个 `SEQUENCE`，并将其当前值设置为比现存最大 TG ID 更大的值，以防止未来生成的新内部 ID 与老用户的 TG ID 冲突。
    *   *SQL 示例*: 
        ```sql
        CREATE SEQUENCE users_id_seq OWNED BY users.id;
        ALTER TABLE users ALTER COLUMN id SET DEFAULT nextval('users_id_seq');
        SELECT setval('users_id_seq', (SELECT MAX(id) FROM users) + 1);
        ```

---

## 3. 核心业务层抽象方案 (Core Services Extraction)

在 `src/` 目录下新建 `core/` 文件夹，将强耦合的逻辑下沉。

### 3.1 目录结构规划
```text
src/
├── core/                       # 【新增】纯净的业务逻辑层
│   ├── __init__.py
│   ├── user_core.py            # 负责账号映射、注册、获取内部 User 实例
│   ├── billing_core.py         # 负责查灵石、扣费、记录流水、查并发锁
│   └── task_core.py            # 负责组装 JSON 并调用底层的 APIClient
├── services/                   # 【保留并瘦身】原有服务，作为 Bot 的门面
│   ├── permission_service.py   # 改为调用 user_core 和 billing_core
│   └── task_service.py         # 改为调用 task_core
└── handlers/                   # 【保持不变】依然只负责解析 TG 消息
```

### 3.2 核心模块职责与接口设计

#### A. `user_core.py` (统一身份解析)
无论请求来自 Bot 还是 Web，第一步都是将其身份映射为内部 `User` 实例。
```python
async def get_or_create_user_by_telegram(tg_id: int, username: str, full_name: str) -> User:
    """根据 TG ID 获取内部 User 对象。如果不存在则创建（内部 ID 自动生成）。"""
    pass

async def get_or_create_user_by_google(google_id: str, email: str, full_name: str) -> User:
    """根据 Google ID 获取内部 User 对象。"""
    pass
```

#### B. `billing_core.py` (计费与并发中心)
所有消耗灵石的操作必须经过此模块，**参数全部使用内部 `internal_user_id`**。
```python
async def check_and_deduct_credits(internal_user_id: int, cost: int, task_type: str) -> tuple[bool, str]:
    """
    检查余额并扣费，自动记录流水。
    返回: (是否成功, 错误提示信息)
    """
    pass

async def check_concurrency_lock(internal_user_id: int) -> tuple[bool, str]:
    """
    检查该用户在 Redis 中的并发任务数是否超限。
    """
    pass
```

#### C. `task_core.py` (纯净任务派发)
移除所有与 `telegram.Update` 或 `context.bot` 相关的代码。
```python
async def core_submit_face_video(
    internal_user_id: int, 
    face_image_path: str, 
    video_path: str, 
    resolution: int, 
    duration: int, 
    cost: int,
    priority: int
) -> tuple[bool, str, str]: 
    """
    纯净的任务派发逻辑。不负责发送 Telegram 消息。
    返回: (是否成功, 错误/成功描述, registry_task_id)
    """
    # 1. 调用 billing_core.check_concurrency_lock
    # 2. 调用 billing_core.check_and_deduct_credits
    # 3. 调用底层的 api_client.submit_task
    # 4. 在 Redis TaskRegistry 中登记任务
    pass
```

---

## 4. Bot Handler 的瘦身与适配

完成 `src/core/` 的编写后，我们需要回过头来修改现有的 `src/services/task_service.py` 和各个 `Handler`。它们将变成非常薄的“胶水层”。

**改造前的示例 (Bot 强耦合)**：
```python
# 原本在 task_service.py
async def process_face_video_task(context, chat_id, user_id, ...):
    # 直接查并发
    active_tasks = await redis_client.increment_user_concurrency(user_id)
    if active_tasks > MAX_CONCURRENT_TASKS:
        await robust_send_message(context.bot, chat_id, "任务超限")
        return
    # 直接扣钱
    await permission_service.increment_quota(...)
```

**改造后的示例 (Bot 作为网关)**：
```python
# 现在在 task_service.py (作为 Telegram 的适配器)
from src.core.task_core import core_submit_face_video
from src.core.user_core import get_or_create_user_by_telegram

async def process_face_video_task(context, chat_id, tg_user_id, ...):
    # 1. 身份转换 (TG ID -> 内部 ID)
    internal_user = await get_or_create_user_by_telegram(tg_user_id, ...)
    
    # 2. 调用核心层
    success, msg, task_id = await core_submit_face_video(
        internal_user.id, face_path, video_path, ...
    )
    
    # 3. 负责向 Telegram 用户返回结果
    if not success:
        await robust_send_message(context.bot, chat_id, f"⚠️ {msg}")
    else:
        await robust_send_message(context.bot, chat_id, f"✅ {msg}")
```

---

## 5. 第一阶段验收标准

完成上述重构后，系统必须达到以下标准才能进入下一阶段（Web BFF 开发）：

1.  **数据库平滑验证**：通过 `alembic upgrade head` 执行迁移后，查看 `users` 表。现存用户的 `id` 保持不变，`telegram_id` 成功复制了 `id` 的值。外键表（如 `user_logs`）的查询未报错。
2.  **功能回归验证**：
    *   启动测试服 Bot (`tg-bot-test`)。
    *   进行签到测试（验证灵石增加和流水记录正常）。
    *   发送一张图片进行生图（验证并发锁检查、扣费、任务派发、结果回传整个链路正常）。
    *   发起一次虚拟支付（验证支付回调能正确识别用户并充值）。
3.  **代码规范验证**：检查 `src/core/` 目录下的文件，确保没有 `import telegram` 或使用任何 Telegram 专属的类（如 `Update`, `ContextTypes`）。

---

## 6. 最小影响执行计划 (Minimal Impact Execution Plan)

为了确保正式服 (Prod) 业务零中断，并实现平滑的架构过渡，后续研发必须严格按照以下三个阶段执行：

### 阶段一：数据库无损扩容（对正式服零影响）
*目标：在数据库层面准备好多平台登录字段，老版本正式服继续无感知运行。*
1. **修改 `models.py`**：在 `User` 模型中新增 `telegram_id`, `google_id`, `email`, `hashed_password` 字段，**必须设置为允许为空（`nullable=True`）**。
2. **定制 Alembic 迁移脚本**：生成自动迁移脚本后，手动在 `upgrade()` 中插入核心 SQL：
   - **数据回填**：`UPDATE users SET telegram_id = id;`
   - **主键防冲突**：创建一个内部 `id` 自增序列，并将其起始值设置为极大值（如 `10000000000000`），确保未来 Web 端产生的新内部 ID 永远不与历史的 10 位数 Telegram ID 冲突。
3. **执行迁移**：运行 `alembic upgrade head`。
   - *约束*：此时正式服继续跑老代码，新字段空置，业务不受任何影响。

### 阶段二：在测试服中进行代码解耦（隔离验证）
*目标：将业务逻辑下沉到 `src/core/`，并仅在 `tg-bot-test` 测试容器中验证。*
1. **重构代码**：
   - 新建 `src/core/` 目录，编写纯净的业务逻辑。
   - 改造 `src/services/` 和 `src/handlers/`，剥离数据库和 Redis 的直接调用，改为调用 `core` 层。
   - 注册逻辑切换：新注册的 TG ID 存入 `telegram_id`，主键 `id` 交由数据库序列自动生成极大值。
2. **部署测试服**：`docker rm -f tg-bot-test && docker-compose -f deploy/docker-compose-test.yml up -d --build`
3. **全量验证**：
   - **新用户注册**：检查是否生成 14 位内部 ID 及绑定正确的 `telegram_id`。
   - **老用户兼容**：检查能否根据 `telegram_id` 正确反查历史数据、扣费并关联外键。
   - *约束*：在此阶段，**绝不允许**更新或重启正式服容器。所有破坏性测试必须物理隔离在测试号段。

### 阶段三：正式服灰度与全量上线（微停机发布）
*目标：测试服验证完美无误后，将重构后的代码平滑发布到生产环境。*
1. **开启正式服维护状态**：进入宿主机执行 `docker exec tg-bot touch /app/MAINTENANCE`（优雅拦截新生图任务，允许进行中任务跑完）。
2. **更新生产环境**：
   ```bash
   docker rm -f tg-bot payment-api
   docker-compose -f deploy/docker-compose.yml up -d --build
   ```
3. **恢复服务**：执行 `docker exec tg-bot rm -f /app/MAINTENANCE`，正式服全面接管新架构。

---

## 7. 下一步行动建议

建议严格按照上述计划，立即从 **阶段一** 开始：修改 `src/database/models.py` 表结构变更设计并生成 **Alembic 迁移脚本**。确认数据库结构调整无误后，再动手编写 `src/core/` 业务代码。
