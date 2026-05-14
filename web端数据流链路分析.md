# Web 端数据流链路分析

## 1. 分析目标

本文梳理当前 Web 端从用户上传素材、提交生成、进入本地生成链路、回传结果、展示结果，到后续投稿、收藏、点赞、应用、发送到 Telegram 私聊的完整数据流。

重点关注两件事：

1. 各页面/功能到底请求了哪些接口，数据从哪里来、往哪里去。
2. 在 `MinIO` 与本地生成服务上行带宽受限的前提下，哪些链路最耗带宽，哪些链路只是轻量元数据请求。

---

## 2. 先给结论

### 2.1 当前 Web 端的主链路

Web 端当前是一个典型的三段式架构：

1. 前端 `Vue` 负责上传、表单、状态监听、结果展示。
2. Web BFF `FastAPI` 负责鉴权、任务编排、历史/广场/收藏等业务接口。
3. 中控 + Redis + Worker + ComfyUI 负责真正的本地生成执行，其中中控负责入队和状态管理，Worker 通过 agent 接口拉任务并驱动 `ComfyUI`。

### 2.2 当前最关键的带宽结论

当前最耗带宽的不是点赞/列表/筛选，而是下面几段媒体搬运：

1. 用户上传原始文件到 `MinIO`。
2. Worker 从 `MinIO` 下载输入素材，再上传到 `ComfyUI`。
3. Worker 从 `ComfyUI` 拉取结果，再上传到 `MinIO`。
4. Web BFF 在任务完成后，常见情况下还会通过中控接口把结果重新下载一遍，再写入 `bot-data` 历史路径；但代码里也保留了直接记录 `result_path` 的降级分支。
5. Web 结果落库后，又会异步触发 `MinIO -> R2` 的热同步和缩略图生成。
6. `send-to-bot` 会把 `MinIO` 文件读成字节流，再上传给 Telegram。

也就是说，当前“生成结果回传”在常见成功路径里不是单次搬运，而是多次跨服务搬运，这才是上行受限时最值得优先优化的热点。

### 2.3 轻量请求和重流量请求的区别

轻量请求：

- `gallery/config`
- `gallery/posts` 列表元数据
- `like/dislike`
- `apply-context`
- `tasks/stream` 的 SSE 状态流

重流量请求：

- `/storage/presigned-url` 之后的浏览器直传文件
- 生成完成后的结果搬运
- `history`/`gallery`/`favorites` 里真正加载图片/视频文件
- 下载原图/原视频
- `send-to-bot`
- R2 热同步和缩略图生成

---

## 3. Web 端总体架构

### 3.1 前端路由场景

Web 主要业务页如下：

| 场景文案 | 路由/页面 | 作用 |
| --- | --- | --- |
| 个人主页 | `/profile` | 用户信息、资产等 |
| 功能入口 | `/custom-features` | 跳转到各生成页 |
| 快速换脸 | `/face-swap` | 双图换脸生成 |
| 视频换脸 | `/video-swap` | 图 + 视频生成 |
| 单图生成 | `/single-image` | 传图后生成 |
| 图 + 提示词 | `/image-prompt` | `i2i_pro` / `i2i_draw` / `edit` / `img2img_lora` |
| 图生视频 | `/single-image-video` | `custom_video` / `video_lora` / `ltx_video` |
| 历史记录 | `/history` | 最近生成结果 |
| 修行市集 | `/gallery` | 公共广场/帖子流 |
| 个人心得 | `/my-submissions` | 我的投稿 |
| 修仙笔记 | `/my-favorites` | 我的收藏和我交互过的内容 |
| 充值 | `/billing` | 支付 |

说明：

- “修行市集”实际代码页是 `Gallery`。
- “修仙笔记”实际代码页是 `MyFavorites`。
- “个人心得”实际代码页是 `MySubmissions`。

### 3.2 Web BFF 暴露的主接口分组

Web BFF 统一挂在 `/api` 下，主要包括：

- `/api/storage/*`
- `/api/tasks/*`
- `/api/users/*`
- `/api/gallery/*`

职责分层：

