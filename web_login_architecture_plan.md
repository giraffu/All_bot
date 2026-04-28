# Web 端多渠道登录系统架构与安全方案

## 1. 方案概述与设计目标
当前系统的主 Web 端仅支持 Telegram 第三方登录（WebApp `initData` 及 Web Widget `hash`）。本方案旨在设计一套**安全、解耦且符合现有修仙业务逻辑**的“账号/密码”登录体系，实现多渠道登录（Telegram + 账号密码）并存。

**核心目标：**
- **账户融合**：支持纯账号注册登录，同时允许现有 Telegram 绑定的用户设置密码（双通道登录同一实体）。
- **业务一致性**：保留现有的“境界/身份”拦截门槛（如：金丹期以上才可登录 Web 端）。
- **高安全性**：防范暴力破解、撞库、XSS 获取 Token 等常见 Web 攻击。

---

## 2. 数据库与数据模型设计
经查，现有的 `users` 表（`src/database/models.py`）已经预留了所需的底层字段，无需进行破坏性迁移：
- `id`: 内部唯一自增主键 (`internal_user_id`)
- `telegram_id`: TG 唯一标识（可为空，代表纯账号注册用户）
- `username` / `email`: 登录凭证（唯一索引）
- `hashed_password`: 存储加盐哈希后的密码

**账户绑定逻辑：**
- **新用户注册**：直接生成 `User` 记录，`telegram_id` 为空。初始境界默认为“凡人/炼气期”。
- **老用户绑定**：现有的 Telegram 用户在 Web 端或 Bot 内提供一个设置密码的入口，更新其 `hashed_password` 和 `username`。

---

## 3. 后端架构方案 (FastAPI + Core)

遵循 `allbot-billing-auth` 技能规范，核心鉴权逻辑必须下沉到 `src/core/` 层。系统架构需要从原来的单一 TG 鉴权，扩展为支持账号密码校验的双轨鉴权体系，但最终签发的 JWT Token 格式必须保持完全一致。

### 3.1 依赖引入与基础配置
- **哈希算法库**：使用 `passlib[bcrypt]` 进行密码加盐哈希，`bcrypt` 天然抗彩虹表和暴力破解。
- **表单数据模型 (Pydantic)**：在 `src/web_api/schemas/auth.py` 中新增 `UserRegisterRequest` (含 `username`, `password`, `email`) 和 `UserLoginRequest` (或复用 FastAPI 自带的 `OAuth2PasswordRequestForm`)。

### 3.2 核心业务逻辑 (`src/core/auth_core.py`)
所有的密码比对和业务鉴权必须在 Core 层完成，隔离 HTTP 上下文（Request/Response）：

1. **密码工具函数**：
   ```python
   from passlib.context import CryptContext
   pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

   def verify_password(plain_password, hashed_password):
       return pwd_context.verify(plain_password, hashed_password)

   def get_password_hash(password):
       return pwd_context.hash(password)
   ```
2. **账号登录校验 (`authenticate_user_by_password`)**：
   - **步骤 1**：根据 `username` 从数据库查询 `User` 记录。
   - **步骤 2**：若用户不存在或 `hashed_password` 为空（纯 TG 用户且未绑定密码），抛出认证失败异常。
   - **步骤 3**：调用 `verify_password` 比对密码。若错误，触发 Redis 限流计数（详见 3.4）。
   - **步骤 4**：复用修仙业务门槛校验（`check_user_web_access(user)`），若未达到“金丹期”或非“内门弟子”，抛出越权异常 403。
   - **步骤 5**：返回合法的 `User` 对象供外层签发 JWT。

3. **用户注册逻辑 (`register_new_user`)**：
   - 检查 `username` 和 `email` 的唯一性，防止 `IntegrityError`。
   - 初始化用户默认属性：初始灵石（`credits`）、默认境界（`user_group="凡人"`）、默认身份。
   - 调用 `get_password_hash`，将数据落库。

### 3.3 API 路由实现 (`src/web_api/routers/auth.py`)
在表现层处理 HTTP 请求，调度 Core 层服务，并生成标准响应：

1. **`POST /api/auth/login`**
   - 接收 `OAuth2PasswordRequestForm`，调用 `authenticate_user_by_password`。
   - 鉴权成功后，调用现有的 `security.create_access_token(data={"sub": str(user.id)})`。
   - 返回标准结构：`{"access_token": token, "token_type": "bearer", "user": user_schema}`。
