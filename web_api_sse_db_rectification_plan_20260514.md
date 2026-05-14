# web-api SSE 与数据库边界整改说明（贴近现状版）

## 一、问题概述

### 日志分析报告

- 监控时间范围: `2026-05-14 21:10:16` ~ `2026-05-14 21:25:16`
- 日志源: `web-api`, `tg-bot`, `dashboard_dashboard-backend_1`, `backend_api_1`, `comfy-agent-1..7`
- 结论概览: 主要异常集中在 `web-api` 的数据库连接污染链路；次要问题为 `tg-bot` RMB 支付失败 1 次、`dashboard` 访问 TONCenter 被 429 限流 3 次。

## 异常总览表

| 异常类型 | 次数 | 首次时间 | 末次时间 | 影响接口/链路 | 级别 |
| --- | ---: | --- | --- | --- | --- |
| web-api 数据库连接已关闭 | 10 | 21:11 | 21:11 | 历史写回/任务状态流 | P1 |
| web-api 回滚时底层连接已关闭 | 8 | 21:11 | 21:11 | 历史写回/任务状态流 | P1 |
| web-api SSE 取消作用域打断数据库操作 | 2 | 21:11 | 21:11 | 任务 SSE / 历史查询 | P1 |

当前 `web-api` 中与“任务结果获取”相关的风险，主要不在连接池参数，而在接口职责和数据库边界设计。

结合当前代码，风险集中在以下三个入口：

- `src/web_api/routers/tasks.py` 的 `GET /api/tasks/{task_id}/stream`
- `src/web_api/routers/users.py` 的 `GET /api/users/history/{task_id}/apply-context`
- `src/web_api/routers/gallery.py` 的 `GET /api/gallery/posts/{post_id}/apply-context`

其中：

- `tasks.py` 的 SSE 路由是当前风险最高的一条链路
- `users.py` 的 `apply-context` 是典型的“GET + 慢 I/O + 条件写回”
- `gallery.py` 的 `apply-context` 也有 `GET + commit` 副作用，但风险级别低于 `users.py`

本次整改的目标，不是单纯“减少报错日志”，而是把职责拆开，让数据库 session 不再跨越长连接、慢 I/O 和可取消边界。

## 二、当前代码的真实现状

### 1. `tasks.py` 里的 SSE 不是纯状态流

当前 `/api/tasks/{task_id}/stream` 的真实行为不是“只推状态”，而是：

1. 先鉴权，读取一次数据库获取当前用户
2. 建立 Redis Pub/Sub 订阅
3. 通过 `httpx` 轮询中控 `/status/{task_id}` 兜底
4. 当任务状态进入 `done` 时，在 SSE 生成器内部：
   - 反复新开 `AsyncSessionLocal()` 查询 `History`
   - 等待 `history.output_file` 可用
   - 生成 MinIO 预签名 URL
   - 把 `result` 字段直接塞进 SSE 返回

而且这段“查 `History` + 等待落库 + 组装结果”的逻辑在代码里出现了三次：

- 初始状态已完成分支
- Redis 收到 `done` 事件分支
- 轮询兜底发现已完成分支

所以它现在本质上是：

- `SSE 状态流`
- `结果就绪等待器`
- `结果地址拼装器`

三种职责的混合体。

### 2. SSE 在可取消生成器中多次进出数据库边界

当前 SSE 并不是持有单个长事务，但它在长生命周期的 `event_generator()` 内多次短开短关 session。

这类结构在用户关闭页面、切换路由、浏览器主动断开、网络抖动时，取消信号可能恰好落在：

- `db.execute(...)`
- `session.__aexit__()`
- rollback / close 清理路径

于是“请求取消”会放大成“数据库连接关闭”“回滚失败”“清理路径报错”之类的异常。

这也是为什么当前问题的主因更接近“职责过重 + 边界穿透”，而不是单纯“连接池不稳”。

