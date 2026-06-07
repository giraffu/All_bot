# 稳妥生产版: 云控制面 + R2 + 本地 GPU 迁移计划

生成时间：2026-06-05，Asia/Shanghai  
状态更新：2026-06-07 晚间已完成正式切换，本文件保留为迁移方案历史依据。当前生产 SOP 以 `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`、`docs/子模块_运维指南与容器管理_ops_deployment.md` 和 `正式服务_云发布环境迁移计划.md` 顶部状态为准。

## 1. 结论

推荐采用“云控制面 + 托管数据层 + Cloudflare R2 + 武汉本地 GPU”的混合架构。

核心判断：

- 当前真正稀缺的是本地 GPU 算力：4 台 GPU 服务器、7 张卡、总名义显存约 288GB，其中 3 张 RTX 5090 32G、4 张 RTX 4090 48G。用云 GPU 24 小时替换这批卡，成本会远高于保留本地算力。
- 当前主服务器的 CPU、Postgres 和 Redis 不是第一瓶颈；瓶颈在 GPU 吞吐、视频任务长尾、武汉电信家庭宽带作为公网入口的稳定性，以及 MinIO 公开访问/回源压力。
- 因此生产稳妥版应该把用户入口、Bot、Web API、支付回调、中控 API、Dashboard、Postgres、Redis 放到新加坡云侧；本地只保留 GPU、ComfyUI、worker agent、本地热缓存和管理工具。
- 公共媒体访问优先走 R2，不再让用户结果页、画廊和缩略图依赖武汉家庭宽带公网链路。

目标拓扑：

```text
用户 / Telegram / 支付回调
  -> Cloudflare DNS / WAF / Access / Workers
  -> 新加坡云控制面
       - tg-bot
       - web-api
       - payment-api
       - Central API
       - Dashboard
       - imgproxy
       - Managed PostgreSQL
       - Managed Valkey/Redis
  -> Tailscale/出站隧道
  -> 武汉本地 GPU 池
       - comfy-agent-1..7
       - ComfyUI 192.168.1.226 / .177 / .252 / .2
       - MinIO 热缓存
  -> Cloudflare R2 公开媒体分发
```

## 2. 采购清单

### 2.1 主推荐采购

| 项目 | 推荐规格 | 用途 | 官方价格依据 | 预计月费 |
| :--- | :--- | :--- | :--- | ---: |
| DigitalOcean Droplet, Singapore | Basic 16GiB RAM / 8 vCPU / 320GiB SSD / 6TiB transfer | 云控制面 App 节点，跑 Bot/Web/Payment/Central/Dashboard/imgproxy | DigitalOcean Droplets 官方价格：16GiB/8vCPU 为 96 USD/月 | 96 USD |
| DigitalOcean Managed PostgreSQL, Singapore | 4GiB RAM / 2 vCPU / 60-120GiB storage range | 生产 `bot_db`，当前约 2.6GB，留足历史和索引增长空间 | DigitalOcean Managed Databases 官方价格：PostgreSQL 4GiB/2vCPU 为 60.90 USD/月 | 60.90 USD |
| DigitalOcean Managed Valkey, Singapore | 1GiB RAM / 1 vCPU / 10GiB disk | Redis/Valkey，当前 Redis 约 58.69MB，1GiB 足够但需监控 key 增长 | DigitalOcean Managed Databases 官方价格：Valkey 1GiB 为 15 USD/月 | 15 USD |
| Cloudflare Workers Paid | 标准 Paid | 媒体网关、R2 访问控制、轻量 API 边缘逻辑、Pages Functions 余量 | Cloudflare Workers 官方价格：5 USD/月基础订阅 | 5 USD |
| Cloudflare R2 Standard | 先按 0.5-1TiB 规划 | 公开结果、缩略图、画廊媒体、备份归档 | R2 Standard storage 0.015 USD/GB-month，Class A 4.50 USD/百万，Class B 0.36 USD/百万，无公网出站流量费 | 约 10-45 USD |
| Tailscale | Personal 或 Standard | 云控制面与武汉 GPU/管理节点组网 | Personal 当前 0 USD，可到 6 用户；Standard 为 8 USD/用户/月 | 0-16 USD |

稳妥生产版预计月费：约 187-237 USD/月，不含税、不含额外快照、不含突发云 GPU。

