# Web API 的 R2 连接池打满问题分析与可实施方案

## 文档目的

这份文档基于当前代码实现重新整理，目标不是只解释“为什么会报 `Connection pool is full`”，而是给出一个可以直接落地、且不会引入新回归的实施版本。

这里特别强调两点：

- 本问题的主要热点链路，当前已确认集中在收藏列表的在线 `exists` 探测，而不是所有列表接口一视同仁。
- 某些方向虽然看起来合理，但如果脱离现有异步复制、legacy 兼容和 fallback 逻辑直接上，会引入真实 bug。

## 问题概述

- 近期多轮日志复查都稳定出现 `urllib3.connectionpool - WARNING - Connection pool is full, discarding connection`。
- 最新一次 10 分钟窗口内，`web-api` 出现了 `82` 次同类告警。
- 告警目标主机为 Cloudflare R2 域名，说明问题发生在 `web-api -> R2` 的对象访问链路，不是 Telegram、PostgreSQL、Redis 或内部网关。
- 结合当前代码实现，最主要的在线热点在收藏列表读取链路；广场公开列表更多是直接拼接 R2 公网 URL，不依赖在线 `HEAD` 探测。

## 直接现象

- 告警样式固定为：

```text
urllib3.connectionpool - WARNING - Connection pool is full, discarding connection: <r2-host>. Connection pool size: 10
```

- 这类日志虽然不会立刻把请求打成 500，但会带来几个实际风险：
  - 连接无法复用，导致额外建连开销
  - 存储探测延迟抬高，放大列表接口 RT
  - 高峰期可能进一步演化为真正的超时或级联抖动
  - 日志噪声过大，掩盖更高价值异常
  

## 影响范围

### 已确认直接相关

- `GET /api/users/my-favorites`
  - 当前实现会对 R2 主 key、legacy key 做存在性判断，并且并发探测缩略图是否存在。

### 可能间接受影响

- 缩略图生成与补齐链路
  - 当缩略图已存在于 MinIO、但还需要补同步到 R2 时，也会走一次 `async_r2_object_exists()` 判断。

### 不应和当前问题混为一谈

- `GET /api/gallery/posts`
  - 当前公开广场列表主要直接拼接 R2 公网 URL，不是这次连接池告警的核心在线探测来源。

## 关键代码位置

### 1. R2 客户端初始化未显式放大连接池

