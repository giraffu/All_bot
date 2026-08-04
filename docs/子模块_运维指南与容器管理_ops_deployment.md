# 子模块: 运维指南与容器管理 (Ops & Deployment)

> 当前发布只使用 `deploy/module-catalog.json` 和
> `scripts/release.py build/deploy/rollback/status`。旧 plan/policy/bundle
> 说明只作历史背景，不再是可执行入口。

> 构建必须给出完整 SHA 和明确模块；部署必须给出环境、单个模块与精确
> digest。prod mutation 额外要求 `--confirm-prod`。数据库迁移、配置契约、
> Compose 契约、Pages 和 GPU 都是 catalog 中的显式目标，不存在自动 planner、
> track、组合 promotion 或 CI/test evidence 门禁。

## 1. 目标与范围

本模块记录当前仓库真实生效的发布、迁移与故障恢复边界。新发布只消费
digest-pinned artifact，不在目标机 build，也不从云端源码目录加载应用代码。
部署前读取目标 live identity，完成后检查目标结果；失败只恢复该模块 previous。
migration 失败保留现场，不自动 downgrade 或恢复数据库备份。

## 2. Legacy 部署路径（禁止用于新代码发布）

- 旧云测试同步、现场 build、单 service 手工重建只作首次切换前取证，不是可执行的新发布方案。
- 旧云正式热修、QQCC 窄同步与旧 cloud compose 只作 legacy 回滚材料，不是可执行的新发布方案。
- 本地正式灾备：仅在云正式整体不可用时按 `docs/子模块_本地正式灾备切换_local_prod_fallback.md` 切回本地主服务器
- 本地正式灾备整栈启动/重建：仅在云正式整体故障、需要本地主服务器临时接管时才执行 `bash safe_deploy.sh`
- 原因：脚本已经把以下步骤串成标准顺序：
  - 进入维护模式
  - 等待活跃任务清空
  - 清理僵尸任务与 Redis 锁
  - 检查 Alembic 多 head
  - 生产脚本基于 `.env` 并显式 `BOT_TYPE=PROD`，宿主机执行 `alembic upgrade head`
  - 重建 workers
  - 重建 central api
  - 重建主服务群
  - 重建 dashboard
  - 发布生产 Web 静态站到 Cloudflare Pages
- `safe_deploy.sh` 到此结束，不会顺带重建测试环境；它不代表当前云正式控制面的发布入口。
- 旧本地测试部署入口已删除；云测试只通过不可变 release 流程维护，不提供恢复旧本地隔离测试栈的人工回退入口。

## 2.1 当前默认发布策略

- AI 在功能研发期间默认只能更新隔离测试环境，不得主动执行生产部署。
- “帮我改功能”“帮我修 Bug”“帮我联调”“帮我验证配置”这类请求，默认理解为测试环境操作。
- 只有在用户明确表达“上线”“发布”“部署正式环境”“交付生产”后，才允许
  执行 `scripts/release.py deploy --env prod --module <name> --artifact
  <exact-digest> --confirm-prod`；`safe_deploy.sh` 只用于云正式整体故障时的
  本地正式灾备。
- 在用户完成测试验收前，不得把测试环境变更直接同步到正式 Bot、正式 Web、正式 Payment、正式 Central API 或正式 Dashboard。
- Dashboard、QQCC Config 和 private worker 没有 fast-track 或 direct 策略别名，
  只使用各自 catalog 模块和精确 digest。全局生成维护不是普通模块发布参数；
  若专项操作确实需要维护、排空或数据库备份，必须先走对应专用 SOP 和独立
  授权，不能假设 `release.py` 会隐式完成。

## 2.2 云端测试控制面

- DigitalOcean SGP1 Droplet 上的云测试只接受一个 catalog 模块的精确 digest：
  `scripts/release.py deploy --env test --module <name> --artifact
  <repository@sha256:digest>`。
- 云测试控制面默认部署同机 Postgres、同机 Redis、Central API、Web API、
  QQCC Config Backend/Frontend 与 imgproxy；Dashboard 不在测试站运行。
  `bot-test` 只通过 `bot` profile 手动启动，测试 Worker 仅在专项诊断显式启用。
  当前对象存储事实源是 Cloudflare R2，云测试 compose 不包含 MinIO、
  Payment API 或 Web 前端 dev 容器。