2. **`POST /api/auth/register`**
   - 接收注册请求体，调用 `register_new_user` 完成创建，可直接返回生成的 JWT 以实现“注册即登录”。
3. **`POST /api/auth/bind-password`** (需认证)
   - 必须在 `Depends(get_current_user)` 保护下调用。
   - 允许仅有 `telegram_id` 但无 `hashed_password` 的老用户设置密码。

### 3.4 Redis 并发锁与防刷机制 (Security Core)
基于项目中现有的并发锁机制（`allbot-task-engine` 思想），密码登录接口极易受到撞库和暴力破解：
- **限流维度**：`RateLimit:Login:{IP}` 和 `RateLimit:Login:{Username}`。
- **阈值设定**：使用 Redis 的 `INCR` 和 `EXPIRE` 命令。连续 5 次密码错误，触发 15 分钟的封禁锁。
- **成功清零**：一旦 `verify_password` 验证通过，主动 `DEL` 清除该用户的失败计数缓存。

---

## 4. 前端架构方案 (Vue3 + Pinia)

### 4.1 UI 层改造 (`frontend/src/views/Login.vue`)
采用**“分屏/折叠”或“上下结构”**的 UI 设计，保持修仙主题的沉浸感：
- **上方**：传统的账号（道号）/ 密码（密咒）输入框 + “破界登录”按钮。
- **分割线**：“或使用 Telegram 开启结界”。
- **下方**：保留原有的 Telegram Widget 登录容器。
- **交互**：增加表单校验（Vuelidate 或 Ant Design Vue 自带校验），处理 Loading 状态。

### 4.2 状态管理复用 (`frontend/src/stores/auth.ts`)
无需大改。账号密码登录成功后，后端返回的数据结构（`access_token` 和 `user` 对象）与 TG 登录保持一致。
- 直接调用现有的 `authStore.setAuth(data.access_token, data.user)` 即可完成状态注入和 `localStorage` 持久化。
- 现有的 Axios 拦截器 (`src/api/index.ts`) 会自动接管后续请求的 `Bearer Token` 注入。

### 4.3 路由守卫 (`frontend/src/router/index.ts`)
无需修改。现有的路由前置守卫 (`router.beforeEach`) 已经实现了基于 Pinia 状态的鉴权和角色/境界拦截。

---

## 5. 安全性规范 (Security Redlines)

在引入账号密码机制后，系统的攻击面会显著扩大，必须强制实施以下安全策略：

### 5.1 密码存储安全
- **严禁明文**：数据库中的 `hashed_password` 必须使用 `bcrypt` 或 `argon2` 算法加盐哈希，Cost Factor 建议设为 12 以上。

### 5.2 防暴力破解 (Brute-force Protection)
- **Redis 限流**：在 `POST /api/auth/login` 接口增加基于 IP 和 Username 的双重限流（Rate Limiting）。例如：同一 IP 连续密码错误 5 次，锁定该 IP 或该账号 15 分钟。

### 5.3 JWT 与会话安全
- 由于前端目前将 JWT 存储在 `localStorage` 中（易受 XSS 攻击），如果项目对安全性要求极高，建议：
  - **方案 A (现状演进)**：保持 `localStorage`，但在后端严格配置 CORS，并在前端增加 CSP (Content Security Policy) 请求头，防止恶意脚本注入。
  - **方案 B (终极安全)**：将 JWT 存储在 `HttpOnly Secure Cookie` 中，防止前端 JS 读取。但考虑到兼容现有的 Telegram WebApp 架构，方案 A 更为现实。

### 5.4 业务越权防范 (IDOR)
- 登录成功后的 Token `sub` 必须是 `internal_user_id`。
- 所有涉及灵石扣减（`allbot-billing-auth`）、资料修改的接口，必须通过 `Depends(get_current_user)` 解析 Token 中的真实 ID，**绝对不可**信任前端传入的 `user_id` 参数。

---

## 6. 实施演进路线 (Roadmap)
1. **Phase 1: 基础设施** - 后端引入密码哈希库，完善 `User` 模型的密码更新机制，开发 `login` 和 `register` 接口。
2. **Phase 2: 前端集成** - 改造 `Login.vue`，对接新接口，打通登录与注册链路。
3. **Phase 3: 账户融合** - 在用户个人中心 (`Profile.vue`) 增加“绑定密码/设置道号”的功能，让现有的纯 TG 用户可以转为双通道用户。
4. **Phase 4: 安全加固** - 引入 Redis 登录防刷锁，配置 Nginx/Traefik 的请求频率限制。