这个版本比“单台便宜 VPS 自托管数据库”贵，但换来两点稳定性：数据库/Redis 不和 App 容器抢同一台机器资源，且数据库备份、版本维护、故障恢复由托管服务承接。以当前数据量看，这个成本比全量云 GPU 替换本地 7 张卡要低得多。

### 2.2 `$48/mo` 过渡生产判断

DigitalOcean Basic Regular `$48/mo` 的页面规格为 `4 vCPU / 8GB RAM / 160GB SSD / 5TB transfer`。它可以先支撑正式服务的“过渡生产控制面”，但前提是数据面和媒体面不压到这台机器上。

可用条件：

- Postgres 使用 DigitalOcean Managed PostgreSQL 或其他托管库，不在这台 Droplet 上长期自托管生产 `bot_db`。
- Redis/Valkey 使用托管服务，不在这台 Droplet 上承载完整生产 Redis。
- MinIO 不迁到这台 Droplet；公开媒体走 R2，本地 MinIO 只保留武汉热缓存。
- 本地 7 张 GPU 和 ComfyUI 不迁移，`comfy-agent-1..7` 通过 Tailscale 访问云 Central API。
- `web-api`、Dashboard backend、imgproxy 的 worker/concurrency 按 4 vCPU 控制，不能照搬当前主服务器余量配置。

建议初始规格口径：

| 服务 | `$48/mo` 初始建议 |
| :--- | :--- |
| `web-api` | 2-3 个 Uvicorn worker 起步，压测后再调 |
| `dashboard-backend` | 1-2 个 worker 起步 |
| `imgproxy` | 并发 4-6 起步，优先处理 R2 URL |
| `tg-bot` | 单实例，确保全网只有一个生产 bot |
| `payment-api` | 单实例，重点验证回调幂等 |
| Central API | 单实例，端口只允许本机/Tailscale |

升级触发条件：

- App 节点 CPU 连续 15 分钟超过 70%。
- 可用内存长期低于 1.5GB 或出现 OOM。
- Web API p95 延迟明显上升，或 Cloudflare 502/504 增加。
- Postgres/Valkey 连接池耗尽。
- Central queue/running 状态正常但 API 响应变慢。
- Dashboard 查询影响 Web/API 响应。

结论：`$48/mo` 可以作为第一阶段正式入口，但不是长期稳妥生产规格。正式业务稳定后，或出现上述任一升级触发条件，应升级到 `$96/mo` 的 `8 vCPU / 16GB RAM / 320GB SSD / 6TB transfer`。

### 2.3 省钱替代

如果需要先把月费压低，可用 Hetzner Singapore `CPX52` 或 `CCX33` 单机自托管 Postgres/Redis：

- `CPX52`：12 vCPU / 24GB RAM / 480GB SSD，新加坡价格约 92.49 USD/月。
- `CCX33`：8 dedicated vCPU / 32GB RAM / 240GB SSD，新加坡价格约 114.49 USD/月。

省钱替代适合测试或过渡，但生产稳妥性弱于托管数据库方案，因为 App、Postgres、Redis 又集中到同一台云 VM 上。

### 2.4 下单前必须复核

云服务价格会变。正式采购当天必须重新打开官方价格页核对：

- Cloudflare R2 pricing: https://developers.cloudflare.com/r2/pricing/
- Cloudflare Workers pricing: https://developers.cloudflare.com/workers/platform/pricing/
- DigitalOcean Droplets pricing: https://www.digitalocean.com/pricing/droplets
- DigitalOcean Managed Databases pricing: https://www.digitalocean.com/pricing/managed-databases
- Tailscale pricing: https://tailscale.com/pricing
- Hetzner Cloud pricing / price adjustment: https://www.hetzner.com/cloud/regular-performance 和 https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/

## 3. 成本测算依据

当前系统资源快照来自 `docs/子模块_系统资源与容量画像_resource_inventory.md`：

- 注册用户约 124,439。
- 近 1 天活跃用户约 7,594。
- 近 30 天活跃用户约 40,689。
- 近 1 天历史记录约 23,070。
- 近 30 天历史记录约 755,736。
- 生产数据库 `bot_db` 约 2.6GB。
- Redis 约 58.69MB。
- MinIO 本地数据约 453GB，其中 `bot-data` 268GB，`comfyui-temp` 182GB。
- 本地 GPU 池 7 张卡，总名义显存约 288GB。