- 操作者按 catalog 精确选择模块；代码模块不会自动扩大到关联消费者，也不会
  隐式 drain Worker 或切换维护。跨模块契约变化必须显式安排每个目标和顺序。
- 测试 Web 使用 `public-web` 的环境中立 artifact，由 Pages adapter 注入测试
  runtime config 并验证 canonical 测试域名；不覆盖式同步 dist。
- 测试 Web/Bot 使用 `runtime/cloud-test/GENERATION_MAINTENANCE` 作为跨重建生成维护标记，容器内路径为 `/app/runtime-flags/GENERATION_MAINTENANCE`，由 `GENERATION_MAINTENANCE_FILE` 注入。该目录属于运行时状态，不提交仓库。
- 云测试 `.env.cloud.test` 已被 `.gitignore` 忽略，不能提交到仓库。
- 云端服务端口绑定到云测试 Tailscale IP `100.82.124.91`，不直接开放公网。
- 云测试全链路 worker 使用 `workers/docker-compose-cloud-worker-test.yml`，容器名为 `cloud-comfy-agent-test-*`，从本地主服务器经 `CLOUD_TEST_CONTROL_HOST=100.82.124.91` 访问云端 `8004` Central API，并直接访问 R2 S3 endpoint 读写 `user-data-test`。当前 compose 声明 `cloud-comfy-agent-test-1..8`；其中 `cloud_worker_test_03` 常驻复用 gpu177 的 `ltx_unified`，`cloud_worker_test_06` 常驻复用 gpu226 的 `all`，`cloud_worker_test_08` 是默认 disabled 的 SCAIL-2 测试 worker。共享正式 ComfyUI 的 test-3/test-6 关闭 prefetch/pipeline、单任务串行，但仍与正式任务共用 GPU 队列。
- 若历史本地测试栈仍在运行，切云测试前用 `scripts/stop_local_test_preserve.sh` 停止并保留数据；云测试 GPU 执行面使用 `scripts/start_cloud_worker_test.sh` 启动本地 cloud-worker 测试栈。
- 云测试 `bot-test` 默认通过 `TON_PAYMENT_POLLING_ENABLED=false` 禁用 TON 链上轮询，避免空云测试库回扫真实商户地址历史交易；仅在专门支付联调时显式开启 `CLOUD_TEST_TON_PAYMENT_POLLING_ENABLED=true`。
- 云测试库若为空，脚本使用当前 ORM schema 初始化并 `alembic stamp head`；若已有 schema，脚本执行 `alembic upgrade head`。这是云测试控制面的特殊兼容策略，不改变生产脚本的迁移口径。
- 云测试 `.env.cloud.test` 中 `MINIO_*` 是项目兼容变量名；R2 直连时应保持 `MINIO_SECURE=true`、`MINIO_BUCKET/MINIO_INPUT_BUCKET/MINIO_RESULT_BUCKET/MINIO_TEMPLATE_BUCKET=user-data-test`、`MINIO_PUBLIC_URL=`、`R2_PUBLIC_DOMAIN=https://r2-test.aivison.it.com`。Web owner 视频结果接口依赖 R2 公网 URL，公开域名缺失会导致视频停在 99% / `pending_result`。
- 云测试公网 Web 使用 Cloudflare Pages `web-cf-test.aivison.it.com`，API 经 `api-cf-test.aivison.it.com` 回源云端测试 Web API。
- 详细说明见 `/docs/子模块_云测试控制面部署_cloud_test_control_plane.md`。

## 2.3 云正式控制面

- 2026-06-07 晚间正式生产已切到云控制面；首次不可变发布切换前的旧
  compose 和脚本仍保留作归档/legacy rollback。新长期入口是模块目录、公共
  cloud/worker compose 和 `scripts/release.py`。
