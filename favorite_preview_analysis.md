# Web 端“我的收藏”图片预览缺失与点击加载慢问题分析

## 结论先看

### 当前讨论结论更新：收藏查看链路改为优先走 R2

- 现状上，用户点击收藏后，后端在 [favorite_history](file:///home/hfy/APP/All_bot/src/web_api/routers/users.py#L209-L251) 里已经会异步触发：

```python
background_tasks.add_task(
    async_copy_to_r2_background, bucket_name, object_name, r2_object_name
)
```

- 既然收藏动作本身已经把原文件同步到 R2，那么“我的收藏”页面后续查看媒体时，**应优先走 R2 链接，而不是继续走 MinIO 预签名链接**。
- 这样做的目标很明确：
  - 列表预览走 R2 缩略图
  - 详情查看走 R2 原图 / 原视频
  - 只有在 R2 资源尚未就绪时，才回退到 MinIO

这意味着，后续修复方向已经不是“要不要走 R2”，而是：

1. 收藏接口返回的数据如何改成优先下发 R2 URL  
2. 收藏缩略图是否也在收藏时同步生成并同步到 R2  
3. R2 未同步完成时，前端和后端如何优雅降级  

### 高概率根因 1：收藏链路没有保证缩略图被生成

- `我的收藏` 走的是 `GET /users/my-favorites`，对应后端实现见 [users.py](file:///home/hfy/APP/All_bot/src/web_api/routers/users.py#L322-L423)。
- 这个接口会**直接给每条收藏记录拼一个缩略图预签名 URL**：

```python
thumb_object_name = f"{base_name}{thumb_ext}"
thumbnail_url = storage.get_presigned_url(thumb_object_name, bucket=bucket_name)
```

- 但这里**只是签出 URL，不会检查这个缩略图对象是否真的存在**。
- 真正负责生成缩略图的逻辑，在 [gallery_core.py](file:///home/hfy/APP/All_bot/src/core/gallery_core.py#L183-L186)：

```python
background_tasks.add_task(
    generate_and_upload_thumbnail, history.output_file, media_type
)
```

- 这段只出现在“投稿到广场”流程里，不在“收藏”流程里。
- “收藏”流程 [favorite_history](file:///home/hfy/APP/All_bot/src/web_api/routers/users.py#L209-L251) 目前只做了：
  - 标记 `is_favorited = True`
  - 触发原文件异步拷贝到 R2
- **没有触发缩略图生成**。

因此，如果某条收藏记录从未投稿、也未被历史脚本补过缩略图，那么：

1. 前端先拿到一个“看起来合法”的缩略图预签名 URL  
2. 实际请求这个 URL 时对象不存在  
3. 页面首屏预览就会失败  

这和你截图里“卡片区域灰底、没有真正图片预览”的现象高度吻合。

---

### 高概率根因 2：缩略图失败后，前端会回退到原图，导致加载很慢

前端收藏页实现见 [MyFavorites.vue](file:///home/hfy/APP/All_bot/frontend/src/views/MyFavorites.vue)。

它加载列表时，会优先把卡片 `src` 指向 `thumbnail_url`：

```ts
const src = getFileUrl(thumbUrl, p.id)
```

如果缩略图加载失败，则在 [handleImageError](file:///home/hfy/APP/All_bot/frontend/src/views/MyFavorites.vue#L378-L391) 中回退到原图：

```ts
img.src = post.media_url.includes('X-Amz-Signature')
  ? post.media_url
  : getFileUrl(post.media_url, post.id)
```

这就带来两个直接后果：

- 卡片预览阶段，如果缩略图不存在，就会退回去加载**原始大图**
- 原图通常远大于缩略图，移动端 WebView 下会明显更慢

也就是说，你现在看到的不是“纯前端不显示”，而更像是：

- 缩略图先失败
- 然后被迫加载原图
- 原图又比较大，所以你感觉“预览没了”和“点进去很慢”同时发生

这两个问题实际上是同一根链路上的前后表现。

---

### 高概率根因 3：详情弹窗直接加载原图，不走 R2 加速链路

收藏详情弹窗同样在 [MyFavorites.vue](file:///home/hfy/APP/All_bot/frontend/src/views/MyFavorites.vue#L515-L518)：

```vue
<img
  v-if="!isVideoFile(currentPost.media_url, currentPost.media_type)"
  :src="getFileUrl(currentPost.media_url, currentPost.id)"
/>
```

这里点击卡片后，详情页直接请求 `media_url` 原文件。

而 `favorite` 接口返回的 `media_url` 来自 [users.py](file:///home/hfy/APP/All_bot/src/web_api/routers/users.py#L357-L384)，本质是：

```python
media_url = storage.get_presigned_url(object_name, bucket=bucket_name)
```

也就是：

- 收藏详情不是读缩略图
- 也不是走 R2 加速链路
- 而是走 MinIO 预签名原图

对移动端来说，这天然比“先看缩略图 / 再按需拿大图 / 走 CDN”更慢。

你的第二张截图里“点开后顶部只出来一点点、整体黑很久”，非常像**大图正在缓慢加载中的过渡状态**，不是单纯样式错乱。

## 为什么“我的点赞 / 我的应用”可能正常，而“我的收藏”更差

这个差异来自后端返回链路不同。

### 点赞 / 应用

- 走 `GET /gallery/my-favorites`
- 数据组装在 [gallery.py](file:///home/hfy/APP/All_bot/src/web_api/routers/gallery.py#L125-L220)
- 媒体 URL 走 `get_media_url()`
- 当配置了 `R2_PUBLIC_DOMAIN` 时，会直接返回 CDN 公网地址

### 收藏

- 走 `GET /users/my-favorites`
- 后端逐条对 `History.output_file` 生成 MinIO 预签名 URL
- 没有复用广场那套 CDN 路由
- 也没有保证缩略图已存在

所以收藏页天然更容易出现：

- 缩略图缺失
- 回退大图
- 首屏慢
- 点详情更慢

## 关键证据

### 证据 1：收藏时没有触发缩略图生成

收藏接口 [users.py](file:///home/hfy/APP/All_bot/src/web_api/routers/users.py#L209-L251) 只有：

- `history.is_favorited = True`
- `async_copy_to_r2_background(...)`

没有：

- `generate_and_upload_thumbnail(...)`

### 证据 2：投稿时才会触发缩略图生成

[gallery_core.py](file:///home/hfy/APP/All_bot/src/core/gallery_core.py#L183-L186)

```python
background_tasks.add_task(
    generate_and_upload_thumbnail, history.output_file, media_type
)
```

### 证据 3：收藏列表后端会“无条件签出缩略图 URL”

[users.py](file:///home/hfy/APP/All_bot/src/web_api/routers/users.py#L373-L383)

```python
thumb_ext = "_thumb.jpg" if is_video else "_thumb.webp"
thumb_object_name = f"{base_name}{thumb_ext}"
thumbnail_url = storage.get_presigned_url(thumb_object_name, bucket=bucket_name)
```

这里没有对象存在性判断，因此“返回了一个缩略图 URL”并不等于“缩略图文件真的存在”。

### 证据 4：前端收藏页会把失败的缩略图回退到原图

[MyFavorites.vue](file:///home/hfy/APP/All_bot/frontend/src/views/MyFavorites.vue#L378-L391)

这会把“缩略图不存在”直接转化成“加载大图”，从而解释慢加载。

## 我目前的判断

### 最可能的真实故障链

1. 用户收藏了一条历史记录  
2. 该历史记录此前没有生成过缩略图  
3. `/users/my-favorites` 仍然返回一个缩略图预签名 URL  
4. 前端请求缩略图，得到 404 或加载失败  
5. 前端降级到原图  
6. 原图较大，移动端加载慢  
7. 点击详情后再次请求原图，于是更慢  

### 这比“纯前端 bug”更像“后端资源生命周期不完整”

我更倾向认为这不是单点样式问题，而是：

- 收藏链路缺少缩略图生成这一步
- 前端又在兜底时直接回源到大图
- 两者叠加后把问题放大到了用户可见层

## 还需要你确认的两个事实

如果你要我下一步继续深入，我建议优先确认这两点：

### 1. 问题是否集中在“未投稿过的收藏”

如果某些收藏项目是已经投稿到广场过的，而它们预览正常；另一些从未投稿过的收藏预览不正常，那几乎就能坐实“缩略图只在投稿链路生成”的判断。

### 2. 浏览器网络里缩略图是否 404

建议你在移动端 WebView 不方便时，桌面浏览器打开同页面抓一下网络请求：

- 查 `*_thumb.webp`
- 查 `*_thumb.jpg`

如果这些请求大量 404，而随后原图请求成功但较慢，这个问题就基本闭环了。

## 暂不改代码时，我建议的排查顺序

1. 先抽 3 条有问题的收藏记录，确认它们是否从未投稿
2. 对比这 3 条记录在对象存储里是否存在对应 `_thumb.webp` 或 `_thumb.jpg`
3. 看 `/users/my-favorites` 返回的 `thumbnail_url` 是否都能直接打开
4. 看失败后前端是否又请求了 `media_url`
5. 记录原图文件体积，如果是几 MB 到十几 MB，点击慢就很合理

## 修复方向更新

结合当前讨论，方向已经可以进一步收敛，不再把“是否走 R2”当成待定项，而是把它作为收藏查看链路的主方案。

### 方向 A：收藏查看链路统一改为 R2 优先

优点：

- 原图详情可直接走边缘分发，点击查看会明显更快
- 收藏卡片和详情页的媒体路由会与“已同步到 R2”这一事实保持一致
- 可以减少对 MinIO 预签名链接的依赖

风险：

- 收藏完成后，R2 同步存在短暂延迟窗口
- 如果后端直接返回 R2 地址，但对象尚未同步完成，前端仍会出现首跳失败

### 方向 B：在“收藏”时同时补缩略图，并同步到 R2

优点：

- 这是解决“预览没了”的关键
- 列表卡片真正能走小图，不必回退原图
- 能和“详情走 R2 原图”组成完整的 R2 加速链路

风险：

- 会增加收藏动作的后台异步任务
- 需要明确缩略图命名规则与 R2 对象名规则完全一致

### 方向 C：`/users/my-favorites` 返回时优先下发 R2 URL，MinIO 作为兜底

优点：

- 路由语义最清晰：收藏查看默认走 R2，未就绪时再走 MinIO
- 可以把“同步未完成”的问题收敛到后端一层处理
- 前端逻辑会比现在更简单

风险：

- 后端需要判断 R2 资源是否存在或是否可直接推导使用
- 如果每条记录都做存在性校验，列表接口会增加额外存储访问开销

### 方向 D：前端收藏页减少激进回退，避免把缩略图失败立即放大成大图卡顿

优点：

- 避免卡片瀑布流被大图拖慢
- 在 R2 缩略图尚未同步完成的短窗口里，用户至少不会被大图拖死首屏

风险：

- 没有缩略图时，卡片可能只能显示占位图
- 用户体验会从“慢”变成“先空后点开”

## 当前建议

基于目前的讨论结论，我建议后续实现按下面顺序推进：

1. 先把“我的收藏查看链路优先走 R2”定为正式方案
2. 在收藏动作里补上“缩略图生成 + 缩略图同步到 R2”
3. `GET /users/my-favorites` 优先返回 R2 原图与 R2 缩略图
4. 如果 R2 尚未同步完成，再由后端或前端降级到 MinIO
5. 最后再收紧前端回退策略，避免缩略图失败直接把列表拖成大图加载

---

## 实施清单

下面这部分按“可以直接开工拆任务”的粒度来写，方便后续开发时逐项勾选。

### 一、后端接口改造清单

#### 1. 收藏写入接口：`POST /users/history/{task_id}/favorite`

目标：

- 收藏动作完成后，不仅同步原文件到 R2，还要同步补齐缩略图链路

实施项：

- 保留现有 `is_favorited = True` 逻辑
- 保留现有原文件 `async_copy_to_r2_background(...)` 逻辑
- 追加缩略图生成任务：
  - 图片生成 `_thumb.webp`
  - 视频生成 `_thumb.jpg`
- 追加缩略图同步到 R2 的后台任务
- 确认后台任务失败仅告警，不阻断收藏成功响应

完成标准：

- 用户点收藏后，后台会同时推进：
  - 原文件 -> R2
  - 缩略图生成
  - 缩略图 -> R2

#### 2. 收藏列表接口：`GET /users/my-favorites`

目标：

- 返回值改成“R2 优先，MinIO 兜底”

实施项：

- 为每条记录统一组装两个候选地址：
  - `media_url`
  - `thumbnail_url`
- 优先返回 R2 地址
- 若 R2 对象尚未可用，则降级返回 MinIO 预签名地址
- 不再无条件返回一个可能不存在的缩略图 URL
- 后端优先处理 URL 选择，减少前端自行猜路径和拼路径

完成标准：

- 前端拿到的 `thumbnail_url` 尽量就是可直接访问的真实地址
- 列表接口不会再频繁下发“对象并不存在”的缩略图 URL

#### 3. 收藏详情数据链路

目标：

- 详情弹窗查看原图 / 原视频时优先走 R2

实施项：

- 确保 `GET /users/my-favorites` 返回的 `media_url` 已按 R2 优先组装
- 如果后续存在单独的“收藏详情接口”，该接口也必须统一采用相同规则
- 统一“收藏列表”和“收藏详情”两处媒体路由策略，避免一处走 R2、一处走 MinIO

完成标准：

- 点击收藏卡片进入详情时，不再默认走 MinIO 原图预签名

### 二、对象存储与命名规则清单

#### 1. R2 对象命名统一

目标：

- 保证原图和缩略图在 MinIO 与 R2 之间有可预测、可推导的一致命名

实施项：

- 原文件对象名继续沿用当前 basename 规则
- 图片缩略图统一使用 `_thumb.webp`
- 视频缩略图统一使用 `_thumb.jpg`
- 明确 R2 中缩略图对象名与 MinIO 对象名的映射规则
- 避免前后端各自推导一套不同的缩略图命名

完成标准：

- 给定任一 `output_file`，后端可以稳定推导：
  - MinIO 原文件对象名
  - MinIO 缩略图对象名
  - R2 原文件对象名
  - R2 缩略图对象名

#### 2. R2 就绪性判断

目标：

- 解决“刚收藏完，R2 还没同步完成”的短暂空窗期

实施项：

- 确认后端是否需要对 R2 做对象存在性检查
- 如果检查成本太高，可采用轻量策略：
  - 优先返回 R2
  - 首次失败后由前端兜底回 MinIO
- 如果接口层做检查，则尽量只检查缩略图，不对所有原图做重校验

完成标准：

- 刚收藏完的资源，即使 R2 还没同步完成，页面也不会长时间空白或卡死

### 三、前端改造清单

#### 1. 收藏列表页：`MyFavorites.vue`

目标：

- 简化前端路径推导逻辑，改为消费后端已经选好的 URL

实施项：

- 保留 `thumbnail_url` 作为列表卡片首选地址
- 不再默认把后端返回路径再次强制改写为 `_thumb.webp` / `_thumb.jpg`
- 优先信任后端返回的真实 `thumbnail_url`
- 仅在后端未返回可用缩略图时，才进入兜底逻辑

完成标准：

- 收藏页不再承担“猜测资源是否存在”的主要职责

#### 2. 收藏列表错误回退策略

目标：

- 避免缩略图失败后立刻把整个瀑布流拖入大图加载

实施项：

- 第一次缩略图失败时，先进入更轻量的兜底：
  - 显示占位图
  - 或尝试备用地址
- 不要对所有卡片立刻回退原图
- 如果必须回退原图，仅在单条卡片范围内生效

完成标准：

- 首屏列表保持流畅
- 单个资源异常不会拖慢整页

#### 3. 收藏详情弹窗

目标：

- 详情优先走 R2 原图 / 原视频

实施项：

- 直接使用后端返回的 `media_url`
- 若 `media_url` 已是完整 R2 地址，前端不再二次拼接存储前缀
- 仅在明确拿到的是相对路径或 MinIO 路径时才调用 `getFileUrl`

完成标准：

- 详情弹窗的媒体加载地址与后端策略保持一致，不再被前端误改写

### 四、降级与容错清单

#### 1. 收藏成功后短时间内的资源延迟

目标：

- 用户刚收藏完成后，即便后台任务尚未完成，也能正常查看

实施项：

- 后端：
  - R2 不可用时回 MinIO
  - 缩略图不可用时返回原图或空值，但不能返回假地址
- 前端：
  - 接收到空缩略图时显示占位图
  - 单张详情可允许回退原图
  - 列表不要大面积激进回退原图

完成标准：

- 任何单点同步延迟都不会让“我的收藏”整体不可用

#### 2. 异步任务失败

目标：

- 保持收藏动作可用，不让后台同步异常影响主流程

实施项：

- 原文件同步失败：记录 warning，继续允许 MinIO 查看
- 缩略图生成失败：记录 warning，列表显示占位或回退单图
- 缩略图同步失败：详情仍可走原图，列表继续兜底

完成标准：

- 收藏功能与查看功能对后台异步失败具备容错能力

### 五、联调与验证清单

#### 1. 功能验证

- 收藏一张从未投稿过的图片，确认列表预览正常
- 收藏一段从未投稿过的视频，确认列表封面正常
- 收藏后立刻进入“我的收藏”，确认不会长时间黑屏
- 点击详情，确认媒体优先从 R2 加载
- 取消收藏后，列表行为正常，不影响已存在对象

#### 2. 网络验证

- 浏览器 Network 确认列表缩略图优先命中 R2 地址
- 浏览器 Network 确认详情原图 / 原视频优先命中 R2 地址
- 人为制造 R2 未同步完成场景，确认会优雅降级到 MinIO
- 人为制造缩略图缺失场景，确认不会让整页回退大图瀑布流

#### 3. 性能验证

- 对比改造前后：
  - 收藏页首屏图片出现时间
  - 点击详情后的首帧 / 首图显示时间
  - 移动端弱网环境下的滚动流畅度
- 确认收藏页不再因为多张原图并发加载而明显卡顿

### 六、建议实施顺序

为了降低返工，我建议按下面顺序落地：

1. 先统一后端“收藏查看 URL 组装策略”，确定 `R2 优先、MinIO 兜底`
2. 再补“收藏时生成缩略图并同步到 R2”
3. 然后收敛前端 `MyFavorites.vue` 的路径猜测与激进回退
4. 最后做网络验证与移动端性能回归

### 七、最小可用版本

如果你想先快速止血，而不是一次做完整，我建议先上最小可用版本：

1. 收藏详情 `media_url` 优先走 R2
2. 收藏动作补上缩略图生成
3. 收藏列表缩略图优先走 R2，失败时不要立刻全量回退原图

这个版本已经能优先解决：

- 点击详情很慢
- 收藏卡片没预览
- 列表因大图回退而卡顿