- 前端只和 Web BFF 交互。
- Web BFF 再调用核心层 `src/core/*`。
- 核心层通过 `src/api_client.py` 调用中控 API。
- 中控负责 Redis 队列与状态管理，Worker 通过 `/api/agent/task/pop` 主动拉取任务并上报进度。

---

## 4. 主生成链路

## 4.1 上传阶段

### 4.1.1 前端上传方式

前端上传不是把文件先传给 Web BFF，而是：

1. 前端调用 `GET /api/storage/presigned-url`
2. Web BFF 返回 `MinIO` 预签名 `PUT URL`
3. 浏览器直接 `PUT` 到 `MinIO`
4. 前端拿到带桶前缀的 `object_key`
5. 后续提交生成任务时，把这个 `object_key` 放进 `inputs`

补充说明：

- 当前接口返回的 `object_key` 形如 `bot-data/web_uploads/{user_id}/...`
- 核心层在后续派发前，会把这个带桶前缀的路径规范化成内部使用的对象键

这条设计的好处是：

- 避免 Web BFF 承担大文件入站流量。
- 避免 Web BFF 内存和磁盘做临时缓存。
- 用户素材一开始就落到对象存储。

### 4.1.2 上传阶段的数据流

```text
用户浏览器
  -> GET /api/storage/presigned-url
Web BFF
  -> 生成 MinIO PUT 预签名 URL
用户浏览器
  -> 直接 PUT 文件到 MinIO
MinIO
  -> 返回 object_key
前端
  -> 将 object_key 放入后续任务 payload
```

### 4.1.3 带宽影响

这段链路直接打到 `MinIO`，因此：

- 用户上传大图/大视频时，首先吃的是 `MinIO` 接入和本地出口/入口带宽。
- BFF 本身较轻，不是这里的瓶颈。

---

## 4.2 提交生成任务

### 4.2.1 前端请求

前端统一调用：

- `POST /api/tasks/generate`

请求里带：

- `task_type`
- `inputs`
- 可选顶层 `prompt`
- 可选 `source_post_id`
- 可选 `priority`
- 可选 `is_template`

其中：

- 如果是普通生成，`source_post_id` 为空。
- 如果是从广场/收藏“应用”来的，`source_post_id` 会在再次提交时带上。

补充说明：

- 路由层会把顶层 `prompt` 合并进 `inputs["prompt"]`
- 现网前端并不完全统一使用顶层 `prompt`，例如图生视频页当前就是直接把提示词放在 `inputs.prompt` 里

### 4.2.2 Web BFF 做什么

Web BFF 在进入核心层后，主要完成：

1. 生成 `task_id`
2. 并发锁检查
3. 扣费
4. 输入路径归一化
5. 记录 `TaskRegistry`
6. 根据 `task_type` 选择不同派发策略
7. 调用中控 API 提交任务
8. 异步启动后台监控任务，用于收尾落库、释放锁、退款、记录历史

### 4.2.3 这里传给中控的不是文件本体

这点很关键：

- 核心层传给中控的，已经不是文件字节流，而是 `MinIO object key`
- 中控/Worker 自己去对象存储拿输入素材

这意味着：

- `Web BFF -> 中控` 这段网络是轻量 JSON 请求，不是大文件传输
- 真正的媒体流量，发生在 `Worker <-> MinIO` 和 `Worker <-> ComfyUI`

---

## 4.3 中控排队与本地生成

### 4.3.1 中控做什么

中控 API 接收任务后，把任务放入 Redis 队列：

- 保存任务元数据
- 记录状态为 `pending`
- 提供状态查询 `/status/{task_id}`
- 提供事件发布通道 `comfy:task_events:{task_id}`

更精确地说：

- 当前实现里，中控主要负责“入 Redis 队列 + 提供状态查询/事件发布 + 接收 Worker 状态回报”
- Worker 不是被中控主动推送任务，而是主动通过 agent 路由拉取待执行任务

### 4.3.2 Worker 做什么

Worker 拉到任务后，会执行下面几步：

