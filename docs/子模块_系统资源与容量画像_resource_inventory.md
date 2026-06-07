# 子模块: 系统资源与容量画像 (Resource Inventory)

## 1. 目标与范围
本文档记录 AllBot 当前主服务器、本地 GPU 节点、网络出口、数据存储与运行负载的资源事实，用于容量规划、云化评估、灾备设计与运维排障。

本文档不是实时监控面板。除明确标注为固定事实的硬件配置外，数据库行数、队列积压、桶容量、活跃用户等都应视为快照数据；做迁移、采购或扩容决策前，必须重新采集。

最近一次结构性更新时间：2026-06-07 晚间，Asia/Shanghai。表内容量数字若未单独标注，仍是历史快照，扩容或迁移决策前必须重新采集。

## 2. 主服务器
当前主服务器不再是正式公开控制面的主承载点。正式 Bot/Web/Payment/Central/Dashboard 已迁到云控制面；本机主要保留本地 GPU worker、ComfyUI 访问、legacy MinIO 数据、本地旧正式数据保留、测试/开发辅助容器和运维工具。

| 项目 | 当前事实 |
| :--- | :--- |
| 主机名 | `hfy-FAEX9` |
| 内网地址 | `192.168.1.115` |
| 操作系统 | Ubuntu 24.04.4 LTS |
| 内核 | Linux 6.17.0-1020-oem |
| 硬件型号 | FEVM FAEX9 |
| CPU | AMD RYZEN AI MAX+ 395 w/ Radeon 8060S |
| CPU 规格 | 16 核 / 32 线程，最高约 5.19GHz |
| 内存 | 62GiB |
| 系统盘 | 3.6T NVMe，ext4 |
| Docker/Compose | Docker 29.1.3，`docker-compose` 1.29.2 |
| 主网卡 | `eno1`，1GbE，内网 `192.168.1.115/24` |
| 远程组网 | `tailscale0` 已存在，用于跨节点/边缘访问 |

最新磁盘快照：

| 挂载点 | 容量 | 已用 | 可用 | 备注 |
| :--- | ---: | ---: | ---: | :--- |
| `/` | 3.6T | 1.4T | 2.1T | 主系统盘与 Docker 数据共盘 |
| `/mnt/remote_data/192.168.1.226/ubantu` | 1.8T | 1.1T | 668G | 远端 GPU 节点 SSHFS |
| `/mnt/remote_data/192.168.1.177/data` | 915G | 823G | 46G | 远端 GPU 节点 SSHFS，容量紧张 |
| `/mnt/remote_data/192.168.1.252/user` | 937G | 519G | 371G | 远端 GPU 节点 SSHFS |
| `/mnt/remote_data/192.168.1.2/data` | 936G | 379G | 518G | 远端 GPU 节点 SSHFS |

## 2.1 云控制面 Droplet
云控制面 Droplet 已于 2026-06-06 创建，并于 2026-06-07 晚间承接正式生产控制面。

| 项目 | 当前事实 |
| :--- | :--- |
| 云厂商 | DigitalOcean |
| 区域 | Singapore `SGP1` |
| Droplet 名称 | `allbot-do-sgp1-control-01` |
| 公网 IPv4 | `159.223.39.217` |
| VPC/私网 IPv4 | `10.104.0.2` |
| 操作系统 | Ubuntu 24.04.3 LTS |
| 规格 | Basic Regular `$48/mo`，4 vCPU / 8GB RAM / 160GB SSD / 5TB transfer |
| 实测 CPU | 4 vCPU |
| 实测内存 | 约 7.8GiB |
| 实测系统盘 | 约 154G，总量；创建后约 152G 可用 |
| SSH 日常入口 | `ssh allbot-do-sgp1-control`，默认 `deploy` 用户 |
| SSH root 入口 | `ssh allbot-do-sgp1-control-root`，仅初始化/救援使用 |

