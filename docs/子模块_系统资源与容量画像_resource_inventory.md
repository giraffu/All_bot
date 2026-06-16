# 子模块: 系统资源与容量画像 (Resource Inventory)

## 1. 目标与范围
本文档记录 AllBot 当前主服务器、本地 GPU 节点、网络出口、数据存储与运行负载的资源事实，用于容量规划、云化评估、灾备设计与运维排障。

本文档不是实时监控面板。除明确标注为固定事实的硬件配置外，数据库行数、队列积压、桶容量、活跃用户等都应视为快照数据；做迁移、采购或扩容决策前，必须重新采集。

最近一次结构性更新时间：2026-06-16，Asia/Shanghai。表内容量数字若未单独标注，仍是历史快照，扩容或迁移决策前必须重新采集。
最近一次局域网 GPU ComfyUI 素材清理：2026-06-08，Asia/Shanghai。
最近一次云正式负载巡检：2026-06-16 18:03，Asia/Shanghai。
最近一次云测试控制面核对：2026-06-09，Asia/Shanghai。

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
| `/` | 3.6T | 1.3T | 2.2T | 主系统盘与 Docker 数据共盘 |
| `/mnt/remote_data/192.168.1.226/ubantu` | 1.8T | 573G | 1.2T | 远端 GPU 节点 SSHFS，2026-06-08 清理后 |
| `/mnt/remote_data/192.168.1.177/data` | 915G | 508G | 361G | 远端 GPU 节点 SSHFS，2026-06-08 清理后 |
| `/mnt/remote_data/192.168.1.177/ubantui` | 915G | 508G | 361G | 同一远端根分区的用户目录挂载，2026-06-08 清理后 |
| `/mnt/remote_data/192.168.1.252/user` | 937G | 178G | 712G | 远端 GPU 节点 SSHFS，2026-06-08 清理后 |
| `/mnt/remote_data/192.168.1.2/data` | 936G | 171G | 726G | 远端 GPU 节点 SSHFS，2026-06-08 清理后 |
| `/mnt/remote_data/192.168.1.2/chuzeyu` | 936G | 171G | 726G | 同一远端根分区的用户目录挂载，2026-06-08 清理后 |

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
| 规格 | Basic Regular `$96/mo`，8 vCPU / 16GB RAM / 320GB SSD / 6TB transfer |
| 实测 CPU | 8 vCPU |
| 实测内存 | 约 15GiB |
| 实测系统盘 | 约 309G 总量；当前约 91G 已用、219G 可用 |
| SSH 日常入口 | `ssh allbot-do-sgp1-control`，默认 `deploy` 用户 |
| SSH root 入口 | `ssh allbot-do-sgp1-control-root`，仅初始化/救援使用 |

使用边界：
- `$96/mo` Droplet 当前作为正式生产控制面；生产 Postgres、Valkey 与对象存储不在该 Droplet 上长期自托管。
- 2026-06-16 原地扩容后，系统盘事实容量已从约 160GB 扩到约 320GB；后续缩容不能再按“保留 160GB 磁盘”的旧口径假设。
- 公开媒体与新生成对象走 Cloudflare R2 `user-data-prod`；本地 MinIO 保留为 legacy 迁移补齐、人工回滚、旧外链排障与本地热数据保留，不再是正式 Web/Dashboard 运行时 fallback。
- 本地 7 张 GPU 和 ComfyUI 不迁移；`cloud-prod-comfy-agent-*` 通过 Tailscale 访问云 Central API。
- 后续如继续增长，优先单独评估 Dashboard/后台任务拆分、PostgreSQL 规格或连接池预算；不要同时放大 Web worker 数和 DB 连接池。

### 2.2 云测试控制面 Droplet
云测试控制面 Droplet 于 2026-06-09 创建，用于替代旧本地常驻测试入口，降低正式与测试环境交叉风险。