1. 从 `MinIO` 下载输入素材到本地临时目录
2. 再把输入素材上传到 `ComfyUI`
3. 加载对应工作流 JSON
4. 补丁工作流参数
5. 调用 `ComfyUI /prompt`
6. 通过 WebSocket 监听进度和完成事件
7. 从 `ComfyUI /view` 拉取结果文件
8. 把结果上传到 `MinIO` 结果桶
9. 向中控上报 `done` 和 `result_path`

### 4.3.3 本地生成链路的数据流

```text
Web BFF
  -> 中控 API（仅 JSON / object_key）
中控
  -> Redis 队列
Worker
  -> 从 MinIO 下载输入文件
Worker
  -> 把输入文件上传给 ComfyUI
ComfyUI
  -> 本地执行工作流生成结果
Worker
  -> 从 ComfyUI /view 拉结果
Worker
  -> 上传结果到 MinIO
Worker
  -> 向中控回报完成
```

### 4.3.4 带宽影响

这里是第一大热点：

1. `MinIO -> Worker` 下载输入素材
2. `Worker -> ComfyUI` 上传输入素材
3. `ComfyUI -> Worker` 拉取结果
4. `Worker -> MinIO` 上传结果

如果本地服务和 `MinIO` 不在同机、同盘、同内网零拷贝体系内，那么这几段都会吃上行/下行。

---

## 4.4 前端监听任务状态

### 4.4.1 Web 前端不是短轮询，而是 SSE

前端会打开：

- `GET /api/tasks/{task_id}/stream?token=...`

这是一个 SSE 流。

### 4.4.2 BFF SSE 内部逻辑

SSE 端点内部有两条数据源：

1. Redis Pub/Sub，实时接收中控发布的事件
2. HTTP 补偿轮询，定时请求中控 `/status/{task_id}`

所以它本质是：

- 优先实时事件
- 兜底状态轮询

### 4.4.3 带宽影响

这部分几乎都是小 JSON：

- 状态值
- 进度
- 排队位置

因此：

- SSE 不是带宽大头
- 它主要吃连接数和少量状态请求

---

## 4.5 任务完成后的结果落库

### 4.5.1 当前并不是“Worker 写完 MinIO 就结束”

这是当前最重要的链路特征。

Worker 已经把结果上传到 `MinIO` 结果桶，但 Web BFF 的后台监控逻辑在收到完成后，还会：

1. 常见情况下，通过中控 `/image/{task_id}` 或 `/video/{task_id}` 再下载一次结果字节
2. 用 `UserLogger.save_output_image()` 再写入 `bot-data/{user_id}/output_images/...`
3. 写 `History`
4. 触发 R2 warmup 和缩略图生成

但这里要补一句非常重要的实现细节：

- 如果 BFF 没拿到结果字节，代码会退化为直接把 `result_path` 写入 `History`
- 所以“二次下载 + 二次写入”是当前常见成功路径，但不是绝对必经路径

### 4.5.2 这意味着结果通常会被搬运两轮

在常见成功路径下，服务侧媒体流通常是：

```text
ComfyUI
  -> Worker
Worker
  -> MinIO result bucket
中控 /image 或 /video
  -> 从 MinIO 再取结果
Web BFF
  -> 再下载一次结果字节
Web BFF
  -> 再写到 bot-data 用户历史路径
```

如果再算上后面的 `R2 warmup`，还要继续加一轮：

```text
MinIO
  -> R2
```

### 4.5.3 带宽影响

这就是当前第二大热点，也是最有优化价值的一段：

- 结果在服务内部被重复下载/上传
- 用户只生成一次，但后端侧常见情况下会做多次媒体搬运

---

## 4.6 用户收到生成结果

### 4.6.1 当前回显方式

SSE 收到 `done/success` 后，BFF 会：

1. 等待 `History.output_file` 落库
2. 为最终文件生成 `MinIO presigned GET URL`
3. 把这个 URL 放进 `result`
4. 前端按图片或视频展示

### 4.6.2 当前前端看到的是对象存储 URL

也就是说：

- 前端展示结果时，通常不是再经 BFF 中转
- 而是浏览器直接访问对象存储 URL

这对 BFF 是好事，但会直接占用：

- `MinIO` 的下行带宽
- 或者命中 `R2` 时占用 `R2/CDN` 下行