- `.env.cloud.prod` 是本机私有文件，已被 `.gitignore` 忽略；`.env.cloud.prod.example` 只提供变量契约和占位值。`.dockerignore` 必须忽略 `.env.*`，避免 root Docker build 把真实云正式变量 COPY 进镜像。
- 云正式 Web API 需要 `JWT_SECRET_KEY`，且不能使用默认占位值；该 key 已纳入 `.env.cloud.prod.example` 和 `scripts/safe_deploy_cloud_prod.sh` preflight 必填检查。
- 云测试环境退役入口为 `scripts/cleanup_cloud_test_for_prod.sh`。脚本默认 dry-run，真实清理必须传 `--execute`；它不得删除 R2 `user-data-test`，不得误改正式服务或 `web.aivison.it.com`。
- 云正式控制面包含 Central API、Web API、Payment API、Dashboard Backend、
  Dashboard Frontend、QQCC Config Backend/Frontend、imgproxy、正式 Bot 和
  可选 QQCC 懒人 Bot。所有目标都按 catalog 模块和精确 digest 独立部署；
  production mutation 每个模块都要求 `--confirm-prod`。migration 与部署契约
  也是独立模块，不存在 direct/standard/emergency 风险策略或自动晋级。
- 云正式执行池由本地 worker compose、LAN AIO 与 RunPod 构成。启动或重建后必须在云 Central `/system/workers` 验证当次目标 worker 集合的 heartbeat、control state 与任务类型，状态不能是 `error` 或 `quarantined`；不要把固定 worker 数量当成验收标准。
- 新建 RunPod 的模型同步默认使用最多 4 个文件级并行下载，可通过
  `RUNPOD_MODEL_DOWNLOAD_CONCURRENCY=1..8` 调整；旧 Pod 不因配置或镜像引用更新
  自动生效。验收应区分下载阶段聚合速率、逐文件重试和后续串行 SHA-256 阶段，
  不能把 bootstrap 总时长全部解释为 R2 网速。
- 使用私有 GHCR 镜像时，正式 env 必须配置
  `RUNPOD_CONTAINER_REGISTRY_AUTH_ID`，指向 RunPod 账户中的只读 registry auth。
  新建 Pod 的 create payload 必须包含 `containerRegistryAuthId`；凭据本身不进入
  Git、正式 env、Pod env 或 operation 日志。
- 云正式 R2 在线口径为 `user-data-prod` 单桶，`MINIO_*` 兼容变量和 `R2_*` 都指向正式 R2；`MINIO_PUBLIC_URL` 保持空，结果公开读取依赖 `R2_PUBLIC_DOMAIN=https://r2.aivison.it.com`。
- 正式 Web API / Dashboard 媒体只使用当前 R2/S3 URL；R2 miss 后只允许短签、空值或 `pending_result`，worker 只写 R2。
- legacy 退出前的用户可见热集补齐使用 `scripts/backfill_history_r2_objects.py --env-file .env.cloud.prod --hotset-profile web-visible-retire-legacy --source-storage legacy --include-input-files --batch-size 500`，默认 dry-run，真实复制必须显式 `--apply`。默认补齐范围包括每用户最近 8 条可见历史、Gallery 投稿/收藏/应用/解锁、History 收藏；若本轮只迁移社区强可见集合，追加 `--skip-per-user-recent-history`，范围收窄为所有 Gallery 投稿、History 收藏、Gallery like/apply 互动关联 active posts 与 prompt unlock 关联 active posts，并使用独立 cursor。先从 legacy 或 current 源复制原文件/已有缩略图/输入文件，再用 `--source-storage current --generate-missing-thumbnails` 从已补齐到 R2 的原文件生成缺失缩略图。
- 云正式历史详情、Gallery/Wan22 预览等读路径需要验收“返回 URL 可读”，不能只验 R2 S3 `HEAD`。若 `R2_PUBLIC_DOMAIN` 对部分 key 返回 404，但 R2 S3 `HEAD` 命中，Gallery 列表应直接返回 R2 S3 短签 URL，历史详情读路径可返回 R2 S3 短签 URL 兜底；Web owner `/result` 视频仍应按真实结果接口单独验收，不要用历史详情 fallback 代替。
- 云正式 Web 由 Cloudflare Pages 项目 `allbot-web-prod` 承接，正式 Web API 独立使用 `api.aivison.it.com` Cloudflare Tunnel 回源云 Web API；`web.aivison.it.com/api/health` 会返回 Pages SPA HTML，不作为 API 健康检查。RMB 支付入口使用 Cloudflare Tunnel 回源云 Payment API。
- Payment API 的机器健康入口为 `/healthz`，只返回服务状态与 RMB 主动查单是否
  启用；`/pay/result` 仅是用户支付跳转页。主动查单默认关闭，启用配置缺少
  `HUANYUY_QUERY_URL` 时 Payment API 必须拒绝启动。
