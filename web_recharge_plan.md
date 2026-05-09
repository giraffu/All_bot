# Web 端充值功能实施方案

## 1. 需求背景与核心决策
为了提升转化率并完善 Web 端的闭环体验，系统将在 Web 端新增充值与会员升级功能。基于与用户的讨论，明确以下核心决策：
- **支付渠道限制**：Web 端直接隐藏 Telegram Stars 支付，仅提供 **RMB (易支付)** 和 **TON (Crypto)** 两种支付方式。
- **页面交互设计**：充值界面设计为**独立的页面**（如 `/dashboard/billing`），并在用户的**个人中心（User Center）**提供显眼的快捷进入入口（如“💎 充值 / 升级会员”按钮）。
- **底层架构复用**：严格遵循 `allbot-billing-auth` 规范，前端不可信。后端完全复用现有的异步预建单与 Webhook 回调发货逻辑（Saga 模式），确保资产变动强一致性。

---

## 2. 后端改造规划 (Web API 层)

后端逻辑基本做到“0”侵入现有发货核心，只需在 Web API 层新增三个轻量级接口供前端调用。

### 2.1 新增路由模块 (`src/web_api/routers/payment.py`)

1. **`GET /api/payment/plans` (获取商品列表)**
   - **逻辑**：查询 `membership_plans` 表。
   - **过滤**：可以直接返回所有可用套餐，但前端展示时将只显示对应的 RMB 价格和 TON 价格（忽略 Stars 价格配置）。

2. **`POST /api/payment/orders` (创建 RMB 预建单)**
   - **鉴权**：需 `Depends(get_current_user)` 提取当前用户对象。
   - **参数**：`plan_id` (int)。
   - **逻辑**：
     1. 根据 `plan_id` 查库获取真实的 `final_price`（防前端篡改）。
     2. 在 `orders` 表插入一条 `status="PENDING"` 的记录。（**避坑注意**：由于历史遗留命名，写库时必须赋值 `telegram_id=current_user.id`，因为履约核心 `fulfill_order` 依赖 `User.id == order.telegram_id` 进行反查匹配）
     3. 调用 `RMBPaymentService` 构造易支付（或其他网关）的带签名支付跳转 URL。**（⚠️ 避坑注意：当前 `RMBPaymentService.create_payment_url` 的 `return_url` 是写死读取环境变量的，必须修改该方法签名，增加 `return_url: str = None` 参数来支持动态覆盖，否则前端付完款会停留在后端的静态死胡同页面）**
   - **返回**：`{"order_id": "...", "pay_url": "https://..."}`

3. **`GET /api/payment/orders/{order_id}/status` (订单状态轮询)**
   - **逻辑**：查询 `orders` 表对应 `order_id` 的 `status`。
   - **返回**：`{"status": "PENDING" | "SUCCESS" | "FAILED"}`

### 2.2 核心机制复用说明
- **RMB 回调**：易支付回调将继续打到现有的 `payment_api_server.py`，验签后调用 `fulfill_order` 发货。
- **TON 支付**：Web 前端构造好 payload 链上发交易后，现有的 `TonPaymentValidator` 守护进程会自动扫块并完成发货。完全不需要 Web API 介入。

---

## 3. 前端改造规划 (Vue3)

### 3.1 路由与页面入口
- **新增路由**：在 `router/index.ts` 注册 `/dashboard/billing`（需登录鉴权）。
- **个人中心入口**：在 `UserCenter.vue` 或 Header 区域，用户余额/身份旁边添加「充值 / 升级」按钮，点击跳转至 `/dashboard/billing`。

### 3.2 独立充值页面 (`Billing.vue`) 设计
- **商品橱窗**：卡片化展示各档位月卡与散修盘缠。高亮显示当前用户的身份以做对比。
- **支付收银台区**：选中商品后，下方滑出/展开支付方式选择：
  - **选项 A：使用支付宝/微信 (RMB)**
  - **选项 B：使用 TON 钱包连接支付**