R2 粗算：

- 仅按当前 MinIO 453GB 全量进入 R2 Standard：453 * 0.015 = 6.80 USD/月。
- 如果按 1TiB 预留：1024 * 0.015 = 15.36 USD/月。
- Class A 写入按 23,070 任务/日、平均每任务 2 个对象估算：月写入约 1.38M，对免费 1M 后约 0.38M 计费，约 1.71 USD/月。
- Class B 读取取决于画廊、结果页和缩略图访问。30M 次/月时，免费 10M 后约 7.20 USD；90M 次/月时约 32.40 USD。
- R2 不收公网出站流量费，但 GET/HEAD 等读取仍算 Class B，所以必须配 Cloudflare 缓存、缩略图缓存和 R2 HEAD 快探测超时。

数据库粗算：

- 当前 `bot_db` 2.6GB，最大表 `history` 约 1.58GB，30 天新增历史约 75.6 万条。DigitalOcean Managed PostgreSQL 4GiB/2vCPU 的 60-120GB 存储范围能覆盖当前规模和一段增长期。
- Redis 当前 58.69MB，Valkey 1GiB 有足够余量；重点监控 Central 队列、worker heartbeat、pending finalizer、限流 key 是否异常增长。

## 4. 服务迁移矩阵

| 当前服务/容器 | 当前位置 | 目标位置 | 迁移动作 | 关键风险 |
| :--- | :--- | :--- | :--- | :--- |
| `tg-bot` | 武汉主服务器 | 云控制面 | 迁到云 App 节点，`API_BASE` 指向云 Central API 内网地址；切换时必须保证全网只有一个生产 bot 在线 | 双 bot 会造成重复消息、重复扣费或状态错乱 |
| `web-api` | 武汉主服务器 | 云控制面 | 迁到云 App 节点，连接 Managed PostgreSQL/Valkey，R2 作为结果优先 URL | 环境变量、R2 fallback、JWT/session 语义 |
| `payment-api` | 武汉主服务器 | 云控制面 | 迁到云 App 节点，Cloudflare 域名和支付回调指向云端；旧端切换后停写 | 回调 split-brain 会导致旧库/新库分裂 |
| `backend_api_1` / Central API | 武汉主服务器 `8003` | 云控制面私网 | 迁到云 App 节点，端口只允许本机、Tailscale 或内网访问；worker 通过 Tailscale 访问 | Central API 不得公网裸露 |
| `dashboard_dashboard-backend_1` | 武汉主服务器 | 云控制面 | 迁到云 App 节点，连接云 Postgres/Valkey；前面加 Cloudflare Access | 管理后台必须做访问控制 |
| `dashboard_dashboard-frontend_1` | 武汉主服务器 | 云控制面或 Cloudflare Pages | 稳妥版先保留容器部署；后续可静态发布到 Cloudflare Pages | 前后端 API origin 和登录态 |
| `imgproxy` | 武汉主服务器 | 云控制面 | 迁到云 App 节点，优先拉 R2 公网 URL，不走武汉 MinIO 回源 | 防止大图/动图打爆云 VM |
| `postgres-server` | 武汉主服务器 | Managed PostgreSQL | 用 `pg_dump -Fc` / `pg_restore` 迁移，生产切换窗口执行 final dump | 迁移窗口内不能有旧库继续写入 |
| `redis-server` | 武汉主服务器 | Managed Valkey | 队列/运行态不热迁移；先 drain 任务。认证黑名单等 key 需要单独审计，必要时切换后强制 Web 重新登录 | 热迁 Central 队列容易产生僵尸任务 |
| `minio-server` | 武汉主服务器 | 本地保留热缓存 | 不作为公开主路径；结果和画廊优先 R2。保留 worker 输入/结果热中转和旧文件 fallback | MinIO 不能继续承担公网大流量 |
| `comfy-agent-1..7` | 武汉主服务器 | 武汉保留 | 不迁云；只把 `MASTER_API_URL` 从本地 `127.0.0.1:8003` 改为云 Central 的 Tailscale 地址 | agent token、Tailscale ACL、任务 drain |
| ComfyUI 7 个端口 | 武汉 GPU 节点 | 武汉保留 | 不改 ComfyUI 地址；agent 继续访问 `192.168.1.*:8188/8189` | 本地内网和 GPU 节点磁盘，尤其 `.177` |
| `filebrowser` | 武汉主服务器 | 武汉保留 | 仅通过 Tailscale/Access 管理，不公开到公网 | 文件管理面板不应公网裸露 |
| `pgadmin-server` | 武汉主服务器 | 停用或内网保留 | 生产数据库改托管后，pgAdmin 只允许 Tailscale 管理云 DB | 数据库管理入口暴露风险 |
| `portainer_agent` | 武汉主服务器 | 武汉保留 | 仅用于本地容器管理，关闭公网暴露 | 管理 API 暴露风险 |
| `monitor_node_exporter` | 武汉主服务器 | 武汉保留，并新增云监控 | 本地继续监控 GPU/主机；云侧新增 node exporter 或 DO Monitoring | 监控割裂，需要统一告警 |
| `tg-bot-test` / `web-api-test` / `payment-api-test` | 武汉测试栈 | 云测试栈或本地保留 | 先做云测试栈，接 1-2 个测试 agent，不占满生产 GPU | 测试任务影响生产 GPU |
| `central-api-test` | 武汉测试栈 | 云测试中控 | 迁到云 App 节点测试端口，仅内网/Tailscale 可达 | 测试 Central 不能误接生产 agent |
| `comfy-agent-test-1..7` | 武汉测试栈 | 武汉保留，按需减少 | 初期只启 1-2 个测试 agent 指向云测试 Central | 测试 agent 和生产 agent 共享物理 GPU |
| `cs-bot` | 武汉主服务器，依赖 LM Studio `host.docker.internal:1234` | 先保留武汉 | 若 Telegram 链路不稳，再把 bot 容器迁云，LLM API 通过 Tailscale 访问本地 LM Studio | 本地 LLM 服务不应公网暴露 |