- 云正式 Dashboard Frontend 由 `cloud-dashboard-frontend-prod` 提供，默认绑定 `100.107.220.127:8086`，`/api/` 在 Docker 内网反代 `dashboard-backend-prod:8043`。QQCC 懒人 Bot 配置已剥离为 `cloud-qqcc-config-frontend-prod` / `cloud-qqcc-config-backend-prod`，默认 `100.107.220.127:8088` / `8045`，并使用独立 `QQCC_CONFIG_*` 管理账号。管理入口若需要公网域名，必须通过 Cloudflare Tunnel + Access 或等价身份层保护，禁止裸开 `8086`/`8043`/`8088`/`8045`。
- Telegram Local API 节点 `69.63.220.115` 当前只能做 8081/8082 公网端口探测；完整容器和磁盘排障需先补 SSH。
- 真实 `docker compose config` 会展开密钥，输出只能本地查看，不得贴到日志、文档或聊天中。
- 云正式 Central 高频观测接口已加入短缓存和 stale-while-revalidate；Dashboard stats 也有短缓存与 single-flight。不要通过前端 `_t` 或脚本高频击穿缓存。
- 云正式最新长期 SOP 见 `/docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`；本地正式灾备 SOP 见 `/docs/子模块_本地正式灾备切换_local_prod_fallback.md`；历史迁云证据已归档到 `/docs/archive/2026-06-cloud-migration/`。

## 2.4 本地正式灾备

- 本地主服务器只保留一套临时本地正式接管方案，不再保留日常正式入口。
- 触发条件是云正式控制面、Tunnel 或云侧数据面整体不可用，且短时间无法恢复。
- 切换前必须确认 `cloud-tg-bot-prod` 已停止或不可用；若 QQCC 懒人 Bot 也切换到本地灾备，还必须确认 `cloud-qqcc-bot-prod` 已停止或不可用，避免任一生产 Bot token 双实例 polling。
- 本地 `.env` 必须是生产口径；如果能从云端导出最新数据库，应先恢复到本地 PostgreSQL 再开放写入口。云端完全不可用时，要接受本地快照导致的对账成本。
- 旧本地 compose 仍有历史硬编码默认值和占位值；本地灾备前必须核对 Central API、Dashboard 与 worker 的 compose 渲染和容器内实际环境变量，不能只依赖 `source .env` 判断配置已生效。渲染输出和 `env` 输出可能包含密钥，只能本机查看。
- 切换 Web/API/RMB 入口前，优先只选一条网络路径，不要同时改 Pages、Tunnel、Nginx 和 DNS。
- 回切云端时必须先冻结本地新增写入并导出灾备期间的订单、用户资产、任务历史和必要日志，再恢复云端入口。

## 3. 旧本地脚本迁移口径

- 旧本地正式脚本的迁移入口在 `safe_deploy.sh` 第 4 步。
- 脚本会先寻找可用的 Alembic 可执行文件，再检查 `heads` 数量。
- 一旦发现多个 head，脚本会直接中止，要求先合并 migration，而不是带病部署。
- 通过多 head 检查后，脚本会立即执行 `alembic upgrade head`。
- 生产脚本在加载 `.env` 后显式导出 `BOT_TYPE=PROD`，避免 `config.py` 的默认 TEST 语义影响生产迁移环境选择。

这意味着知识库里以下旧说法都应删除：

- “等容器启动时自动迁移”
- “部署完新容器后再手动进容器跑 upgrade head 才是标准流程”

## 4. 服务重建注意事项

- 所有自有服务只运行 digest-pinned 镜像；目标机不得现场 build。
- Compose module adapter 通过 `sudo -n docker compose` 消费保持
  `root:root 600` 的 `/etc/allbot/<env>.env`；不得把正式 env 改为 deploy 可读来
  修复权限错误。目标机必须只给 operator 配置这条既有免密 sudo 能力。