使用边界：
- `$48/mo` Droplet 当前作为正式过渡控制面；生产 Postgres、Valkey 与对象存储不在该 Droplet 上长期自托管。
- 公开媒体与新生成对象走 Cloudflare R2 `user-data-prod`；本地 MinIO 保留为 legacy 历史媒体只读 fallback 与本地热数据保留。
- 本地 7 张 GPU 和 ComfyUI 不迁移；`cloud-prod-comfy-agent-*` 通过 Tailscale 访问云 Central API。
- 长期稳妥生产规格仍建议升级到 8 vCPU / 16GB RAM 档，或把 Dashboard/后台任务拆到第二台节点。

## 3. 服务与容器分布
正式控制面当前在云端，本地主服务器保留本地 GPU worker 与旧数据。测试/开发服务仍可能在本地或云测试控制面运行，必须按 compose、端口、环境变量、数据库与 Valkey/Redis DB 隔离。

当前正式生产常驻类型：
- 云端正式入口：`cloud-tg-bot-prod`、`cloud-web-api-prod`、`cloud-payment-api-prod`
- 云端正式执行面：`cloud-central-api-prod`，Tailscale `100.107.220.127:8003`
- 云端正式管理面：`cloud-dashboard-backend-prod`、`cloud-imgproxy-prod`
- 本地正式 worker agent：`cloud-prod-comfy-agent-1` 至 `cloud-prod-comfy-agent-7`
- 本地 legacy 数据：原 PostgreSQL/Redis/MinIO 只作为保留或 fallback，不应继续作为正式写入事实源

测试/辅助服务类型：
- 测试入口：`tg-bot-test`、`web-api-test`、`payment-api-test`
- 测试执行面：`central-api-test`，宿主机 `8004 -> 8003`
- 测试 worker agent：`comfy-agent-test-1` 至 `comfy-agent-test-7`
- 管理与数据：`postgres-server`、`redis-server`、`minio-server`、`pgadmin-server`、`filebrowser`、`portainer_agent`
- 媒体与监控：`imgproxy`、`monitor_node_exporter`
- Dashboard：生产与测试各自运行 frontend/backend 容器

重要运行约束：
- `web-api`、Dashboard、Payment API 等 COPY 型服务改代码后必须重建镜像，不能只 `restart`。
- 云正式生产发布优先走 `scripts/safe_deploy_cloud_prod.sh` 或 cloud-prod compose 单服务重建；旧本地正式栈才使用 `safe_deploy.sh`。
- 生产单服务重建时不得使用 `--remove-orphans` 或无 service 名的批量 compose 操作。
- 本地云正式 worker 使用旧版 `docker-compose` 时，遇到 `ContainerConfig` 兼容错误只能清理目标 worker 容器和同 service label 残留。

## 4. 本地 GPU 算力池
本地算力池由 4 台 GPU 服务器组成，共 7 张 GPU。项目容量口径以 GPU 监控截图与用户确认的硬件事实为准：3 张 RTX 5090 32G，4 张 RTX 4090 48G，总名义显存约 288GB。

> 注意：部分 ComfyUI 进程通过设备隔离启动，`/system_stats` 中会统一显示为 `cuda:0`。判断真实 GPU 数量时，不要把 Comfy 端口数、`cuda:0` 文本和物理 GPU 数混为一谈。

| GPU 服务器 | 物理 GPU | ComfyUI 端口 | 生产 Agent | 主要支持任务 |
| :--- | :--- | :--- | :--- | :--- |
| `192.168.1.226` | 1 x RTX 5090 32G | `8188` | `cloud_prod_worker_01` | `face_swap`、`i2i_pro`、`i2i_draw`、`face_video`、`video_edit`、`image_to_video`、`t2i-pornmaster-turbo` |
| `192.168.1.177` | 2 x RTX 5090 32G | `8188`、`8189` | `cloud_prod_worker_02`、`cloud_prod_worker_03` | `video_insert`、`video_edit`、`image_to_video`、`ltx_video` |
| `192.168.1.252` | 2 x RTX 4090 48G | `8188`、`8189` | `cloud_prod_worker_04`、`cloud_prod_worker_05` | `img2img`、`img2img_lora`、`wan22_video_v2`、`video_edit`、`image_to_video` |
| `192.168.1.2` | 2 x RTX 4090 48G | `8188`、`8189` | `cloud_prod_worker_06`、`cloud_prod_worker_07` | `img2img`、`img2img_lora`、`video_insert`、`video_edit`、`image_to_video` |