---

## 5. 业务场景拆解

## 5.1 生成功能页

涉及页面：

- `FaceSwap`
- `VideoSwap`
- `SingleImage`
- `ImageAndPrompt`
- `SingleImageToVideo`

统一流程：

1. 前端先上传素材到 `MinIO`
2. 前端调用 `POST /api/tasks/generate`
3. 前端通过 `SSE` 监听状态
4. 任务完成后拿到结果 URL
5. 用户打开详情时，再从 `/api/users/history` 补拉最近记录

特点：

- 真正的重流量集中在上传和最终媒体回显
- 生成控制本身是轻量接口

---

## 5.2 历史记录

接口：

- `GET /api/users/history`
- `DELETE /api/users/history/{id}`
- `POST /api/users/history/{task_id}/favorite`
- `GET /api/users/history/{task_id}/apply-context`
- `POST /api/users/history/{task_id}/send-to-bot`

### 5.2.1 `GET /users/history`

作用：

- 返回最近 8 条记录
- 组装 `output_file_url`
- 组装 `thumbnail_url`
- 同步校验该条记录是否仍在广场有效上架

媒体读取策略：

1. 优先看 `R2`
2. `R2` 没命中再回退 `MinIO presigned URL`

带宽特点：

- 接口本身只返回元数据
- 真正费流量的是页面开始加载缩略图/原图/视频封面

### 5.2.2 收藏历史

接口：

- `POST /api/users/history/{task_id}/favorite`
- `DELETE /api/users/history/{task_id}/favorite`

“收藏”不仅改数据库标志，还会触发：

1. 原文件异步复制到 `R2`
2. 缩略图生成
3. 缩略图同步到 `R2`

所以“收藏”不是纯元数据动作，它会触发额外媒体链路。

### 5.2.3 删除历史

接口：

- `DELETE /api/users/history/{id}`

行为：

- `History` 软删除
- 如果对应内容已经在广场上架，也同步下架 `GalleryPost`

特点：

- 主要是数据库操作
- 几乎不消耗媒体带宽

### 5.2.4 从历史一键应用

接口：

- `GET /api/users/history/{task_id}/apply-context`

返回内容：

- `prompt`
- `lora_name`
- `input_file`
- `input_file_url`
- `width/height/duration`
- `billing_resolution`
- `task_type`

特点：

- 这个接口主体上仍是轻量 JSON 返回
- 它的主要作用是把原任务上下文回填到前端
- 但它并不完全是“纯只读接口”，必要时会顺手补录媒体元数据、归一化 `billing_resolution` 并提交数据库
- 真正的重流量通常发生在用户再次提交生成后，而不是这个接口本身
- 是否需要用户重新上传参考图，取决于具体页面实现；部分页面会直接复用 `input_file` 和 `input_file_url`

### 5.2.5 发送到 Telegram 私聊

接口：

- `POST /api/users/history/{task_id}/send-to-bot`

服务侧链路：

1. BFF 从 `MinIO` 把文件读成字节
2. 再调用 Telegram Local API `sendPhoto/sendVideo`

这是明确的重流量链路，因为：

- `MinIO -> BFF`
- `BFF -> Telegram`

两段都是真实媒体传输。

---

## 5.3 修行市集

接口：

- `GET /api/gallery/config`
- `GET /api/gallery/posts`
- `POST /api/gallery/posts/{id}/interact?action=like|dislike`
- `GET /api/gallery/posts/{id}/apply-context`

### 5.3.1 广场列表

`GET /gallery/posts` 会做这些事：

1. 查 `GalleryPost`
2. 查关联 `History`
3. 查当前用户是否点过赞/踩
4. 生成 `media_url`
5. 生成 `thumbnail_url`

媒体策略：

- 优先走 `R2`
- 不存在则回退原始存储路径

带宽特点：

- 列表接口本身只是元数据
- 真正流量来自列表滚动时缩略图/视频封面加载
- 如果 `R2` 未命中，用户浏览广场会直接打到 `MinIO`

### 5.3.2 点赞/点踩

接口：

- `POST /api/gallery/posts/{id}/interact`