- QQCC 链式视频的尾帧探测、拼接与智能画幅适配由控制面执行；
  `qqcc-bot`、`private-bot-worker`、`qqcc-config-backend`、
  `dashboard-backend` 必须继承不可部署的 `python-media-runtime-base`。该层除
  ffmpeg/ffprobe 外固定 OpenCV headless、SmartCrop 和按 SHA-256 校验的 YuNet
  ONNX。相关 focused tests 应验证媒体工具、`cv2`/`smartcrop` 导入和模型存在；
  修改该窄基础层或媒体依赖只重建真实 descendants。
- Dashboard、QQCC Config 或 Bot 由操作者明确选择 catalog 模块；发布器只
  核对目标结果，不自动扩大消费者集合。
- `workers` 更新环境变量时，应使用 `docker-compose up -d` 触发重新创建，而不是只做 `restart`。
- 当前受支持的测试环境是云测试控制面；旧本地测试脚本仍可能留在仓库内作为历史迁移/取证材料，但不应被当成回滚目标。
- 若人工取证确需短时启动旧本地隔离测试栈，应使用独立的 `.env.test`、`backend/docker-compose-test.yml` 与 `workers/docker-compose-test.yml`，并让测试入口服务指向独立的 Central API 端口与独立 Redis 队列；否则可能与正式或云测试环境共用任务调度面。
- `workers/docker-compose-test.yml` 中的 `${...}` 插值不会读取 `env_file: ../.env.test` 的值。短时启动旧本地测试 worker 后仍要用 `docker exec <worker> env` 核对实际生效值，避免 401 或读写错误桶；取证完成后立即停止旧本地测试栈。
- 云正式本地 worker 使用 `workers/docker-compose-cloud-prod-worker.yml`。本地主服务器仍可能是 `docker-compose 1.29.2`，目标 worker `up` 触发 `KeyError: 'ContainerConfig'` 时，只删除目标正式 worker 容器和同 service label 残留，再 `up -d --no-deps`；不得使用 `--remove-orphans`，不得清理测试 worker 或旧本地 worker。
- 常规云正式 worker/relay 更新优先进入维护或等价门禁，阻止新生成任务进入，等待 pending/running 或至少目标 worker 当前任务归零后再重建；worker 正在处理任务时重建会中断该 worker 当前单任务。紧急抢修可按目标 worker 直接处理，但必须明确接受该 worker 当前任务可能中断。

## 4.1 workflow 资产事实源

- `workers/comfy_agent/workflows` 是唯一 workflow 运行时事实源；`backend/workflows` 已退出，Central API 不再挂载、COPY 或启动校验 workflow 目录。
- 修改 workflow JSON、`mappings.json` 或 workflow patcher 时，只更新 Worker 目录，并重建或重启会执行该 task type 的 Worker。
- Worker 初始化 `WorkflowPatcher` 时仍会校验 `workers/comfy_agent/workflows/mappings.json`，确保映射节点和输入名存在；Central API 只负责请求参数与队列，不再以 workflow 文件作为启动门禁。
- 若只重建 Central API 而未重建 Worker，workflow 变更不会生效；新增 task type 还必须同步 `TASK_TYPE_WORKFLOW_FILENAMES`、`mappings.json` 和目标 Worker 的 `SUPPORTED_TASK_TYPES`。

## 4.2 局域网 GPU 节点操作边界

- 局域网 GPU 节点的 SSH、硬件、ComfyUI 容器、模型挂载和安全操作边界分别见：
  - `/docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md`
  - `/docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`
- `cloud-prod-comfy-agent-*` 是本地主服务器上的 worker 容器；GPU 节点上的 `comfy0/comfy1` 或宿主机 ComfyUI 是另一层。替换 worker 不会自动重启 ComfyUI，重启 ComfyUI 也不会更新 worker 代码。
- 双卡 GPU 节点上，`comfy0` 与 `comfy1` 绑定不同 GPU 和不同 `inst0/inst1` 输入输出目录，但共享模型目录和宿主机资源。单个任务类型或单个 worker 异常时，只操作目标 worker 和目标 Comfy 容器。
- 禁止因为一个 Comfy 容器异常而整机 reboot、无 service 名 `docker compose down/up`、批量删除所有 Comfy 容器或清理整个共享模型目录。
- `allbot-gpu-226` 的 ComfyUI 是宿主机进程，cwd 为 `/home/ubantu/comfyui`，不是 Docker Comfy 容器；不要对它执行 `docker restart comfy0`。
- GPU 节点 ComfyUI 素材清理优先使用 `scripts/cleanup_lan_comfy_artifacts.sh`；脚本默认 dry-run，必须显式 `--execute` 才删除。当前保守策略是 `output/temp` 清 60 分钟以前文件，`input` 只清 24 小时以前文件。不要把“只保留 1 小时”直接套到 `input`，也不要清理 `models/custom_nodes/workflows`。
- 2026-06-08 已清理一次旧素材，但 `input/output/temp` 会持续增长；模型下载、Docker pull/build 或大视频输出前必须重新检查 `df -hT`。