同一批 ComfyUI 节点也可能被测试 agent 使用。正式 agent 连接云 Central API `100.107.220.127:8003`；测试 agent 连接测试 Central。测试与生产共享物理 GPU 时，要避免把测试任务当成免费容量；大模型/视频任务压测会直接影响生产排队。

ComfyUI 版本快照：

| ComfyUI URL | ComfyUI | PyTorch | 运行时识别显存 |
| :--- | :--- | :--- | :--- |
| `http://192.168.1.226:8188` | 0.17.0 | 2.10.0+cu130 | RTX 5090，约 31.36GiB |
| `http://192.168.1.177:8188` | 0.18.2 | 2.11.0+cu130 | RTX 5090，约 31.36GiB |
| `http://192.168.1.177:8189` | 0.18.2 | 2.11.0+cu130 | RTX 5090，约 31.36GiB |
| `http://192.168.1.252:8188` | 0.18.5 | 2.11.0+cu128 | RTX 4090，约 47.37GiB |
| `http://192.168.1.252:8189` | 0.22.0 | 2.11.0+cu128 | RTX 4090，约 47.37GiB |
| `http://192.168.1.2:8188` | 0.19.5 | 2.11.0+cu128 | RTX 4090，约 47.62GiB |
| `http://192.168.1.2:8189` | 0.22.0 | 2.11.0+cu128 | RTX 4090，约 47.62GiB |

## 5. 网络与外部依赖
现实网络条件：
- 主服务器位于中国武汉，电信家庭千兆内网环境。
- 主服务器主网卡为 1GbE；本地 GPU 节点通过 `192.168.1.0/24` 内网访问。
- ComfyUI 内网探测多数在几十毫秒内返回，但仍可能出现单节点端口瞬时慢响应。
- 公网入口依赖 Cloudflare、海外 VPS、Tailscale/Cloudflare Tunnel/FRP 等链路，不应把武汉家庭宽带作为唯一公网入口。
- Telegram API 访问通过代理/海外节点链路，HTTPS 可达但链路延迟明显高于普通内网 API。

当前云侧与边缘事实：
- 前端静态资源、部分公开分发能力与域名解析依赖 Cloudflare。
- R2 `user-data-prod` 是正式新对象写入与公开媒体分发事实源。
- MinIO 不再承接正式新写入公开事实源；`assets.aivison.it.com` 仅作为 legacy 历史媒体只读回源。
- Web/API 的海外访问路径详见 [网络暴露与代理穿透](./子模块_网络暴露与代理穿透_network_proxy.md) 与 [边缘节点运维指南](./子模块_边缘节点运维指南_edge_node_ops.md)。

## 6. 数据存储快照
### PostgreSQL
生产数据库 `bot_db` 当前约 2.6GB，测试库 `bot_db_test` 当前约 98MB。生产库主要体积来自历史与日志表。

| 表 | 近似行数 | 总体积 |
| :--- | ---: | ---: |
| `history` | 1,683,320 | 1580MB |
| `user_logs` | 2,419,762 | 465MB |
| `worker_logs` | 1,458,181 | 347MB |
| `users` | 123,508 | 78MB |
| `checkin_history` | 440,026 | 47MB |
| `user_interactions` | 168,287 | 41MB |
| `referrals` | 112,389 | 16MB |
| `gallery_posts` | 17,187 | 6.4MB |
| `orders` | 8,026 | 5.3MB |

用户与生成量快照：

| 指标 | 数量 |
| :--- | ---: |
| 注册用户 | 124,439 |
| 近 1 天活跃用户 | 7,594 |
| 近 7 天活跃用户 | 16,872 |
| 近 30 天活跃用户 | 40,689 |
| 历史记录总数 | 1,679,245 |
| 近 1 天历史记录 | 23,070 |
| 近 7 天历史记录 | 178,279 |
| 近 30 天历史记录 | 755,736 |