## 5. 目标部署结构

建议后续新增云部署文件，不直接改现有生产 compose，避免误伤本地生产：

```text
deploy/docker-compose-cloud.yml
backend/docker-compose-cloud.yml
dashboard/docker-compose-cloud.yml
deploy/docker-compose-cloud-test.yml
backend/docker-compose-cloud-test.yml
.env.cloud.prod       # 不提交 git
.env.cloud.test       # 不提交 git
scripts/safe_deploy_cloud_test.sh
scripts/safe_deploy_cloud_prod.sh
```

云侧服务边界：

- `deploy/docker-compose-cloud.yml`：`bot`、`web-api`、`payment-api`、`imgproxy`。
- `backend/docker-compose-cloud.yml`：Central API `api`。
- `dashboard/docker-compose-cloud.yml`：`dashboard-backend`、`dashboard-frontend`。
- Postgres/Valkey 使用托管服务，不放进 compose。
- Nginx/Caddy/Traefik 任取一个作为云侧反向代理；只开放 `80/443`，SSH 限 IP 或仅 Tailscale。

云侧必须关闭公网端口：

- 不公开 `8000`、`8003`、`8043`。
- 不公开 `5432`、`6379`。
- 不公开 MinIO `9000/9001`。
- Central API 只能被本机服务和 Tailscale 内的 worker 访问。

## 6. 迁移阶段计划

### 阶段 0: 准备与冻结规则

目标：不动生产，只补齐可回滚条件。

动作：

1. 重新采集资源快照：Postgres 大小、表大小、Redis keyspace、Central pending/running、MinIO 桶大小、R2 命中率、GPU 节点磁盘。
2. 记录当前生产镜像、容器、环境变量键名，不记录密钥值。
3. 梳理 Redis key 类型：
   - 可冷启动：Central pending/running、active task、heartbeat、限流、临时锁。
   - 需评估连续性：JWT blacklist、安全通知、登录限流、pending finalizer。
4. 定义维护模式：切换窗口内禁止新任务进入，等待 Central 队列清空。
5. 设置 Cloudflare DNS 低 TTL，准备新 origin，但不切换。
6. 准备 R2 生产桶和测试桶，配置 CORS、生命周期、缓存规则。

阶段完成标准：

