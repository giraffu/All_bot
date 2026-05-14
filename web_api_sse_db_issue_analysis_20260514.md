# web-api SSE 与数据库连接异常分析（校正版）

## 结论摘要

基于当前代码与现有日志交叉核实，这次问题的主判断是成立的，但需要把责任边界写得更精确。

可以确认的事实有：

- `GET /api/tasks/{task_id}/stream` 的 SSE 路由确实在可取消的长连接生成器内多次进入数据库边界。
- `GET /api/users/history/{task_id}/apply-context` 确实是一个 `GET + 慢 I/O + 条件写回 commit` 的混合接口。
- 日志中的 `Cancelled via cancel scope`、`connection is closed`、`cannot call Transaction.rollback(): the underlying connection is closed`，高度符合“请求/流被取消后打断数据库操作或清理”的链路。
- `pool_pre_ping=True` 不是这类问题的主修复点，它解决不了“正在使用中的连接被取消打断”。

需要修正的地方有：

- 本次 SSE 主故障点并不是 `src/web_api/dependencies.py` 的 `get_db()`，因为 `tasks.py` 的 SSE 路由没有走这个依赖，而是直接 `async with AsyncSessionLocal()`。
- SSE 当前更准确的描述是“长生命周期生成器里反复短 session 查库”，而不是“单个长事务持续持有一个 session”。
- `apply-context` 的 `get_db()` 实际走的是 `src/web_api/routers/users.py` 里本地定义的 `get_db()`，虽然实现和公共版本几乎一样，但修复责任不能只写到 `dependencies.py`。

## 涉及代码

主链路代码：

- `src/web_api/routers/tasks.py` 的 `GET /api/tasks/{task_id}/stream`
- `src/web_api/routers/users.py` 的 `GET /api/users/history/{task_id}/apply-context`
- `src/database/core.py` 的 `AsyncSessionLocal`

相关但非主根因代码：

- `src/web_api/dependencies.py` 的 `get_db()`
- `src/web_api/routers/users.py` 的本地 `get_db()`
- `src/web_api/routers/gallery.py` 的 `GET /posts/{post_id}/apply-context`
- `src/core/media_processor.py` 的 `extract_media_metadata_from_storage()`

## 一、已核实的事实

### 1. SSE 路由确实在可取消生成器里查库，而且不止一次

`src/web_api/routers/tasks.py` 的 `task_status_stream()` 先在进入 SSE 前用一次短 session 做鉴权：

- `async with AsyncSessionLocal() as session`
- `current_user = await get_current_user(session, token)`

真正的风险点在 `event_generator()`：

- 它是一个会被 `EventSourceResponse` 取消的长生命周期异步生成器。
- 它在任务完成态下，会多次执行 `async with AsyncSessionLocal() as db` 去查询 `History`。
- 该查询逻辑在代码里重复出现 3 次：
  - 初始化状态已是 `done` 时
  - Pub/Sub 收到 `done` 事件时
  - 轮询状态接口发现已 `done` 时
- 每次最多轮询 30 次，每次间隔 `0.5s`，直到 `History.output_file` 可用。

因此，SSE 当前不是“纯状态推送”，而是：

- Redis 订阅
- 状态轮询
- 完成态查 `History`
- 等待 `output_file` 落库
- 生成 presigned URL

这使它成为“长连接 + 可取消生成器 + 反复进入 DB 边界”的组合。

### 2. `apply-context` 确实是 GET 读写混合接口

`src/web_api/routers/users.py` 的 `GET /history/{task_id}/apply-context` 当前行为不是纯读取：

- 先查询 `History`
- 再查询对应 `GalleryPost`
- 计算 `billing_resolution / width / height / duration`
- 当历史记录缺少元数据时，调用 `extract_media_metadata_from_storage(...)`
- 最后在 `should_commit` 为真时执行 `await db.commit()`

也就是说，这条 GET 接口具备以下特征：

- 读请求里持有请求级 `AsyncSession`
- 持有 session 期间执行存储访问/媒体探测
- 在满足条件时回写数据库

这与“纯只读接口”有本质区别。

### 3. `extract_media_metadata_from_storage()` 的确属于慢 I/O

`src/core/media_processor.py` 中：

- 视频路径会先生成预签名 URL，再通过 `ffprobe` 获取元数据。
- 图片路径会先把对象下载到临时文件，再读取宽高。
- 这些步骤都通过 `asyncio.to_thread(...)` 避免阻塞事件循环，但并没有改变它们属于“慢 I/O / 外部资源访问”的事实。

因此，`apply-context` 的问题不是“阻塞 event loop”，而是“持有 session 时跨越慢 I/O 边界”。

### 4. `pool_pre_ping=True` 不是根治方案

`src/database/core.py` 开启了：

- `pool_pre_ping=True`