### 3. 前端当前直接依赖 SSE 的 `result` 字段

这点是原简版文档里遗漏但非常关键的现状。

当前前端任务流并不是“收到 `success` 后再请求结果接口”，而是：

1. 监听 `/api/tasks/{task_id}/stream`
2. 收到 `payload.status === "success"`
3. 直接使用 `payload.result` 作为：
   - 结果预览地址
   - 下载地址
   - 悬浮任务球完成态展示数据

这意味着：

- 如果先把 SSE 改成纯状态流
- 但前端还没切到新结果接口

那么会立即产生功能回归，表现为：

- 成功任务没有预览
- 下载按钮失效
- 已完成任务无法正确展示

因此，SSE 的瘦身不能脱离前端联动单独推进。

### 4. `users.py` 的 `apply-context` 确实是 GET 读写混合接口

当前 `GET /api/users/history/{task_id}/apply-context` 会：

- 查询 `History`
- 查询关联 `GalleryPost`
- 计算 `billing_resolution`
- 在必要时调用 `extract_media_metadata_from_storage()`
- 根据探测结果回写 `billing_resolution / width / height / duration`
- 最后执行 `await db.commit()`

这意味着它实际是“读 + 慢 I/O + 条件写回”的混合接口，而不是纯读取接口。

### 5. `users.py` 在持有 session 时跨越慢 I/O

`extract_media_metadata_from_storage()` 虽然内部使用了 `asyncio.to_thread(...)`，不会阻塞事件循环，但它本质仍是慢 I/O：

- 视频：预签名 URL + `ffprobe`
- 图片：对象下载到本地 + Pillow 读取

问题不在“会不会阻塞 loop”，而在“数据库 session 仍处于持有状态”。

只要慢 I/O 发生在 session 生命周期内，就会拉长数据库边界的暴露时间，并把用户取消请求、网络中断等情况耦合进清理路径。

### 6. `gallery.py` 的问题属同类，但比 `users.py` 轻

当前 `GET /api/gallery/posts/{post_id}/apply-context` 也会：

- 查询 `GalleryPost`
- 查询 `History`
- 计算 `billing_resolution`
- 在必要时更新 `history.billing_resolution`
- 执行 `await session.commit()`

但和 `users.py` 不同的是，它当前没有跨越 `extract_media_metadata_from_storage()` 这种明显的慢 I/O。

因此它的主要问题是：

- `GET` 语义不纯
- 存在副作用
- 与 `users.py` 的接口行为不一致

而不是当前数据库异常的第一主战场。

### 7. 现有中控 `/image` `/video` 不能直接替代 `web_api` 结果接口

仓库里确实已有：

- `backend/app/main.py` 的 `GET /image/{task_id}`
- `backend/app/main.py` 的 `GET /video/{task_id}`

但它们属于中控 backend，不是 `web_api` 面向 Web 用户的统一结果接口。

当前这两个接口的特点是：

- 依赖中控 `queue_manager` 的状态
- 按 `result_path` 直接从 MinIO 拉文件回传
- 不等价于 `web_api` 当前“用户归属校验 + History 语义 + 预签名 URL 返回”的行为

因此，本次整改仍然需要在 `web_api` 侧补一条真正适配 Web 端的结果接口，而不是直接复用中控下载接口来替代 SSE。

### 8. `pool_pre_ping=True` 已开启，但不是主修复点

数据库引擎当前已启用 `pool_pre_ping=True`。

它解决的是：

- 从连接池借出陈旧连接时的检测问题

它不能根治的是：

- 正在使用中的连接被请求取消打断
- session cleanup 路径与取消异常交叉
- 长生命周期逻辑里反复进出数据库边界

所以本次问题的主修复点仍应放在职责拆分和事务边界收缩上。

## 三、整改目标

本次整改建议围绕四个明确目标推进：