行为：

- 修改 `UserInteraction`
- 更新 `GalleryPost.likes_count/dislikes_count`

特点：

- 基本只动数据库
- 不是媒体带宽压力点

### 5.3.3 从广场一键应用

接口：

- `GET /api/gallery/posts/{id}/apply-context`

返回：

- 原始 prompt
- LoRA
- 输入文件 URL
- 分辨率/时长
- task_type

前端行为：

1. 先把 apply context 存到 `sessionStorage`
2. 再跳转到对应生成页
3. 用户后续重新提交任务时，带上 `source_post_id`

特点：

- 取上下文本身轻量
- 再生成才是重流量
- 某些页面会直接复用返回的 `input_file` / `input_file_url` 预填原始素材，不一定要求用户先重新上传

---

## 5.4 个人心得

对应页面：

- `/my-submissions`

接口：

- `GET /api/gallery/my-posts`
- `POST /api/gallery/posts/{id}/interact`
- `PUT /api/gallery/posts/{id}/status`
- `DELETE /api/gallery/posts/{id}`
- `GET /api/gallery/posts/{id}/apply-context`

### 5.4.1 我的投稿列表

本质是读取自己在广场的帖子，加上：

- 媒体 URL
- 缩略图 URL
- 交互状态

带宽特点：

- 和广场类似
- 主要由图片/视频加载决定

### 5.4.2 上下架、删除

主要是数据库写操作：

- `status` 改上/下架
- `delete` 做软删除并同步解绑历史的 `is_public`

这些不是带宽热点。

---

## 5.5 修仙笔记

对应页面：

- `/my-favorites`

这里有两种数据源：

1. `filter_type = favorite`
   - 请求 `GET /api/users/my-favorites`
   - 表示“我收藏的自己的历史作品”
2. `filter_type = like|apply|all`
   - 请求 `GET /api/gallery/my-favorites`
   - 表示“我在广场点赞/应用过的帖子”

### 5.5.1 收藏列表

`GET /users/my-favorites` 会：

1. 查 `History.is_favorited = true`
2. 拼 `media_url`
3. 拼 `thumbnail_url`
4. 优先 `R2`，未命中时回退 `MinIO presigned URL`

特点：

- 列表接口是轻量
- 但收藏本身会触发 R2 复制和缩略图生成
- 所以“收藏动作”不是轻操作

### 5.5.2 交互收藏列表

`GET /gallery/my-favorites` 查的是：

- `UserInteraction.action_type in ('like', 'apply')`

因此：

- 点赞过的广场帖子会进这里
- 应用过的广场帖子也会进这里

它本质是广场列表的用户子集视图。

---

## 5.6 投稿

接口：

- `POST /api/gallery/posts/submit/{task_id}`

### 5.6.1 投稿做了什么

投稿不是只插一条帖子记录，还包括：

1. 限频检查
2. 验证 `History`
3. 验证是否允许投稿
4. 创建 `GalleryPost`
5. 将 `History.is_public = true`
6. 后台异步复制原文件到 `R2`
7. 后台异步生成缩略图并同步到 `R2`

### 5.6.2 带宽特点

投稿是一个“中等偏重”的动作，因为它会带出两条媒体任务：

1. 原文件上 `R2`
2. 缩略图生成与同步

如果大量投稿，`MinIO -> R2` 会持续吃出口。

---

## 6. 存储链路

## 6.1 当前存储角色分工

### 6.1.1 MinIO

当前 `MinIO` 仍然是主源站，承担：

- 用户输入文件
- Worker 生成结果
- Web 历史最终文件
- 发送到 TG 的源文件读取
- `presigned upload/download`

### 6.1.2 R2

`R2` 目前主要承担：

- Web 历史热缓存
- 广场和收藏的媒体分发
- 缩略图分发

也就是：

- `MinIO` 是事实源
- `R2` 是读分发层/缓存层

## 6.2 历史/广场/收藏读取策略

当前整体策略仍然是“优先 `R2`，未命中再回退源站”，但不同接口的回退方式并不完全一样：