它能缓解的是：

- 从连接池借出空闲连接时，该连接已经陈旧/失效

它不能解决的是：

- 一个正在使用中的连接，在 `db.execute()`、`session.__aexit__()`、rollback/close 过程中被取消打断

所以本次问题的核心不是连接池配置，而是请求模型与事务边界设计。

## 二、日志与代码如何对上

结合现有日志分析，可将异常链路收敛为同一类问题的连续阶段：

1. 前端建立 `GET /api/tasks/{task_id}/stream` 的 SSE 连接，或调用 `GET /api/users/history/{task_id}/apply-context`
2. 请求在执行中途被取消、断开或超时
3. 取消恰好打进数据库边界或 session 清理路径
4. 先出现 `Cancelled via cancel scope`
5. 随后连接进入异常/失效状态，出现 `connection is closed`
6. 后续 rollback 或继续写回时再出现 `cannot call Transaction.rollback(): the underlying connection is closed`

这里要强调两点：

- 这 3 条日志更像一条链路的连续表现，而不是 3 个独立 bug。
- 现有代码与日志高度吻合，但严格来说，我们能证明的是“高度相关且强可疑”，不是仅凭静态代码就 100% 证明每一次异常都只来自这两个接口。

## 三、需要收紧的表述

### 1. 不能把 `get_db()` 写成 SSE 的主修复入口

文档旧版把 `src/web_api/dependencies.py` 的 `get_db()` 写得较靠前，容易误导后续动作。

更准确的说法应是：

- `apply-context` 这类依赖注入型路由，确实会受 `get_db()` 行为影响。
- 但本次 SSE 主路径没有走 `Depends(get_db)`，而是在 `tasks.py` 内部直接 `async with AsyncSessionLocal()`。
- 因此，补强 `get_db()` 只能作为兜底优化，不能代替对 `tasks.py` 本身的重构。

### 2. SSE 不是“单个长事务”，而是“长生成器里反复短查库”

旧版“长连接里夹了查库”这个方向是对的，但还可以更准确：

- 每次 DB 查询本身是短 session
- 风险来自这些短 session 被放在一个可取消的长生成器内部反复执行
- 所以修复重点应该是“把 DB 逻辑移出 SSE”而不是仅仅“缩短单次事务”

### 3. `apply-context` 的 `get_db()` 来源需要写准确

`src/web_api/routers/users.py` 自己定义了一份：

- `async def get_db(): async with AsyncSessionLocal() as session: yield session`

它与 `src/web_api/dependencies.py` 的实现基本等价，但 `GET /history/{task_id}/apply-context` 实际绑定的是前者。

如果后续只修公共依赖、不清理本地重复定义，容易漏改。

### 4. 还有一个同类 GET 写回接口

`src/web_api/routers/gallery.py` 的 `GET /posts/{post_id}/apply-context` 也会在必要时：

- 修改 `history.billing_resolution`
- 调用 `session.commit()`

它没有 `users.py` 那条接口那么重，因为没有媒体探测慢 I/O，但从接口语义一致性上看，仍属于“GET 带副作用”的同类问题，建议纳入整改清单。

## 四、根因判断

从实际代码出发，本次问题的根因可以归纳为 3 条：

### 根因 1：SSE 被设计成了可取消长连接里的结果拼装器

当前 `task_status_stream()` 不只是状态流，还负责：

- 等待结果文件落库
- 查询 `History`
- 拼装最终结果 URL

这让它跨越了“推送通道”和“结果查询接口”的职责边界。

### 根因 2：读接口中混入了慢 I/O 和写库

`GET /history/{task_id}/apply-context` 会：

- 持有 session
- 做外部存储访问/媒体探测
- 在必要时提交写回

这会显著放大取消对数据库边界的冲击。

### 根因 3：session 生命周期与取消边界没有隔离

当前无论是 SSE 路由内部 `async with AsyncSessionLocal()`，还是多个 `get_db()` 实现，本质上都没有针对“取消正好打进 cleanup/rollback”做额外隔离。

但这一点是兜底问题，不是主矛盾。主矛盾仍然是前两个结构性设计问题。

## 五、整改方案（按优先级）

### P0：把 SSE 收敛成真正的状态流

目标：

- SSE 只负责把任务状态推给前端
- 不在 SSE 内查 `History`
- 不在 SSE 内等待 `output_file`
- 不在 SSE 内生成 presigned URL

建议改法：

1. 当状态为 `done` 时，SSE 只返回：
   - `status=success`
   - `task_id`
   - 必要的 `task_type`
2. 前端在收到 `success` 后，再单独调用结果接口拿最终媒体地址。
3. 结果接口可以：
   - 复用现有 `/image/{task_id}`、`/video/{task_id}`
   - 或新增 `/api/tasks/{task_id}/result`

验收标准：