## 5. 常见问题与恢复约束

- MinIO 503 / 上传假死
  - 现象：Web 请求超时，甚至非上传接口也被拖慢。
  - 根因：Region 探测阻塞事件循环。
  - 处理：重启 MinIO，并保持 `_region_map` 离线映射策略。
- Nginx 404 / 502
  - `404` 常见于 `proxy_pass` 带错误路径
  - `502` 常见于后端服务或 Tailscale 链路不可达
- 旧本地测试 worker 短时取证后出现 401 / 读错桶
  - 常见根因：把 `env_file` 当成 compose `${...}` 插值来源，或测试 worker 容器内实际 `AGENT_SECRET_TOKEN`、`MINIO_INPUT_BUCKET`、`MINIO_RESULT_BUCKET` 与 `.env.test` 口径不一致
  - 处理：核对 `workers/docker-compose-test.yml` 默认值是否仍为测试桶，重建后用 `docker exec <worker> env` 验证 `MINIO_INPUT_BUCKET=bot-data-test`、`MINIO_RESULT_BUCKET=comfyui-temp-test`，并确认 token 与旧本地测试 Central API 一致；取证结束后停止该栈
- 云测试 R2 新对象公开域名返回 403
  - 现象：R2 S3 API `head_object` 成功，但 `https://r2-test.aivison.it.com/<new-key>` 返回 403
  - 处理：若只是图片结果，可临时使用 R2 S3 预签名 URL 闭环；若是 Web 视频结果，必须优先修复公开域名或改造 owner result fallback，否则 `/api/tasks/{task_id}/result` 会持续 `pending_result`
- 云正式 `/system/status`、管理后台 worker 监控卡顿
  - 常见根因：Central 状态观测重复扫描 Redis/Valkey、Dashboard stats 重查询、前端高频缓存击穿或 Valkey 连接抖动。
  - 处理：确认 Central 使用共享 Redis 客户端和约 10 秒观测缓存；确认 Dashboard stats 缓存未被 `_t` 参数击穿；确认 `/system/status` 和 `/system/workers` 只是观测接口，不参与任务分发。
- 云正式 Central 健康检查与全部 Worker 心跳同时消失，但进程仍在
  - 常见根因：Central 的结果媒体代理读取 R2/MinIO 时发生慢读或不完整响应，并在单进程事件循环中执行了同步存储调用；Dashboard 对 Central 超时会降级显示 `0 Worker`，不代表 GPU Worker 已全部退出。
  - 处理：关联 Central 日志中的媒体 `Fetching`、存储读取错误和健康检查超时；结果媒体下载必须在线程中执行，不能阻塞 heartbeat、pop、status、complete 与观测接口。紧急恢复可只重启当前 Central 精确镜像，但旧镜像被同一媒体请求再次命中时仍会复发，必须发布包含非阻塞读取修复的 Central artifact。
- 云控制面磁盘被 Docker 构建缓存或无限容器日志占用
  - 先用 `df -hT`、`docker system df -v`、`docker buildx du` 和逐容器 HostConfig 只读核对真实占用；构建缓存的 reclaimable 数字不等于可无条件删除，仍需确认当前无 CI/发布构建使用对应 builder。
  - 正式控制面 Compose 的所有服务必须保持 `json-file`、`max-size=50m`、`max-file=5`，并通过不可变发布重建生效。已有超大日志不会因仓库修改自动收缩；不得直接删除 `/var/lib/docker/containers` 下文件。
  - `docker builder prune` / `docker buildx prune` 属于正式主机 mutation，必须获得当次明确授权并限定 builder/保留窗口；执行前后记录 `df` 与 builder cache 差值，不顺带 prune image、volume 或运行容器。