1. `history` / `users/my-favorites`
   - 先探测 `R2` 是否存在
   - 命中则返回 `R2 public URL`
   - 未命中则回退到 `MinIO presigned URL`
2. `gallery` / `gallery/my-favorites`
   - 先探测 `R2` 是否存在
   - 命中则返回 `R2 public URL`
   - 未命中时通常回退到原始对象路径，而不是统一由 BFF 生成 `MinIO presigned URL`

好处：

- 命中 `R2` 时可以减轻源站读取压力

代价：

- 初次热身前仍可能回源
- 探测本身会产生一定额外请求

---

## 7. 受限上行带宽下的热点排序

下面按照“对 `MinIO` / 本地生成服务上行压力”的重要程度排序。

### P0：生成结果重复搬运

当前常见链路大概率存在如下重复搬运：

1. `ComfyUI -> Worker`
2. `Worker -> MinIO`
3. `MinIO/中控 -> Web BFF`
4. `Web BFF -> bot-data`
5. `MinIO -> R2`

但要注意：

- 第 3、4 步在现网代码里并不是绝对必经分支
- 如果 BFF 没拿到结果字节，会退化为直接记录 `result_path`

即便如此，这仍然是当前最值得优先下手的一段。

### P1：用户上传原始素材

用户每次上传大图/大视频都会直打 `MinIO`。

特点：

- 无法完全消除
- 但可以通过限制尺寸、压缩、前端裁剪、视频转码策略降低压力

### P1：Worker 输入拉取 + 上传到 ComfyUI

如果输入文件先在 `MinIO`，再被 Worker 下载到本地，再上传给 `ComfyUI`，则中间至少多了一次复制。

如果 Worker 与 ComfyUI 不同机或不同网络路径，这段压力会更明显。

### P1：收藏/投稿后的 R2 warmup

收藏和投稿会触发：

- 原图/原视频复制到 `R2`
- 缩略图生成和同步到 `R2`

这对用户来说不是立即必须完成的主链路，但会稳定消耗上行。

### P2：历史/广场用户浏览

这部分压力是否大，取决于 `R2` 命中率：

- `R2` 命中高：源站压力下降
- `R2` 命中低：会持续回源打 `MinIO`

### P2：send-to-bot

这条链路用户频率通常较低，但单次请求对媒体流量是真实占用：

- `MinIO -> BFF`
- `BFF -> Telegram`

如果视频较大，会明显占出口。

---

## 8. 哪些动作是“轻操作”，哪些是“假轻操作”

## 8.1 真正轻操作

- 登录校验
- 拉取广场配置
- 点赞/点踩
- 上下架
- 删除历史记录
- 获取 apply-context（接口本身偏轻，但历史 apply-context 可能顺带做元数据自愈回写）
- SSE 状态监听

这些主要消耗：

- 数据库
- Redis
- 少量 JSON 请求

## 8.2 表面轻，实际会触发媒体搬运的操作

- 收藏历史
- 投稿到广场
- 任务完成后的自动收尾
- send-to-bot

这些动作虽然接口请求本身很短，但后台会继续跑媒体任务。

---

## 9. 当前数据流的关键观察

### 9.1 已经做得比较好的地方

1. 用户上传已改成浏览器直传 `MinIO`，避免 BFF 吃大文件。
2. `BFF -> 中控` 传递的是对象键，不是媒体本体。
3. 前端拿结果、广场、收藏大多直接访问对象存储 URL，而不是由 BFF 代理下载。
4. 广场/历史/收藏已经尽量优先 `R2`，具备分流基础，只是不同接口的回退路径并不完全相同。

### 9.2 当前最明显的结构性浪费

1. 结果回传链路重复搬运。
2. 收藏/投稿会立即触发 `R2` 同步，可能和主链路争带宽。
3. `send-to-bot` 必须走 BFF 字节中转，无法直接复用浏览器直链思路。
4. `apply-context` 虽轻，但后续再次生成会重新触发整条重链路。

---

## 10. 优化优先级建议

以下建议按“对受限上行带宽的缓解价值”排序。

### 优先级 1：消除生成结果的二次下载/二次写入

目标：