| 项目 | 当前事实 |
| :--- | :--- |
| 云厂商 | DigitalOcean |
| 区域 | Singapore `SGP1` |
| Droplet 名称 | `allbot-do-sgp1-test-control` |
| 公网 IPv4 | `168.144.128.133` |
| VPC/私网 IPv4 | `10.104.0.5` |
| Tailscale IPv4 | `100.82.124.91` |
| 操作系统 | Ubuntu 24.04 LTS x64 |
| 规格 | Basic Regular `$12/mo`，1 vCPU / 2GB RAM / 50GB SSD / 2TB transfer |
| SSH 日常入口 | `ssh allbot-do-sgp1-test-control`，默认 `deploy` 用户 |
| 运行服务 | `cloud-postgres-test`、`cloud-redis-test`、`cloud-central-api-test`、`cloud-web-api-test`、`cloud-dashboard-backend-test`、`cloud-dashboard-frontend-test`、`cloud-imgproxy-test`、`cloud-tg-bot-test` |
| 公网保护 | 服务端口绑定 `100.82.124.91`；`allbot-cloud-test-firewall.service` drop 公网 eth0 的 `8001/8004/8044/8084/8087` |

使用边界：
- 测试 PostgreSQL 与 Redis 均为同机容器，只服务云测试栈，不连接正式托管 PostgreSQL/Valkey。
- 测试对象存储事实源为 R2 `user-data-test`，公网读取域名 `https://r2-test.aivison.it.com`。
- 本地主服务器运行 `cloud-comfy-agent-test-1..7`，通过 `CLOUD_TEST_CONTROL_HOST=100.82.124.91` 访问云测试 Central `8004`。
- 公网测试 Web 入口是 `web-test.aivison.it.com`，由 Web/Nginx VPS 静态站 `/root/dist-test` 反代到云测试 Web API `100.82.124.91:8001`。

### 2.3 云正式负载巡检快照

2026-06-08 17:10 Asia/Shanghai 的只读巡检显示，云控制面 CPU、内存和磁盘未打满，Web 卡顿更主要来自公网/边缘链路、结果媒体依赖和 GPU 队列等待。

| 指标 | 快照 | 判断 |
| :--- | :--- | :--- |
| 云 Droplet load average | 约 `1.90 / 2.08 / 2.18` | 4 vCPU 未打满 |
| 云 Droplet 内存 | 7.8GiB，总 available 约 3.2GiB | 未内存耗尽 |
| 云 Droplet 磁盘 | 154G 总量，约 58G 已用，97G 可用 | 使用率约 38% |
| `cloud-web-api-prod` | CPU 约 24%，内存约 2.0GiB | 有负载但不是满载 |
| `cloud-tg-bot-prod` | CPU 约 40%，内存约 1.15GiB | Bot 有明显活跃负载 |
| `cloud-central-api-prod` | CPU 约 8%，内存约 101MiB | Central 非 CPU 瓶颈 |
| 托管 PostgreSQL | 连接约 75ms；2 active、24 idle、1 idle in transaction、0 waiting locks | 暂未见连接池/锁打满 |
| 托管 Valkey/Redis | used_memory 约 40MB，connected_clients 81，blocked_clients 0 | 暂未见 Redis 打满 |

2026-06-16 18:03 Asia/Shanghai 扩容后复核显示：

| 指标 | 快照 | 判断 |
| :--- | :--- | :--- |
| 云 Droplet CPU/内存 | `nproc=8`，内存约 15GiB，available 约 13GiB | 控制面 CPU/RAM 已升至 8C16G 档 |
| 云 Droplet 磁盘 | 309G 总量，约 91G 已用，219G 可用 | 本次扩容实际包含磁盘扩展 |
| 云控制面容器 | Central/Web/Payment/Dashboard/imgproxy 均 `Up`；Bot polling 单实例保持运行 | 控制面服务恢复正常 |
| 托管 PostgreSQL 连接池预算 | 可用连接按 `100 - 3 reserved = 97` 估算；本轮配置目标峰值约 `73` | 保留约 24 条给迁移、排障、后台任务和抖动 |
| 托管 Valkey/Redis | 近期观测 used_memory 约 73MB/2GB、connected_clients 约 53、blocked/rejected/evicted 均为 0 | 本轮不提升 Valkey 配置 |