### 3.3 支付交互逻辑

#### 场景一：RMB 支付
1. 点击支付 -> 调用 `POST /api/payment/orders`。
2. 拿到 `pay_url` 后，提示用户“正在前往收银台...”，并跳转支付链接。**（⚠️ 前端避坑：如果使用 `window.open` 在 `await` 异步请求之后执行，极大概率会被浏览器弹窗拦截器拦截。建议在请求前同步打开 `const newWin = window.open('about:blank', '_blank')`，拿到 url 后再赋值 `newWin.location.href = url`，或者直接在当前页 `window.location.href = url` 跳转）**
3. 原页面弹出“等待支付完成”的 Modal，并开启 `setInterval` 每 3 秒轮询一次 `GET /api/payment/orders/{order_id}/status`。
4. 当轮询到 `SUCCESS`，关闭 Modal，播放撒花动画，并调用 `fetchUserInfo` 刷新全局 Store 中的灵石余额与会员头衔。

#### 场景二：TON 支付
1. 前端需引入 `@tonconnect/ui-vue` 库（如已存在则复用）。
2. 无需调用后端建单。前端直接获取当前用户的 `telegram_id`，并构造 Payload：`ORDER:{telegram_id}:{plan_id}:{Date.now()}`。（**核心避坑**：现有后端的 `TonPaymentValidator` 强依赖解析出的 TG ID 查库，且目前所有 Web 用户均已绑定 TG，所以必须传 `telegram_id` 而非 `internal_user_id`）。
3. 拉起钱包授权并发送链上交易。
4. 交易发出后，由于没有本地 order_id，前端可通过**轮询获取用户最新信息 API (`GET /api/users/me`)** 来监听余额/身份是否发生变化，以此判断链上发货是否成功。

### 3.4 前端交互与性能规范 (Vue 3)
- **防内存泄漏**：使用 `setInterval` 轮询订单或用户信息时，必须在组件的 `onUnmounted` 生命周期中主动 `clearInterval`。
- **防无限轮询死锁 (风险控制)**：如果用户点击支付后在收银台页面放弃了支付，原来工作台的 Modal 可能会一直以 3 秒/次的频率无限请求后端。**必须设置一个最大轮询次数或超时时间**（例如 5 分钟，即 100 次），达到上限后自动 `clearInterval`，并将 Modal 状态改为：“订单可能尚未支付或网络延迟，请稍后刷新页面查看”。
- **优雅动效**：支付方式的展开/折叠区域，推荐使用 Vue 3 内置的 `<Transition name="slide-fade">` 配合 `v-if/v-show` 实现。
- **全局状态无缝同步**：支付成功结束动画后，务必调用 Pinia Store 的 `fetchUserInfo()` 刷新全局状态，这会自然触发 Header 栏的余额/身份实时变化。

---

## 4. 实施与推进步骤

1. **第一阶段：后端接口就绪**
   - **修改 `src/services/rmb_payment_service.py` 中的 `create_payment_url`，使其支持动态接收 `return_url` 参数**。
   - 创建 `src/web_api/routers/payment.py`。
   - 实现查询套餐、建单、状态轮询三个 API。
   - 在 `src/web_api/main.py` 挂载路由。

2. **第二阶段：前端页面与 RMB 联调**
   - 完成 `/dashboard/billing` 静态页面与入口组件。
   - 对接 RMB 支付 API，跑通预建单 -> 跳转 -> 回调 -> 轮询成功的完整闭环。

3. **第三阶段：前端 TON 钱包对接**
   - 引入 TON Connect UI 组件。
   - 构造交易 Payload 并测试链上扫块与异步发货。

4. **第四阶段：验收与上线**
   - 检查越权漏洞（能否为他人建单？前端能否篡改金额？）。
   - 检查极端情况（用户支付完立刻关掉网页，系统能否正常发货？——由于后端有异步回调和守护进程，可以正常发货）。