- 本地 GPU 生成中“停几秒再继续”
  - 常见根因：ComfyUI 模型/LoRA 加载、显存切换、WebSocket 终态未及时返回、worker 转 `/history/{prompt_id}` 轮询收口。
  - 处理：查对应 `cloud-prod-comfy-agent-*` 日志和 ComfyUI `/system_stats`，不要直接归因为 Central 状态接口慢。
- 双卡 GPU 节点只坏一个 ComfyUI
  - 现象：同一台 GPU 服务器上一个端口异常，另一个端口仍正常。
  - 处理：按 worker 到 Comfy 的映射只重启目标 `comfy0` 或 `comfy1`，并验证未操作端口 `/system_stats` 仍可用。不要整机重启，也不要执行无 service 名 compose 操作。
- SCAIL-2 正式 RunPod 停摆或 OOM
  - 现象：`runpod_prod_scail2_manual_NN` heartbeat 进入 `error` / unhealthy，或 RunPod 日志提示内存限制。
  - 处理：先通过 Central control `disable` 停止接新单，确认 `current_task_id` 为空后用 `scripts/runpod_prod_ops.sh down --profile scail2 --slot NN --execute` 删除 Pod 释放计费资源。不要让 Dashboard 或 CLI 并发创建多条相同 `scail2` add operation；需要恢复时重新 `add --profile scail2 --count 1`，等待 disabled heartbeat、canary 两单 MP4 成功后再决定是否 enable。SCAIL-2 正式主路径仍以 gpu-002 slot0 LAN runtime 为准。
- LTX 正式 RunPod 停摆或输出异常
  - 现象：`runpod_prod_ltx_video_manual_NN` heartbeat 进入 `error` / unhealthy，或 canary/正式任务未产出有效 MP4。
  - 处理：先 `disable` 停接，确认无当前任务后优先 `down --profile ltx_video --slot NN --execute` 删除重建；恢复时重新 `up/add`、等待 disabled heartbeat、跑一单 `canary --profile ltx_video` 5s I2V MP4，确认产物后再 enable。不要把模型临时打入正在运行的 LAN LTX AIO 容器来修 RunPod；RunPod 只认 GHCR 镜像 + `allbot-model-cache/ltx_video/2026-06-10/manifest.json` + v1.2 workflow override。
- LTX 正式 LAN AIO workflow bundle 过旧
  - 现象：`lan_aio_prod_gpu177_gpu1_ltx_video_01` heartbeat 正常但镜像内 RunPod runtime 缺少 10Eros v1.2 workflow，或容器 env 缺少 `TASK_TYPE_WORKFLOW_OVERRIDES`。
  - 处理：在正式生成维护开启且队列为空时，只对 `gpu-177-gpu1-ltx_video` 执行 `scripts/lan_aio_fleet_prod_ops.py start-disabled --slot gpu-177-gpu1-ltx_video --execute`，确认 disabled heartbeat、AIO `/object_info`、v1.2 workflow 文件和模型文件后再 `enable-aio`。不要批量重启 GPU 节点，不要通过 RunPod 脚本修 LAN AIO。

## 6. 文档维护口径

- 涉及本地正式灾备 compose 的文档必须和 `safe_deploy.sh` 的真实顺序保持一致；云正式和云测试文档必须分别以对应 cloud compose / cloud deploy 脚本为准。
- 若云测试流程、旧本地测试栈退役口径、`safe_deploy_cloud_test.sh` 或“测试优先发布”策略发生变化，必须同步更新运维技能、`AGENTS.md` 与本子模块文档。
- 若云正式、本地灾备、Cloudflare Tunnel、Pages 或边缘 upstream 发生变化，必须同步更新云正式、网络、边缘、资源画像和本地灾备文档。
- 任何涉及 Alembic 的说明，都应明确“先检查多 head，再在宿主机执行 upgrade head”。
- 任何涉及容器代码更新的说明，都应先核对卷挂载，再决定是 `restart` 还是 `--build`。
- 任何涉及 workflow 资产的说明，都应明确 Central 校验目录与 Worker 执行目录是否一致。
- 任何涉及 GPU 节点运维的说明，都应明确 worker 容器、ComfyUI 容器、模型目录和 `inst0/inst1` 目录是否共享或隔离。