1. 让 SSE 回到“只推状态”的单一职责
2. 让结果获取改由独立短请求完成
3. 让 `apply-context` 回到只读语义，不再在 GET 中隐式写库
4. 让数据库 session 不再跨越慢 I/O 与可取消边界

## 四、推荐整改方案

### 第一步：先补 `web_api` 结果接口，不要先砍掉 SSE 的 `result`

这是最关键的顺序调整。

在当前代码现状下，不能直接先把 SSE 改成纯状态流，因为前端还依赖 `payload.result`。

应先在 `web_api` 新增统一结果接口，例如：

- `GET /api/tasks/{task_id}/result`

建议该接口职责收敛为：

1. 使用短生命周期 session
2. 查询 `History`
3. 校验 `task_id` 是否属于当前用户
4. 判断 `output_file` 是否已就绪
5. 生成 Web 端可直接消费的结果地址
6. 返回结构化结果，而不是直接透传中控下载接口

推荐返回语义示例：

- 已完成：
  - `status=success`
  - `task_id`
  - `task_type`
  - `media_type`
  - `result_url`
- 未就绪：
  - `status=pending_result`
  - 或 `404 result not ready`

这里更推荐：

- 用结构化 JSON 返回状态
- 保持与前端任务流兼容

而不是简单返回文件流。

### 第二步：前端先切换到“收到 success 后单独拉结果”

在新结果接口上线后，再同步调整前端任务流：

1. SSE 继续负责状态事件
2. 当前端收到 `status === "success"` 时
3. 不再依赖 `payload.result`
4. 改为调用 `GET /api/tasks/{task_id}/result`
5. 把接口返回的 `result_url` 写入 `task.resultUrl`

必要时可加短暂重试：

- SSE 先收到 `success`
- 但 `History.output_file` 还未完全可见
- 结果接口短时间返回 `pending_result`
- 前端重试几次即可

这一步完成前，不应直接删除 SSE 中的 `result` 字段。

### 第三步：在前端切换完成后，把 SSE 收敛为真正的状态流

前端不再依赖 `payload.result` 后，再修改 `src/web_api/routers/tasks.py`：

1. 保留鉴权
2. 保留 Redis Pub/Sub 监听
3. 保留轮询中控 `/status/{task_id}` 的兜底逻辑
4. 当任务状态进入完成态时，只返回最小状态字段，例如：
   - `status=success`
   - `task_id`
   - `task_type`
5. 删除 SSE 中三段：
   - `History` 查询
   - 等待 `output_file` 的轮询
   - `presigned_url` 组装逻辑

这样做后，SSE 会重新回到：

- 长连接只负责推状态
- 普通短请求负责取结果

两个边界清晰的职责模型。

### 第四步：把 `users.py` 的 `apply-context` 改成只读接口

当前 `users.py` 是最典型的“读 + 慢 I/O + commit”混合接口，应优先整改。

推荐方案：

1. 保留读取 `History` 与 `GalleryPost` 的逻辑
2. 运行时计算 `billing_resolution / width / height / duration`
3. 如字段缺失，可继续调用媒体探测逻辑
4. 但不再在该 GET 接口中回写 `History`
5. 删除：
   - `should_commit`
   - `await db.commit()`
   - 同步自愈写库逻辑

如业务仍希望逐步补齐历史脏数据，建议改为以下两种方案之一：

- 方案 A：完全不回写，只做运行时计算
- 方案 B：接口返回结果，同时投递后台异步修复任务

如果短期必须保留回写，也应至少改成：

1. 第一段短 session 只读数据库
2. 关闭 session
3. 再执行媒体探测等慢 I/O
4. 如确实需要回写，再新开第二段短 session 单独 update / commit

但这只应作为过渡止血，不应作为长期方案。

### 第五步：同步把 `gallery.py` 的 `apply-context` 改成只读

`gallery.py` 当前风险比 `users.py` 轻，但为了接口语义一致性，仍建议同步收口。

整改方式：