- 让 `History` 直接引用 Worker 已写入 `MinIO` 的结果对象
- 或在 `MinIO` 内部做服务端复制
- 避免 `Web BFF` 再经 HTTP 把结果整文件下载一遍再上传

如果这一项落地，通常会是最直接的收益。

### 优先级 2：把 R2 warmup 从“立即执行”改为“按需/延后执行”

可以考虑：

- 仅对公开内容、收藏内容、最近 N 条历史做 warmup
- 普通历史先不立即同步
- 低峰期批量搬运

这样可以把用户主链路和缓存分发链路解耦。

### 优先级 3：继续压缩输入上传

可以考虑：

- 前端上传前压缩大图
- 视频时长/分辨率限制更严格
- 对上传文件做更早的尺寸/码率治理

这会直接降低 `MinIO` 的入口压力。

### 优先级 4：减少 Worker 与 ComfyUI 之间的重复文件搬运

如果可行，可以评估：

- 是否能让 ComfyUI 直接读取共享路径
- 是否能复用本地共享卷
- 是否能绕过“下载到本地再上传一次”的流程

这项优化对本地生成节点的吞吐提升也会有帮助。

### 优先级 5：对 send-to-bot 做结果缓存/复用策略

例如：

- 首次发送后缓存 Telegram `file_id`
- 同一作品再次发送时尽量复用已有 `file_id`

这样可以减少重复的大文件上传。

---

## 11. 最后总结

### 11.1 当前 Web 数据流的本质

当前 Web 端已经实现了：

- 上传直达对象存储
- 生成走 BFF -> 中控 -> Redis -> Worker -> ComfyUI
- 历史/广场/收藏基于 `History` / `GalleryPost` / `UserInteraction`
- 媒体读取优先 `R2`，再按各接口策略回退到 `MinIO presigned URL` 或原始对象路径

这套架构方向是对的。

### 11.2 当前最值得优先优化的不是列表页，而是结果回传链路

如果带宽真的是当前瓶颈，那么最该优先处理的是：

1. 任务完成后结果文件在服务内被重复搬运
2. 收藏/投稿触发的 `R2` 热同步与缩略图生成
3. Worker 与 `ComfyUI` 之间的输入/输出文件中转

### 11.3 一句话判断

当前 Web 端真正消耗带宽的，不是“请求次数多”的地方，而是“媒体文件被多次复制”的地方。

---

## 12. 附录：现网接口/链路口径对照表

这一节只做一件事：

- 把几个最容易混淆的读链和回退策略拆开列清楚
- 默认以当前现网代码为准，而不是按抽象设计口径概括

### 12.1 history 相关接口

| 场景 | 接口 | 主要返回/行为 | 首选链路 | 未命中回退 | 是否经过 BFF 字节中转 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 历史列表 | `GET /api/users/history` | 返回 `output_file_url`、`thumbnail_url` 等元数据 | 优先探测 `R2` 对应 `history/{task_id}` 媒体与缩略图 | 原图/视频回退 `MinIO presigned URL`；缩略图若对象存在则回退缩略图的 `MinIO presigned URL` | 否 | 接口本身只下发元数据，真正媒体流量发生在浏览器加载 URL 时 |
| 收藏历史列表 | `GET /api/users/my-favorites` | 返回收藏历史的 `media_url`、`thumbnail_url` | 优先探测 `R2` | 回退 `MinIO presigned URL` | 否 | 本质上沿用 history 私有读链，只是查询条件变成 `History.is_favorited = true` |
| 删除历史 | `DELETE /api/users/history/{id}` | 软删除 `History`，必要时同步下架 `GalleryPost` | 无 | 无 | 否 | 主要是数据库写操作 |

### 12.2 gallery 相关接口