- `src/web_api/routers/tasks.py` 的 `/{task_id}/stream` 内不再出现 `History` 查询。
- SSE 路由不再直接依赖 `AsyncSessionLocal()` 获取最终结果路径。
- 用户主动关闭页面或切路由时，不再触发该链路上的 DB 连接异常。

### P1：把 `users.py` 的 `apply-context` 改成真正只读

目标：

- GET 路由不再 `commit`
- GET 路由不再在持有 session 时做慢 I/O 后回写

可选方案：

方案 A：只读返回，不写库

- 运行时计算 `billing_resolution / width / height / duration`
- 返回给前端
- 不回写 `History`

方案 B：异步自愈

- GET 接口只负责返回
- 若发现历史元数据缺失，则投递后台任务异步修复

验收标准：

- `GET /history/{task_id}/apply-context` 不再出现 `await db.commit()`
- 该接口在请求取消时不会把副作用传播到数据库写回

### P1：同步收口同类接口

建议同时检查并整改：

- `src/web_api/routers/gallery.py` 的 `GET /posts/{post_id}/apply-context`

目标：

- 至少消除 GET 请求中的 `commit`
- 保持 Web 各 apply-context 行为一致

### P2：如果短期不能完全重构，先缩短事务边界

若业务短期必须保留回写，可先做过渡方案。

对 `apply-context`：

1. 用短 session 读取 `History` / `GalleryPost`
2. 脱离 DB session 做 `extract_media_metadata_from_storage(...)`
3. 如需写回，再新开一个短 session 执行单次 update/commit

对 SSE：

1. 把 `History` 查询抽成独立 helper
2. 每次查询只持有极短 session
3. 一旦出现取消，立即停止后续轮询，不再继续拼装结果

注意：

- 这是过渡止血，不是最终方案
- 最终仍应把查结果逻辑移出 SSE

### P3：最后统一补强 session cleanup

可以作为框架层兜底补强，但不要把它当成主修复项。

建议：

- 统一收敛各处重复的 `get_db()` 实现
- 明确普通异常与取消异常的 cleanup 路径
- 在必要时避免 cleanup 再次被取消打断
- 对连接已关闭场景做更清晰的日志区分

验收标准：

- 项目中 `get_db()` 不再在多个路由文件里重复定义
- 出现取消时，日志能区分“业务取消”和“连接已失效后的清理失败”

## 六、推荐执行顺序

建议按下面顺序落地，而不是一开始先改底层 session：

1. 先改 `src/web_api/routers/tasks.py`
   - 去掉 SSE 中的 `History` 查询与结果 URL 拼装
2. 再改 `src/web_api/routers/users.py`
   - 去掉 `GET /history/{task_id}/apply-context` 的同步写回
3. 再改 `src/web_api/routers/gallery.py`
   - 去掉同类 GET 写回
4. 最后统一清理 `get_db()` 与 session cleanup

原因很直接：

- 这次最强故障链在 `tasks.py`
- 最明显的接口语义问题在 `users.py`
- cleanup 是兜底，不是主根因

## 七、回归验证清单

整改完成后，至少验证以下场景：

### 1. SSE 断开场景

- 前端建立 SSE 后，在任务未完成时主动关闭页面
- 前端在任务刚完成、SSE 正准备返回 success 时主动关闭页面
- 前端频繁切换路由，触发快速连接/断开

预期：

- 不再出现 `Cancelled via cancel scope -> connection is closed -> rollback failed` 连锁异常

### 2. apply-context 场景

- 历史记录已完整，调用一次 `GET /history/{task_id}/apply-context`
- 历史记录缺失元数据，调用同一接口
- 请求尚未返回时主动取消请求

预期：

- 接口仍能返回正确上下文
- 不因用户取消而产生 DB 连接污染
- 若采用只读方案，则无任何写库副作用

### 3. 完成态结果获取场景

- 任务 `done` 后，前端通过新结果接口获取媒体地址
- `History.output_file` 尚未可见时，结果接口是否有明确返回语义
- 视频与图片任务均验证

预期：

- SSE 与结果查询职责清晰分离
- 不再依赖 SSE 轮询 `History`

## 结论

这次异常可以视为同一类问题的 3 个连续阶段：

1. SSE 或 GET 请求被取消
2. 取消打进数据库操作或 session 清理边界
3. 连接进入失效状态，后续 rollback/写回继续报错

最有效、最可执行的修复方向只有 3 个：

- 把 SSE 收敛成真正的只读状态流
- 把 `apply-context` 收敛成真正的只读接口，或把回写移到后台
- 把数据库事务从慢 I/O 与可取消请求边界中拆出去

如果只补 `get_db()` cleanup，而不调整 `tasks.py` 与 `apply-context` 的职责边界，本次问题大概率只能缓解，不能根治。