- 已确认当前生产任务可 drain。
- 已确认数据库 final dump 所需时间。
- 已确认支付回调切换方式。
- 已确认云端和本地通过 Tailscale 可互通。

### 阶段 1: 云基础设施

目标：让云 App 节点、托管 DB、托管 Redis 可用，但不接生产流量。

动作：

1. 创建 DigitalOcean Singapore Droplet：Ubuntu 24.04 LTS，Basic 16GiB/8vCPU。
2. 创建 Managed PostgreSQL 4GiB/2vCPU。
3. 创建 Managed Valkey 1GiB。
4. 配置 DO Cloud Firewall：
   - 入站 `80/443` 开放给 Cloudflare/公网。
   - SSH 仅允许固定管理 IP 或 Tailscale。
   - PostgreSQL/Valkey 仅允许云 App Droplet 访问。
5. 安装 Docker、Compose v2、Tailscale、基础监控、日志轮转。
6. 加入 Tailscale tailnet，给云 App 节点打 `tag:allbot-cloud-control`。
7. Tailscale ACL 允许本地 `comfy-agent` 节点访问云 Central API 端口，不允许访问 Postgres/Valkey。

阶段完成标准：

- 云节点能访问 Managed PostgreSQL/Valkey。
- 武汉主服务器能通过 Tailscale 访问云 Central API 测试端口。
- 云节点出站访问 Telegram、Cloudflare R2、支付服务商正常。

### 阶段 2: 云测试栈

目标：先把测试环境跑起来，验证链路，不碰生产。

动作：

1. 从 `bot_db_test` 导出测试库，恢复到云测试库。
2. 新建 `.env.cloud.test`，指向云测试 DB、云 Valkey 测试 DB/index、R2 测试桶。
3. 启动云测试 Central API。
4. 启动云测试 `web-api-test`、`payment-api-test`、`dashboard`。
5. 只重启 1-2 个测试 agent，让它们指向云测试 Central API。
6. 验证：
   - `/api/health`
   - Central `/health`
   - worker heartbeat
   - Web 测试任务提交
   - ComfyUI 执行
   - Worker complete 回流
   - Web monitor 落库
   - R2 warmup
   - `/result` 返回 R2 URL
   - Dashboard 能看到队列和 worker 状态

阶段完成标准：

- 测试任务能完整完成。
- R2 未 ready 时图片 fallback 正常，视频保持 `pending_result`。
- 测试 payment callback 使用测试配置，不触碰生产订单。

### 阶段 3: R2 媒体分层

目标：把公开访问从武汉 MinIO 迁到 R2。

动作：

1. 生产 R2 桶建议：
   - `allbot-media-prod`：公开结果、缩略图、画廊媒体。
   - `allbot-media-test`：测试媒体。
   - `allbot-backup-prod`：数据库 dump、配置备份、迁移快照。
2. 配置 R2 custom domain，例如：
   - `media.example.com`
   - `media-test.example.com`
3. 保持现有代码策略：结果 URL 优先 R2，找不到对象才 fallback 原始存储路径；视频 owner result 必须等 R2。
4. 先 warmup 最近 7-14 天的结果和画廊媒体，历史旧文件采用 lazy migration。
5. MinIO 生命周期：
   - 生产热结果保留 14-30 天。
   - 测试桶定期清理。
   - 旧结果长期访问走 R2。

阶段完成标准：

- 结果页、历史、画廊、缩略图优先返回 R2。
- MinIO 回源率下降。
- R2 Class B 请求量可被 Cloudflare cache 控制。

### 阶段 4: 生产 dry-run

目标：在不切流量的情况下演练完整数据迁移。

动作：

1. 从当前生产库执行一次 dry-run dump：

```bash
pg_dump -Fc --no-owner --no-acl -d bot_db -f /tmp/bot_db_dryrun.dump
```

2. 在云端临时库 restore：

```bash
pg_restore --clean --if-exists --no-owner -d bot_db_dryrun /tmp/bot_db_dryrun.dump
```

3. 云端执行 Alembic 检查：

```bash
alembic heads
alembic upgrade head
```

4. 对比关键数据：
   - `users` 总数。
   - `history` 总数。
   - `orders` 总数。
   - `gallery_posts` 总数。
   - 最近 24 小时订单和历史。