本轮云正式 DB 连接池预算：

| 服务 | 进程/worker 口径 | 池配置 | 峰值预算 |
| :--- | :--- | :--- | ---: |
| `cloud-web-api-prod` | `uvicorn --workers 4` | `DB_POOL_SIZE=6`、`DB_MAX_OVERFLOW=6` | 48 |
| `cloud-dashboard-backend-prod` | `gunicorn -w 1` | `DB_POOL_SIZE=6`、`DB_MAX_OVERFLOW=4` | 10 |
| `cloud-payment-api-prod` | 单进程 | `DB_POOL_SIZE=4`、`DB_MAX_OVERFLOW=3` | 7 |
| `cloud-tg-bot-prod` | 单进程 | `DB_POOL_SIZE=4`、`DB_MAX_OVERFLOW=4` | 8 |
| 合计 | - | - | 73 |

延迟拆分基线：
- 云机内部访问 `100.107.220.127:8000/8003/8043` 通常为 5-40ms。
- Web 边缘 VPS 到云 Web API 约 0.51-0.55s；该基线主要用于 `assets`/回滚/`web-test` 排障，不代表当前正式 Pages 主路径。
- 本地主服务器经公网访问 `api.aivison.it.com` API 约 0.3-0.7s；旧 `web.aivison.it.com/api` 不再作为 API 健康检查入口。
- 本地主服务器到云 Central Tailscale 约 0.7-2.1s。

队列与媒体压力：
- Central 当时约 pending 23-24、running 12，最老 pending 约 2873 秒；`healthy_workers=7`、`error_workers=0`、`quarantined_workers=0`。
- 队列主要集中在 `image_to_video`（含 legacy `video_insert` / `video_edit` alias）、`wan22_video_v2`、`face_swap`、`i2i_pro` 等长耗时或高峰任务。
- Web API 30 分钟内曾观测到约 172 次 R2 result URL 解析超时；边缘 30 分钟内约 202 次 499，`assets.aivison.it.com` legacy 回源约 37 次 upstream 异常。

## 3. 服务与容器分布
正式控制面当前在云端，本地主服务器保留本地 GPU worker 与旧数据。测试/开发服务仍可能在本地或云测试控制面运行，必须按 compose、端口、环境变量、数据库与 Valkey/Redis DB 隔离。

当前正式生产常驻类型：
- 云端正式入口：`cloud-tg-bot-prod`、`cloud-web-api-prod`、`cloud-payment-api-prod`
- 云端正式执行面：`cloud-central-api-prod`，Tailscale `100.107.220.127:8003`
- 云端正式管理面：`cloud-dashboard-backend-prod`、`cloud-dashboard-frontend-prod`、`cloud-imgproxy-prod`
- 本地正式 worker agent：`cloud-prod-comfy-agent-1` 至 `cloud-prod-comfy-agent-7`
- 本地 legacy 数据：原 PostgreSQL/Redis/MinIO 只作为保留或 fallback，不应继续作为正式写入事实源

测试/辅助服务类型：
- 云测试入口：`cloud-tg-bot-test`、`cloud-web-api-test`、`cloud-dashboard-backend-test`、`cloud-dashboard-frontend-test`、`cloud-imgproxy-test`
- 云测试执行面：`cloud-central-api-test`，Tailscale `100.82.124.91:8004`
- 云测试数据面：`cloud-postgres-test`、`cloud-redis-test`，仅 Docker 内网可达
- 本地云测试 worker：`cloud-comfy-agent-test-1` 至 `cloud-comfy-agent-test-7`
- 本地旧测试栈：不再作为受支持测试或回滚环境；仅作为历史取证材料，默认应停止并保留数据
- 本地运维与历史数据：`postgres-server`、`redis-server`、`minio-server`、`pgadmin-server`、`filebrowser`、`portainer_agent`