1. 保留当前查询与计算逻辑
2. 移除：
   - `history.billing_resolution = ...`
   - `await session.commit()`
3. 改为只读计算后直接返回

这样可以达到三个效果：

- 去掉 GET 写库副作用
- 让两个 `apply-context` 行为一致
- 降低未来维护时的心智负担

### 第六步：最后再做 session 依赖与 cleanup 兜底收口

在结构性问题完成后，再处理兜底增强项：

1. 统一 `web_api` 下重复的 `get_db()` 实现
2. 收敛 session 依赖入口到统一位置
3. 对“请求取消”和“数据库清理失败”分别记录更清晰的日志
4. 必要时补充 cleanup 防御，避免二次放大错误

这一步是加固项，不应替代前面的职责拆分。

## 五、推荐实施顺序

更贴近当前代码的推进顺序应为：

1. 先新增 `web_api` 结果接口
   - 先把“取结果”从 SSE 中剥离出可独立使用的能力
2. 再修改前端任务流
   - 收到 `success` 后改调结果接口
   - 不再依赖 SSE 的 `payload.result`
3. 再收敛 `src/web_api/routers/tasks.py`
   - 删除 SSE 里的查库与结果拼装
4. 再整改 `src/web_api/routers/users.py`
   - 去掉 `apply-context` 的同步写回
5. 再整改 `src/web_api/routers/gallery.py`
   - 去掉 GET 中的 `commit`
6. 最后统一 session 管理与 cleanup 兜底

这样排序的原因是：

- `SSE` 风险最高，但它又被前端直接依赖
- 所以必须先解耦，再瘦身
- `users.py` 是数据库边界问题最明显的 GET 接口
- `gallery.py` 更偏语义收口和一致性收口
- cleanup 补强属于最后的防御性加固

## 六、每一步的验收标准

### 1. `web_api` 结果接口上线完成

验收标准：

- `GET /api/tasks/{task_id}/result` 可以独立返回结果状态
- 接口会校验任务归属
- 图片和视频任务都能返回统一结构
- 结果未就绪时有明确语义，不依赖异常猜状态

### 2. 前端切换完成

验收标准：

- 前端收到 SSE 的 `success` 后，改为请求结果接口
- 页面预览、下载、任务完成提示均不再依赖 `payload.result`
- 任务刚完成但结果稍后可见时，前端有可接受的重试或等待机制

### 3. SSE 改造完成

验收标准：

- `/api/tasks/{task_id}/stream` 中不再查询 `History`
- SSE 中不再生成最终结果 URL
- SSE 只负责状态推送，不再承担结果拼装职责
- 用户关闭页面、切换路由时，该链路数据库异常明显下降

### 4. `users.py` apply-context 完成只读化

验收标准：

- `GET /api/users/history/{task_id}/apply-context` 不再包含 `db.commit()`
- 接口不再在持有 session 时跨越媒体探测慢 I/O 后写回
- 返回字段与现有前端兼容

### 5. `gallery.py` apply-context 完成只读化

验收标准：

- `GET /api/gallery/posts/{post_id}/apply-context` 不再包含 `session.commit()`
- 与用户历史 `apply-context` 的字段行为保持一致
- GET 请求不再带数据库副作用

### 6. session 兜底收口完成

验收标准：

- `web_api` 中重复的 `get_db()` 实现减少或统一
- 日志中能区分“请求取消”与“清理路径失败”
- cleanup 逻辑不再放大原始异常

## 七、结论

结合当前实际代码，本次问题的核心不是单一数据库参数，而是接口职责与数据库边界设计。

最优先的整改方向有四条：

- 先补结果接口，解除前端对 SSE `result` 的强耦合
- 再把 SSE 改回纯状态流
- 把 `apply-context` 改回纯只读接口
- 把数据库 session 从慢 I/O 和可取消请求边界中拆出去

如果只补 cleanup、只加日志或只调整连接池参数，通常只能缓解，不能根治。