5. 云端启动生产配置但不对外暴露，使用内网/临时域名验证 health。

阶段完成标准：

- dry-run restore 成功。
- Alembic 无 multiple heads。
- 数据行数对齐。
- 云端生产配置健康，但未接真实生产流量。

### 阶段 5: 正式切换

目标：用最小停机窗口把生产入口和数据层切到云。

建议维护窗口：低峰期 30-90 分钟。

动作顺序：

1. 开启维护模式，停止新任务提交。
2. 等待运行任务完成：
   - Bot/Web active tasks 为 0。
   - Central pending queue 为 0。
   - Central running set 为 0。
   - pending web finalizers 清空或可审计。
3. 停止本地生产入口，避免旧库继续写：
   - `tg-bot`
   - `web-api`
   - `payment-api`
4. 保留本地 worker 暂停接新任务，不直接删除容器。
5. 执行 final dump：

```bash
pg_dump -Fc --no-owner --no-acl -d bot_db -f /tmp/bot_db_final_$(date +%Y%m%d_%H%M%S).dump
```

6. 恢复到 Managed PostgreSQL。
7. 云端执行 `alembic upgrade head`。
8. Redis/Valkey 处理：
   - Central 队列不迁移，保持空启动。
   - 如不迁移 JWT blacklist，则切换后强制 Web 用户重新登录，或旋转 token 版本策略。
   - 支付幂等以数据库订单/流水为准，不能依赖旧 Redis。
9. 启动云生产服务：
   - Central API
   - web-api
   - payment-api
   - dashboard
   - imgproxy
   - tg-bot 最后启动
10. 修改本地 `comfy-agent-1..7`：
    - `MASTER_API_URL` 指向云 Central API 的 Tailscale URL。
    - `COMFY_API_URL` 保持本地 `192.168.1.*`。
    - `MINIO_ENDPOINT` 初期仍指向本地 MinIO，结果同时 warmup R2。
11. 重启本地生产 agent，验证 7 个 heartbeat。
12. Cloudflare DNS/API origin 切到云 App 节点。
13. 支付回调域名切到云 payment-api。

阶段完成标准：

- 云 `web-api` health 正常。
- 云 Central API health 正常。
- 7 个生产 worker heartbeat 正常。
- Bot 只存在云端一个生产实例。
- 支付回调打到云端。
- Web 能登录、提交任务、看到结果。
- R2 结果 URL 正常。

### 阶段 6: 切后观察

目标：确认没有隐性 split-brain 和结果链路问题。

切后 24 小时重点看：

- Web 5xx、502、504。
- Payment callback 成功率和重复回调幂等。
- Central pending/running 是否异常堆积。
- Worker `idle/running/error/quarantined` 状态。
- R2 HEAD/GET 失败率。
- MinIO fallback 比例。
- Postgres 连接数、慢查询、CPU、IO。
- Valkey 内存和 keyspace。
- 本地 GPU 节点磁盘，尤其 `192.168.1.177`。

切后 7 天动作：

- 降低本地 MinIO 公开依赖。
- 整理旧 VPS 转发链路，只保留必要 fallback。
- 建立每天数据库备份到 R2。
- 建立每周恢复演练。
- 把云部署脚本固化为 `safe_deploy_cloud_test.sh` / `safe_deploy_cloud_prod.sh`。

## 7. 回滚策略

### 7.1 切换前回滚

如果还未切 DNS、未启动云生产 bot、未写入云生产 DB：

- 直接保持本地生产不变。
- 删除或停止云端临时服务。
- 不影响用户。

### 7.2 切换后短窗口回滚

如果云端已经接收写入，不能简单切回旧本地库，否则会丢订单、灵石、历史和任务状态。

短窗口回滚流程：

1. 再次开启维护模式。
2. 停止云 `tg-bot/web-api/payment-api` 写入。
3. 从云 Managed PostgreSQL dump 最新数据。
4. 恢复回本地主库。
5. 本地执行 Alembic 校验。
6. 本地入口恢复。
7. Cloudflare origin 切回本地/VPS 链路。

因此正式切换后的前 2 小时不要做额外数据库结构变更，方便必要时回滚。

### 7.3 R2 回滚