| 场景 | 接口 | 主要返回/行为 | 首选链路 | 未命中回退 | 是否经过 BFF 字节中转 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 广场列表 | `GET /api/gallery/posts` | 返回 `media_url`、`thumbnail_url`、点赞状态、作者信息等 | 优先探测 `R2` 公网 URL | 回退原始对象路径 `output_file` / `thumb_file`，不是统一回退 `MinIO presigned URL` | 否 | 前端再按对象存储域名去加载，命中不到 `R2` 时更容易直接打到源站 |
| 交互收藏列表 | `GET /api/gallery/my-favorites` | 返回“我点赞/应用过的帖子”子集 | 优先探测 `R2` | 回退原始对象路径 | 否 | 这条链路属于广场视图，不等同于私有收藏夹 |
| 点赞/点踩 | `POST /api/gallery/posts/{id}/interact?action=like|dislike` | 修改 `UserInteraction` 与帖子计数 | 无 | 无 | 否 | 纯元数据操作，不负责媒体搬运 |
| 投稿列表 | `GET /api/gallery/my-posts` | 返回自己投稿的帖子与媒体 URL | 优先探测 `R2` | 回退原始对象路径 | 否 | 读链口径与广场列表基本一致 |

### 12.3 favorites 相关接口

| 页面视角 | 实际数据源 | 接口 | 真实含义 | 首选链路 | 未命中回退 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| `/my-favorites`，`filter_type=favorite` | 私有历史 | `GET /api/users/my-favorites` | 我收藏的自己的历史作品 | 优先 `R2` | 回退 `MinIO presigned URL` | 私有读链 |
| `/my-favorites`，`filter_type=like|apply|all` | 广场交互记录 | `GET /api/gallery/my-favorites` | 我在广场点过赞或应用过的帖子 | 优先 `R2` | 回退原始对象路径 | 广场子集视图 |

### 12.4 apply-context 相关接口

| 场景 | 接口 | 返回的关键字段 | 输入素材 URL 的真实来源 | 回退策略 | 是否有副作用 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 从历史一键应用 | `GET /api/users/history/{task_id}/apply-context` | `prompt`、`lora_name`、`input_file`、`input_file_url`、`width/height/duration`、`billing_resolution`、`task_type` | 由 `history.input_file` 推断 bucket 后生成 `MinIO presigned URL` | 不走 `R2`，直接按对象路径生成预签名读链 | 有 | 可能补录媒体元数据、归一化 `billing_resolution` 并 `commit` |
| 从广场一键应用 | `GET /api/gallery/posts/{id}/apply-context` | 同上，且 `source_post_id=post.id` | 同样由 `history.input_file` 推断 bucket 后生成 `MinIO presigned URL` | 不走 `R2`，直接按对象路径生成预签名读链 | 有，但比历史口径更轻 | 当前主要是 `billing_resolution` 校正；前端通常先写入 `sessionStorage` 再跳转 |

补充理解：

- `apply-context` 本身返回的是轻量 JSON
- 但部分页面会直接复用 `input_file` / `input_file_url` 预填原始素材，所以它不是简单“只看提示词”的接口
- 真正的大流量通常发生在用户再次提交生成后，而不是取上下文这一步

### 12.5 send-to-bot 相关接口

| 场景 | 接口 | 读取源 | 实际传输链路 | 回退策略 | 是否经过 BFF 字节中转 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 发送历史结果到 Telegram 私聊 | `POST /api/users/history/{task_id}/send-to-bot` | `history.output_file` 指向的对象存储文件 | `MinIO -> BFF 内存字节流 -> Telegram Local API` | 无额外 CDN/R2 回退；核心是先把对象完整读入后端再上传 | 是 | 当前还带 TG 绑定校验、10 秒 Redis 防刷、图片/视频分流到 `sendPhoto/sendVideo` |

### 12.6 一眼区分

| 你想确认的问题 | 快速答案 |
| --- | --- |
| 哪些列表接口未命中后会回退 `MinIO presigned URL`？ | `users/history`、`users/my-favorites` |
| 哪些列表接口未命中后回退原始对象路径？ | `gallery/posts`、`gallery/my-favorites`、`gallery/my-posts` |
| 哪些接口虽然轻，但会顺带写库？ | 两类 `apply-context`，尤其 `users/history/{task_id}/apply-context` |
| 哪条链路一定是后端读字节再转发？ | `send-to-bot` |
| 哪些媒体展示通常不是 BFF 代理下载？ | history/gallery/favorites 的前端图片/视频展示，通常都是浏览器直连对象存储 URL |