### Redis
正式运行态当前由云侧 Valkey/Redis 承载，用于 Bot/Web 运行态、Central API 队列、worker 心跳、并发锁、pending finalizer、限流等短生命周期数据。下表为迁移前/迁移期本地快照，不代表当前云正式实时值。

| 指标 | 当前值 |
| :--- | ---: |
| `used_memory_human` | 58.69MB |
| `db1` key 数 | 111,937 |
| `db2` key 数 | 24,609 |
| `db3` key 数 | 192 |
| `db4` key 数 | 1,103 |
| 生产 `active_tasks` | 142 |
| 生产 `pending_web_finalizers` | 45 |
| Central pending queue | 130 |
| Central running set | 10 |
| Central agent heartbeats | 9 |
| Central task hashes | 23,361 |

### MinIO
MinIO 本地数据目录：`/home/hfy/APP/minio-deploy/data`，迁移前快照总量约 453GB。当前正式新数据写入 R2；本地 MinIO 保留 legacy 历史媒体、旧输入和本地热数据，不应作为新生成结果公开事实源。

| 桶/目录 | 当前体积 | 备注 |
| :--- | ---: | :--- |
| `bot-data` | 268GB | 生产输入/用户数据热桶 |
| `comfyui-temp` | 182GB | 生产生成结果热桶 |
| `bot-template` | 2.5GB | 模板资源 |
| `comfyui-temp-test` | 717MB | 测试结果桶 |
| `bot-data-test` | 266MB | 测试输入桶 |
| `comfyui-input` | 17MB | 旧/兼容输入目录 |

MinIO 是主服务器历史数据与内存占用大户之一。规划清理时应先确认 R2 命中率和 legacy fallback 访问量，再逐步缩短本地热数据生命周期。

## 7. 当前容量判断
当前系统瓶颈顺序大致为：
1. GPU 任务吞吐与视频任务长尾耗时。
2. 云控制面到本地 GPU/ComfyUI 的 Tailscale/内网链路稳定性，以及本地 GPU 节点短暂停顿。
3. MinIO 热桶容量、内存占用与回源压力。
4. 云控制面规格较小导致的 Web/Dashboard/状态观测资源竞争，以及托管 Valkey/PostgreSQL 连接池压力。
5. `192.168.1.177` 远端挂载盘可用空间偏低。

当前 CPU、Redis、Postgres 数据体积都不是第一瓶颈。若做云化，优先迁移控制面、公开对象分发与数据库备份，不应优先把本地 7 张 GPU 全量替换为云 GPU。

推荐容量策略：
- 控制面云化：Bot/Web/Payment/Central/Dashboard 已迁到云 VM，后续重点是规格升级、拆分 Dashboard 或引入第二控制面节点。
- 数据面分层：Postgres/Valkey 已采用云侧口径；R2 承接公开媒体分发和新对象写入。
- 本地 GPU 保留：4 台 GPU 服务器继续作为主算力池，worker 通过 Tailscale 连接云 Central API。
- 云 GPU 弹性：只在队列积压或单类任务爆发时临时拉起，不建议 24/7 常驻替代本地 GPU。
- MinIO 生命周期：生产热结果保留有限天数，长期公开访问走 R2，定期清理测试桶和临时桶。

## 8. 重新采集 Checklist
做采购、迁移或扩容决策前，至少重新采集：
- `hostnamectl`、`lscpu`、`free -h`、`df -hT`
- `docker ps`、`docker stats --no-stream`
- Postgres 数据库大小、表大小、近 1/7/30 天活跃与历史量
- Redis `INFO memory`、`INFO keyspace`、Central pending/running/heartbeat
- MinIO 桶大小与最近 7 天出入站量
- 所有 ComfyUI `/system_stats` 与 Dashboard GPU 监控
- Cloudflare/R2 命中率、MinIO 回源量、边缘 VPS 502/504 错误率
- 各 GPU 节点磁盘剩余空间，尤其是 `192.168.1.177`

采集结果必须标注具体日期和时区，避免把实时队列或短期活动峰值写成长期容量。