R2 不需要回滚。即使控制面回滚，本地服务仍可继续读取 R2 结果；R2 只作为公开媒体分发和备份层，不应破坏业务状态。

## 8. 安全与权限

必须执行：

- 云控制面 SSH key 使用 `allbot-do-sgp1-control-20260606`，密钥路径、指纹和轮换策略见 `docs/子模块_云控制面SSH密钥管理_cloud_ssh_access.md`。
- Cloudflare Access 保护 Dashboard、pgAdmin、filebrowser、Portainer。
- Central API 不公网暴露，只允许云本机和 Tailscale agent。
- Postgres/Valkey 只允许云 App 节点访问。
- 本地 MinIO 不再作为公网公开入口。
- 所有 `.env.cloud.*` 不提交 git。
- 生产 bot token、payment secret、JWT secret、R2 key、DB password 统一轮换一次。
- Tailscale ACL 按角色隔离：
  - `tag:allbot-cloud-control`
  - `tag:allbot-gpu-agent`
  - `tag:allbot-admin`
- 每次切换前确认只有一个生产 `tg-bot` 在线。

## 9. 监控与告警

云侧新增：

- App 节点 CPU、内存、磁盘、负载。
- `web-api` `/api/health`。
- Central API `/health`。
- Dashboard backend `/api/health`。
- Postgres 连接数、CPU、IO、慢查询。
- Valkey 内存、keyspace、evictions。
- Cloudflare 5xx、origin response time。
- R2 Class A/B 请求量和错误率。

本地保留：

- GPU 使用率、显存、温度。
- ComfyUI `/system_stats`。
- worker heartbeat 和 `healthy_workers`。
- GPU 节点磁盘，尤其 `192.168.1.177` 剩余空间。
- MinIO 磁盘、内存、桶增长。
- 武汉主服务器网络出站。

业务告警：

- pending queue 超过阈值。
- running set 长时间不下降。
- `pending_web_finalizers` 堆积。
- 支付回调失败。
- R2 warmup 失败。
- 视频结果长时间 `pending_result`。
- worker 进入 `error` 或 `quarantined`。

## 10. 预计时间线

| 阶段 | 预计耗时 | 是否影响生产 |
| :--- | :--- | :--- |
| 采购和云基础设施 | 0.5 天 | 否 |
| 云测试栈部署 | 0.5-1 天 | 否 |
| R2 测试和最近媒体 warmup | 0.5-1 天 | 否 |
| 生产 dry-run 迁移 | 0.5 天 | 否 |
| 正式切换窗口 | 30-90 分钟 | 是 |
| 切后观察 | 24 小时 | 否，但需值守 |
| 稳定化和脚本固化 | 3-7 天 | 否 |

## 11. 不建议现在做的事

- 不建议把 7 张本地 GPU 全量替换为云 GPU。
- 不建议继续让武汉家庭宽带承担主要公网 API 和媒体入口。
- 不建议热迁 Redis Central 队列。
- 不建议在没有队列 drain 的情况下切 Central API。
- 不建议让本地和云端两个 `tg-bot` 同时连生产 token。
- 不建议把 MinIO 直接搬到云上继续做公开主存储；公开媒体应优先 R2。
- 不建议切换当天同时做大版本功能发布或数据库结构大改。

## 12. 最小验收清单

正式切换前必须全部通过：

- 测试栈云端完整跑通一个图片任务和一个视频任务。
- R2 结果 URL 正常，视频等待 R2 的逻辑正常。
- Dashboard 能看到 worker heartbeat、队列、任务状态。
- 支付测试回调幂等通过。
- `pg_dump` / `pg_restore` dry-run 成功。
- Alembic 只有一个 head，云端 `upgrade head` 成功。
- 本地 7 个生产 agent 能通过 Tailscale 访问云 Central。
- Cloudflare origin 回源云 App 节点正常。
- 维护模式和回滚脚本准备好。

正式切换后必须立即验证：

- `tg-bot` 只有云端一个生产实例。
- `/api/health` 正常。
- Central `/health` 正常。
- 7 个生产 worker heartbeat 正常。
- Web 登录正常。
- Bot 命令正常。
- Web 提交一个低成本任务正常完成。
- 结果落库、R2 warmup、历史页、画廊详情正常。
- 支付回调能写入云数据库且不重复履约。