- 代码位置：[storage.py](file:///home/hfy/APP/All_bot/src/services/storage.py#L98-L108)

```python
self.r2_client = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    config=BotoConfig(signature_version="s3v4"),
    region_name="auto",
)
```

- 这里没有显式设置 `max_pool_connections`。
- `boto3/botocore` 默认连接池容量较小，在当前这种并发 `head_object` 模式下很容易被打满。

### 2. R2 存在性判断走 `head_object`

- 代码位置：[storage.py](file:///home/hfy/APP/All_bot/src/services/storage.py#L249-L259)

```python
def r2_object_exists(self, object_name: str) -> bool:
    if not self.r2_client or not self.r2_bucket:
        return False
    try:
        self.r2_client.head_object(Bucket=self.r2_bucket, Key=object_name)
        return True
    except Exception:
        return False
```

- 每次存在性判断都会发一个独立的 R2 `HEAD` 请求。
- 单次调用成本不高，但在列表页并发场景下很容易放大成连接池竞争。

### 3. 收藏列表会对多个候选 key 做在线探测

- 代码位置：[users.py](file:///home/hfy/APP/All_bot/src/web_api/routers/users.py#L42-L58)

```python
async def _get_r2_url_if_exists(object_key: str) -> str:
    public_url = storage.get_r2_public_url(object_key)
    if not public_url:
        return ""
    if await storage.async_r2_object_exists(object_key):
        return public_url
    return ""
```

- 代码位置：[users.py](file:///home/hfy/APP/All_bot/src/web_api/routers/users.py#L98-L109)

```python
media_r2_url, thumbnail_r2_url, thumb_exists = await asyncio.gather(
    _get_first_r2_url_if_exists(media_r2_key, legacy_media_r2_key),
    _get_first_r2_url_if_exists(thumb_r2_key, legacy_thumb_r2_key),
    storage.async_object_exists(bucket_name, thumb_object_name),
)
```

- 这里需要精确认知：
  - `_get_first_r2_url_if_exists()` 是顺序短路，不是“无条件同时探测主 key 和 legacy key”
  - 但当主 key miss 时，仍会继续探测 legacy key
  - 对媒体和缩略图分别都可能发生一次这样的回退
- 因此，真实问题不是“每条记录固定 4 次 R2 探测”，而是“在主 key 命中率不足时，单页请求会迅速放大 `HEAD` 请求量”。

### 4. 收藏后的 R2 同步是异步完成，不是写后立刻可见

- 代码位置：[users.py](file:///home/hfy/APP/All_bot/src/web_api/routers/users.py#L314-L329)

```python
background_tasks.add_task(
    async_copy_to_r2_background, bucket_name, object_name, r2_object_name
)
background_tasks.add_task(
    generate_and_upload_thumbnail,
    history.output_file,
    media_type,
    build_history_r2_thumbnail_key(history.task_id, media_type),
)
```

- 这意味着：
  - 收藏请求返回成功时，R2 对象和缩略图不一定已经上传完成
  - 列表页当前之所以还要做 `exists` 判断，是为了避免把还没同步成功的 R2 URL 直接下发给前端

### 5. 缩略图补齐链路也依赖 R2 exists 判断

- 代码位置：[media_processor.py](file:///home/hfy/APP/All_bot/src/core/media_processor.py#L47-L61)

```python
thumb_exists, r2_exists = await asyncio.gather(
    storage.async_object_exists(bucket_name, thumb_object_name),
    storage.async_r2_object_exists(target_r2_key),
)
if thumb_exists:
    if not r2_exists:
        await storage.async_copy_to_r2(
            bucket_name, thumb_object_name, target_r2_key
        )
```

- 这说明缓存策略不能只考虑读接口，还要考虑后台补同步链路的一致性。

## 根因判断

当前问题不是单点 bug，而是三个因素叠加：

### 根因 1：R2 客户端默认连接池太小

- 默认池容量无法承受当前收藏列表的并发探测模式。
- 一旦同一时间有多个协程一起做 `head_object`，很快就会出现池满告警。

### 根因 2：收藏列表存在“主 key + legacy key”的在线回退

- 这是兼容历史数据所必须付出的在线探测成本。
- 在主 key 命中率不够高时，请求量会被明显放大。

### 根因 3：缺少短时缓存，重复请求无法复用判断结果

- 用户连续翻页、刷新、反复进入收藏页时，会对同一批 key 重复执行 `head_object`。
- 当前没有任何短 TTL 的“对象存在性缓存”。

## 为什么这是 P1

- 它不是纯日志噪声，而是在持续消耗连接池和建连资源。
- 它已经稳定复现，不依赖偶发外部限流。
- 它直接影响线上高频页面的稳定性和响应时间。
- 如果不治理，随着收藏量和列表访问量提升，后续只会从 `WARNING` 演化成真实接口退化。

## 可实施方案

下面按“立即止血 -> 安全优化 -> 长期演进”分层给出建议，并明确每一项的前提与风险。

### 方案 A：先扩大 R2 连接池容量

这是最快速、最直接、风险最低的止血手段。

- 修改位置：[storage.py](file:///home/hfy/APP/All_bot/src/services/storage.py#L98-L108)
- 实施建议：
  - 为 `boto3.client` 显式配置更大的 `max_pool_connections`
  - 建议起步值：`50`
  - 如果线上确认收藏页峰值更高，可直接取 `100`

示意：

```python
from botocore.config import Config as BotoConfig

self.r2_client = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    config=BotoConfig(
        signature_version="s3v4",
        max_pool_connections=100,
    ),
    region_name="auto",
)
```

优点：

- 改动最小
- 见效最快
- 不改变现有业务语义

限制：

- 只能缓解，不能根治“探测过多”的问题

### 方案 B：给 R2 exists 判断加短缓存，但必须区分正负缓存

这是值得做的结构优化，但不能按“统一 TTL 30~120 秒”粗暴落地。

#### 推荐策略

- 正缓存：`exists=True`
  - TTL 可取 `30s ~ 120s`
- 负缓存：`exists=False`
  - TTL 必须更短，建议 `3s ~ 10s`
- 写后失效或回填：
  - 收藏成功后触发的 `async_copy_to_r2_background`
  - 缩略图补齐成功后的 `async_copy_to_r2`
  - 以上链路一旦复制成功，应主动删除旧的负缓存，或直接回填正缓存

#### 为什么必须这样做

如果把 `False` 结果也缓存 30~120 秒，会出现真实回归：

- 用户刚收藏后第一次进入列表
- 此时后台 R2 同步可能还没完成，第一次 `HEAD` 返回不存在
- 负缓存被写入
- 即使 1 秒后后台已经同步完成，后续多个请求仍会继续拿到“对象不存在”的旧结果

这会导致：

- 收藏图继续走降级路径
- 缩略图继续为空
- 用户误以为收藏资源没有同步成功

#### 适合缓存的数据

- `r2_key -> exists / not exists`

#### 注意事项

- 缓存应放在 `async_r2_object_exists()` 这一层或其上层统一封装，避免多个调用方各自实现一套缓存逻辑。
- 不要只在 `GET /api/users/my-favorites` 上做局部缓存而忽略后台缩略图补齐链路。

### 方案 C：保留主 key 优先，但不要在未完成数据迁移前直接删除 legacy 回退

目标不是“马上砍掉 legacy”，而是“在有数据前提下安全收缩 legacy 探测”。

#### 当前事实

- 收藏列表当前依赖：
  - history 主 key
  - legacy basename key
  - MinIO 缩略图 fallback
- 代码位置：[users.py](file:///home/hfy/APP/All_bot/src/web_api/routers/users.py#L95-L109)

#### 可实施做法

1. 保持主 key 优先、legacy key 兜底的现状不变  
2. 增加命中率统计  
3. 确认主 key 命中率已经足够高后，再灰度下线 legacy 回退  
4. 或先做离线历史数据补齐，再减少在线双探测

#### 不可直接做的事

- 不能仅凭“想减少 HEAD 请求”就删除 legacy 回退逻辑。

否则会导致：

- 历史收藏数据拿不到 R2 URL
- 一部分旧资源缩略图直接丢失
- 线上出现“老收藏可见性回退”

### 方案 D：不要把“稳定 URL 下发”理解成“无条件直接返回 R2 URL”

这是文档里最容易被误用的一点。

#### 当前前提

- 收藏后的 R2 上传是后台异步完成
- `storage.get_r2_public_url()` 只是拼接 URL，不校验对象是否真实存在
- 代码位置：[storage.py](file:///home/hfy/APP/All_bot/src/services/storage.py#L261-L265)

#### 因此不能直接这样做

- 一收藏就给列表接口直接返回 `history/{task_id}/original.*` 或 `history/{task_id}/thumb.*`

因为这会在同步尚未完成时把真实 404 URL 下发给前端。

#### 更安全的演进方向

- 第一阶段：
  - 保留 `exists` 判断
  - 用缓存减少重复 `HEAD`
- 第二阶段：
  - 在“复制成功”后把稳定 key 固化到数据库字段或状态位
  - 只有状态明确可用时，列表接口才直接返回稳定 URL

### 方案 E：必要时增加并发限制，但只能作为兜底手段

如果短期内不能立即完成缓存与收缩探测，可以增加并发限制抑制尖峰。

例如：

- 用 `asyncio.Semaphore` 限制同一时刻的 `head_object` 并发数

优点：

- 能抑制瞬时打爆连接池

缺点：

- 会把问题从“瞬时太猛”换成“整体更慢”
- 如果阈值设置过小，会明显拖慢收藏页 RT
- 这不是减少请求量，只是在限流

## 不可直接照抄实施的高风险点

下面几项必须在落地时显式写入开发说明，否则很容易把“优化”做成“回归”：

### 风险 1：负缓存过长

- 会把“刚同步成功的对象”继续判成不存在。

### 风险 2：未迁移完成前删除 legacy 回退

- 会导致历史收藏资源丢图或缩略图缺失。

### 风险 3：无条件直接返回稳定 R2 URL

- 会让刚收藏但尚未完成异步同步的对象直接返回 404 链接。

### 风险 4：只在接口层做局部优化

- 可能遗漏后台缩略图补齐链路，导致缓存行为和实际对象状态不一致。

## 推荐落地顺序

我建议按下面顺序推进，收益最大且返工最少：

### 第一阶段：快速止血

1. 提高 `max_pool_connections`
2. 观察 `Connection pool is full` 告警是否显著下降

### 第二阶段：安全减压

3. 给 `async_r2_object_exists()` 增加正负分离缓存
4. 在 R2 复制成功后主动失效或回填缓存
5. 如仍有尖峰，再增加适度并发限制

### 第三阶段：削减在线探测

6. 统计主 key 与 legacy key 命中率
7. 先补齐历史数据，再灰度下线 legacy 回退

### 第四阶段：结构优化

8. 把“资源已稳定同步到 R2”的状态前移为可判定事实
9. 让列表接口只在状态明确时直接返回稳定 URL，逐步减少在线 exists 判断

## 验证标准

修复后建议重点看下面几项：

### 日志指标

- `Connection pool is full` 在相同访问模式下明显下降，最好归零

### 接口表现

- `GET /api/users/my-favorites` RT 下降
- 收藏页高峰期首屏更稳定

### 探测量

- 同一批 key 在短时间内不再重复触发大量 `HEAD` 请求
- 主 key miss 后的 legacy 回退比例可观测

### 一致性

- 收藏成功后，资源在短时间内能自然切换到 R2，不会被长时间错误判定为不存在
- 不出现“收藏成功但返回 404 CDN 链接”的回归

## 最终结论

- 当前问题的本质不是 R2 服务故障，而是“高并发 exists 探测策略”与默认连接池容量不匹配。
- 最先该做的是：扩大 R2 连接池。
- 最值得做的结构优化是：给 exists 判断加带失效机制的短缓存，而且正负缓存必须分离。
- 真正的长期解法不是简单删除判断，而是先把历史兼容和异步同步链路梳理清楚，再逐步减少在线探测。