重要运行约束：
- `web-api`、Dashboard、Payment API 等 COPY 型服务改代码后必须重建镜像，不能只 `restart`。
- 云正式生产发布优先走 `scripts/safe_deploy_cloud_prod.sh` 或 cloud-prod compose 单服务重建；只有云正式整体故障、本地主服务器临时接管正式服务时才使用 `safe_deploy.sh`。
- 生产单服务重建时不得使用 `--remove-orphans` 或无 service 名的批量 compose 操作。
- 本地云正式 worker 使用旧版 `docker-compose` 时，遇到 `ContainerConfig` 兼容错误只能清理目标 worker 容器和同 service label 残留。

## 4. 本地 GPU 算力池
本地算力池由 4 台 GPU 服务器组成，共 7 张 GPU。项目容量口径以 GPU 监控截图与用户确认的硬件事实为准：3 张 RTX 5090 32G，4 张 RTX 4090 48G，总名义显存约 288GB。详细容器、模型挂载和安全运维边界见 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`。

> 注意：部分 ComfyUI 进程通过设备隔离启动，`/system_stats` 中会统一显示为 `cuda:0`。判断真实 GPU 数量时，不要把 Comfy 端口数、`cuda:0` 文本和物理 GPU 数混为一谈。

| GPU 服务器 | 物理 GPU | ComfyUI 端口 | 生产 Agent | 主要支持任务 |
| :--- | :--- | :--- | :--- | :--- |
| `192.168.1.226` | 1 x RTX 5090 32G | `8188` | `cloud_prod_worker_01` | `face_swap`、`i2i_pro`、`i2i_draw`、`face_video`、`video_edit`、`image_to_video`、`t2i-pornmaster-turbo` |
| `192.168.1.177` | 2 x RTX 5090 32G | `8188`、`8189` | `cloud_prod_worker_02`、`cloud_prod_worker_03` | `video_insert`、`video_edit`、`image_to_video`、`ltx_video` |
| `192.168.1.252` | 2 x RTX 4090 48G | `8188`、`8189` | `cloud_prod_worker_04`、`cloud_prod_worker_05` | `img2img`、`img2img_lora`、`wan22_video_v2`、`video_edit`、`image_to_video` |
| `192.168.1.2` | 2 x RTX 4090 48G | `8188`、`8189` | `cloud_prod_worker_06`、`cloud_prod_worker_07` | `img2img`、`img2img_lora`、`video_insert`、`video_edit`、`image_to_video` |

表中 `video_insert` / `video_edit` 仅表示生产 worker 仍声明的兼容 alias；canonical 执行面类型是 `image_to_video`，不再代表独立模型或独立 workflow。

同一批 ComfyUI 节点也可能被测试 agent 使用。正式 agent 连接云 Central API `100.107.220.127:8003`；测试 agent 连接测试 Central。测试与生产共享物理 GPU 时，要避免把测试任务当成免费容量；大模型/视频任务压测会直接影响生产排队。

本地主服务器已配置局域网 GPU 节点 SSH 别名：`allbot-gpu-226`、`allbot-gpu-177`、`allbot-gpu-252`、`allbot-gpu-002`。密钥、权限边界与验证命令见 `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md`。

GPU 节点运行方式与模型挂载快照：

| GPU 服务器 | ComfyUI 运行方式 | 模型目录 | 实例隔离 | 运维注意 |
| :--- | :--- | :--- | :--- | :--- |
| `192.168.1.226` | 宿主机进程，cwd `/home/ubantu/comfyui`，端口 `8188` | `/home/ubantu/comfyui/models`，约 325G | 单实例 | 不是 Comfy Docker 容器；重启前先确认进程管理方式 |
| `192.168.1.177` | Docker `comfy0`/`comfy1`，分别绑定 GPU 0/1，端口 `8188`/`8189` | `/data/comfy/models`，约 444G，共享 | `inst0`/`inst1` 的 input/output/temp/custom_nodes/workflows 分离 | 2026-06-08 清理后根分区可用约 361G；`8189` 已修复 `FL_RIFE` |
| `192.168.1.252` | Docker `comfy0`/`comfy1`，分别绑定 GPU 0/1，端口 `8188`/`8189` | `/home/user/APP/data/models`，约 121G，共享 | `inst0`/`inst1` 的 input/output/temp/custom_nodes/workflows 分离 | `comfy0` 主打 img2img，`comfy1` 主打视频/Wan22 |
| `192.168.1.2` | Docker `comfy0`/`comfy1`，分别绑定 GPU 0/1，端口 `8188`/`8189` | `/data/comfy/models`，约 85G，共享 | `inst0`/`inst1` 的 input/output/temp/custom_nodes/workflows 分离 | 可只重启目标 Comfy 容器，不要整机重启 |

双卡节点的重要边界：`comfy0` 与 `comfy1` 是独立容器、独立 GPU、独立输入输出目录，但共享模型目录和宿主机资源。处理某个 worker 或某个 ComfyUI 的问题时，只操作对应 worker 容器或对应 GPU 节点上的 `comfy0`/`comfy1`；不要使用整机 reboot、无 service 名 `docker compose down/up` 或批量 `docker rm`。

ComfyUI 素材清理口径：
- 2026-06-08 检查确认 GPU 节点没有项目级 ComfyUI 素材自动清理机制，只有系统默认 tmp/log 清理。
- 已执行一次安全清理：`output/temp` 删除 60 分钟以前文件，`input` 只删除 24 小时以前文件。
- 长期清理脚本为 `scripts/cleanup_lan_comfy_artifacts.sh`，默认 dry-run，必须显式 `--execute` 才删除。
- 不要把“只保留最近 1 小时”套到 `input` 目录；已进入 ComfyUI 队列的任务可能仍引用输入文件。

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
- 正式 Web 静态站由 Cloudflare Pages 承接；正式 Web API 与 RMB 支付入口由 Cloudflare Tunnel 回源云控制面。
- R2 `user-data-prod` 是正式新对象写入与公开媒体分发事实源。
- MinIO 不再承接正式新写入公开事实源；`assets.aivison.it.com` 仅作为 legacy 旧外链、人工回滚和迁移排障入口，正式应用不再生成该域名 URL。
- Web/API 的海外访问路径详见 [网络暴露与代理穿透](./子模块_网络暴露与代理穿透_network_proxy.md) 与 [边缘节点运维指南](./子模块_边缘节点运维指南_edge_node_ops.md)。

### 边缘 VPS

当前海外边缘层至少包含两台 VPS。详细运维 SOP 见 `docs/子模块_边缘节点运维指南_edge_node_ops.md`。

| 节点 | 入口 | 资源快照 | 当前职责 | 风险 |
| :--- | :--- | :--- | :--- | :--- |
| Web/Nginx 边缘 VPS `web` | Tailscale `100.88.57.122`，公网 `154.17.30.113`，SSH `root@100.88.57.122` 使用 `frontend/ssh_key/id_rsa.pem` | Ubuntu 24.04，2 vCPU，1.9GiB RAM，40G 根盘；2026-06-16 受控轮转日志后已用约 32G，可用约 6.3G | `web-test.aivison.it.com` 测试静态站与 `/api/` 反代，`assets.aivison.it.com` legacy MinIO 代理，`/root/dist` 正式 Web 回滚副本 | 根盘从 97% 降至约 84%，`/var/cache/nginx` 仍约 26G；`logrotate.timer` 已启用且 Nginx 日志已当天压缩；不再承接正式 `web.aivison.it.com` 主流量 |
| Telegram Local API VPS | 公网 `69.63.220.115` | 本轮 SSH key 未打通，CPU/内存/磁盘待补采；公网 22/8081/8082 可达 | Telegram Local Bot API `8081` 与文件服务 `8082`，支撑大文件下载/上传 | 当前主服务器未纳入 SSH 免密管理，资源与容器状态不可远程只读确认 |

边缘容量判断：
- Web 边缘根盘低于 10% 可用时，不建议发布新静态资源、扩大 Nginx cache 或新增大日志调试。
- `assets.aivison.it.com` 根路径返回 403 不代表具体旧外链/人工回滚对象不可读；验收该链路必须测试真实 object URL。正式 Web/Dashboard 响应不应再返回该域名。
- Telegram Local API 节点如果 SSH 不可用，发生 8081/8082 故障时只能做公网端口判断，无法快速查看容器日志和挂载目录，应优先补齐 SSH key 管理。

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

MinIO 是主服务器历史数据与内存占用大户之一。规划清理时应先确认 R2 命中率、可见热集补齐状态和 legacy 旧外链/人工回滚访问量，再逐步缩短本地热数据生命周期。

## 7. 当前容量判断
当前系统瓶颈顺序大致为：
1. GPU 任务吞吐与视频任务长尾耗时。
2. 公网/Cloudflare/Web 边缘到云控制面的链路延迟，以及前端多接口串行等待。
3. R2 result URL 探测、R2 公开域名/短签耗时，以及 legacy `assets.aivison.it.com` 旧外链/人工回滚链路的边缘缓存/磁盘压力。
4. 云控制面到本地 GPU/ComfyUI 的 Tailscale/内网链路稳定性，以及本地 GPU 节点短暂停顿。
5. Dashboard stats/外部接口熔断与托管 Valkey/PostgreSQL 连接池压力。
6. ComfyUI 本地 `input/output/temp` 会继续随视频任务快速增长，若缺少定期巡检，远端 GPU 节点仍可能再次磁盘吃紧。

当前 CPU、Redis、Postgres 数据体积都不是第一瓶颈。若做云化，优先迁移控制面、公开对象分发与数据库备份，不应优先把本地 7 张 GPU 全量替换为云 GPU。

推荐容量策略：
- 控制面云化：Bot/Web/Payment/Central/Dashboard 已迁到云 VM，后续重点是规格升级、拆分 Dashboard 或引入第二控制面节点。
- 数据面分层：Postgres/Valkey 已采用云侧口径；R2 承接公开媒体分发和新对象写入。
- 本地 GPU 保留：4 台 GPU 服务器继续作为主算力池，worker 通过 Tailscale 连接云 Central API。
- 云 GPU 弹性：只在队列积压或单类任务爆发时临时拉起，不建议 24/7 常驻替代本地 GPU。
- MinIO 生命周期：生产热结果保留有限天数，长期公开访问走 R2，定期清理测试桶和临时桶。
- Web 体验优化：优先减少首屏/结果页串行 API 等待，R2 result 探测失败时快速返回 `pending_result` 或缓存快照，降低用户端 499。

## 8. 重新采集 Checklist
做采购、迁移或扩容决策前，至少重新采集：
- `hostnamectl`、`lscpu`、`free -h`、`df -hT`
- `docker ps`、`docker stats --no-stream`
- 云内、Web 边缘到云、公网域名三段 API 延迟
- Postgres 数据库大小、表大小、近 1/7/30 天活跃与历史量
- Redis `INFO memory`、`INFO keyspace`、Central pending/running/heartbeat
- Central pending 最老等待时间、`queue_by_type`、`healthy/error/quarantined` worker 数
- MinIO 桶大小与最近 7 天出入站量
- 所有 ComfyUI `/system_stats` 与 Dashboard GPU 监控
- Cloudflare/R2 命中率、R2 result timeout、MinIO 回源量、边缘 VPS 499/502/504 错误率
- 各 GPU 节点磁盘剩余空间，尤其是 `192.168.1.177`
- GPU 节点上 `comfy0`/`comfy1` 的 GPU 绑定、模型目录和 `inst0`/`inst1` 挂载是否仍与 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md` 一致

采集结果必须标注具体日期和时区，避免把实时队列或短期活动峰值写成长期容量。
