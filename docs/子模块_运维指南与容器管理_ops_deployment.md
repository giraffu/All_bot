# 子模块: 运维指南与容器管理 (Ops & Deployment)

## 1. 目标与范围
本模块记录当前仓库真实生效的部署顺序、迁移策略与常见故障恢复方式。最重要的事实更新有两点：
- 数据库迁移已经由 `safe_deploy.sh` 在宿主机上主动执行，不再依赖“容器下次启动自动迁移”。
- `web-api` 等服务若未挂载源码卷，代码变更后必须 `--build` 重建镜像才会生效。

## 2. 当前推荐部署路径
- 功能研发、联调、修复、配置调整：首选隔离测试栈或云测试控制面，按目标环境使用 `bash safe_deploy_test.sh` 或 `scripts/safe_deploy_cloud_test.sh`
- 当前云正式生产热修：按云正式文档使用 `scripts/safe_deploy_cloud_prod.sh` 或目标 cloud-prod compose 单服务重建
- 旧本地正式整栈发布：仅在明确需要维护本地旧正式栈时才执行 `bash safe_deploy.sh`
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
  - 发布生产 Web 静态站到边缘 VPS
- `safe_deploy.sh` 到此结束，不会顺带重建测试环境；它不代表当前云正式控制面的首选发布入口。
- 若仅更新隔离测试栈，可执行 `bash safe_deploy_test.sh`；它会处理 `.env.test`、测试数据库迁移、测试 workers、测试 central api、测试入口服务，以及 `frontend/scripts/deploy-edge-test.sh` 对应的边缘 VPS 测试站静态资源发布；不会重建生产服务，也不会重建正式 Dashboard。

## 2.1 当前默认发布策略
- AI 在功能研发期间默认只能更新隔离测试环境，不得主动执行生产部署。
- “帮我改功能”“帮我修 Bug”“帮我联调”“帮我验证配置”这类请求，默认理解为测试环境操作。
- 只有在用户明确表达“上线”“发布”“部署正式环境”“交付生产”后，才允许切换到 `safe_deploy.sh` 或生产 compose。
- 在用户完成测试验收前，不得把测试环境变更直接同步到正式 Bot、正式 Web、正式 Payment、正式 Central API 或正式 Dashboard。

## 2.2 云端测试控制面
- DigitalOcean SGP1 Droplet 上的云测试控制面入口为 `scripts/safe_deploy_cloud_test.sh`，compose 文件为 `deploy/docker-compose-cloud-test.yml`。
- 云测试控制面默认部署 Postgres、Redis、Central API、Web API、Dashboard Backend 与 imgproxy；不启动 Telegram test bot，也不启动 GPU worker。当前对象存储事实源是 Cloudflare R2，兼容 MinIO 仅通过 `compat-minio` profile 按需启动，Payment API 仅通过 `payment` profile 按需启动。
- 云测试 `.env.cloud.test` 已被 `.gitignore` 忽略，不能提交到仓库。
- 云端服务端口默认绑定 `127.0.0.1`；配置 `CLOUD_TEST_BIND_IP=<云服务器 Tailscale IPv4>` 后，测试入口服务绑定到 Tailscale IP，不直接开放公网。
- 云测试全链路 worker 使用 `workers/docker-compose-cloud-worker-test.yml`，容器名为 `cloud-comfy-agent-test-*`，从本地主服务器经 Tailscale 访问云端 `8004` Central API，并直接访问 R2 S3 endpoint 读写 `user-data-test`。
- 停止本地测试栈但保留数据时使用 `scripts/stop_local_test_preserve.sh`；启动本地 cloud-worker 测试栈使用 `scripts/start_cloud_worker_test.sh`。
- 云测试 `bot-test` 默认通过 `TON_PAYMENT_POLLING_ENABLED=false` 禁用 TON 链上轮询，避免空云测试库回扫真实商户地址历史交易；仅在专门支付联调时显式开启 `CLOUD_TEST_TON_PAYMENT_POLLING_ENABLED=true`。
- 云测试库若为空，脚本使用当前 ORM schema 初始化并 `alembic stamp head`；若已有 schema，脚本执行 `alembic upgrade head`。这是云测试控制面的特殊兼容策略，不改变生产脚本的迁移口径。
- 云测试 `.env.cloud.test` 中 `MINIO_*` 是项目兼容变量名；R2 直连时应保持 `MINIO_SECURE=true`、`MINIO_BUCKET/MINIO_INPUT_BUCKET/MINIO_RESULT_BUCKET/MINIO_TEMPLATE_BUCKET=user-data-test`、`MINIO_PUBLIC_URL=`、`R2_PUBLIC_DOMAIN=https://r2-test.aivison.it.com`。Web owner 视频结果接口依赖 R2 公网 URL，公开域名缺失会导致视频停在 99% / `pending_result`。
- 云测试公网 Web 使用 `web-test.aivison.it.com` 的边缘 VPS 静态站，`/api/` 反代到云端测试 Web API `http://100.107.220.127:8001`；云端 `web-frontend-test` / `dashboard-frontend-test` dev 容器只在临时调试时启用 `frontend` profile。
- 详细说明见 `/docs/子模块_云测试控制面部署_cloud_test_control_plane.md`。

## 2.3 云正式控制面
- 2026-06-07 晚间正式生产已切到云控制面。当前长期运维入口为 `deploy/docker-compose-cloud-prod.yml`、`workers/docker-compose-cloud-prod-worker.yml`、`scripts/safe_deploy_cloud_prod.sh`、`all_bot_nginx_cloud_prod.conf` 和 `all_bot_nginx_cloud_prod_rmb.conf`。
- `.env.cloud.prod` 是本机私有文件，已被 `.gitignore` 忽略；`.env.cloud.prod.example` 只提供变量契约和占位值。`.dockerignore` 必须忽略 `.env.*`，避免 root Docker build 把真实云正式变量 COPY 进镜像。
- 云正式 Web API 需要 `JWT_SECRET_KEY`，且不能使用默认占位值；该 key 已纳入 `.env.cloud.prod.example` 和 `scripts/safe_deploy_cloud_prod.sh` preflight 必填检查。
- 云测试环境退役入口为 `scripts/cleanup_cloud_test_for_prod.sh`。脚本默认 dry-run，真实清理必须传 `--execute`；它只清云测试容器、本地 `cloud-comfy-agent-test-*`、`bot_db_test` 和 Valkey DB3/DB4，不删除 R2 `user-data-test`，不改 `web-test.aivison.it.com` 边缘站。
- 云正式控制面包含 Central API、Web API、Payment API、Dashboard Backend、imgproxy 和正式 Bot；`cloud-tg-bot-prod` 使用 `bot` profile，重建前必须确认全网只有一个生产 polling 实例。
- 云正式 worker 只派生当前本地正式 7 个 worker，容器名为 `cloud-prod-comfy-agent-*`；启动或重建后必须在云 Central `/system/workers` 验证 7 个 `cloud_prod_worker_*` heartbeat，状态不能是 `error` 或 `quarantined`。
- 云正式 R2 在线口径为 `user-data-prod` 单桶，`MINIO_*` 兼容变量和 `R2_*` 都指向正式 R2；`MINIO_PUBLIC_URL` 保持空，结果公开读取依赖 `R2_PUBLIC_DOMAIN=https://r2.aivison.it.com`。
- 迁移期旧媒体不再要求切换前全量搬完 `bot-data`；Web API / Dashboard 可通过 `LEGACY_MINIO_*` 只读回源本地 MinIO。该 fallback 只用于 R2 miss 后读取旧历史媒体，worker 仍只写 R2，不得把 legacy MinIO 配进 worker 写路径。
- 用户可见历史对象预热使用 `scripts/backfill_history_r2_objects.py --visible-scope user-visible --source-storage legacy`，默认 dry-run，真实复制必须显式 `--apply`。推荐先 `--media-only` 预热 `history/{task_id}/original.ext`，再 legacy copy-only 复制已有缩略图，最后用 `--source-storage current --generate-missing-thumbnails` 从已预热到 R2 的原文件生成缺失缩略图。
- 云正式历史详情、Gallery/Wan22 预览等读路径需要验收“返回 URL 可读”，不能只验 R2 S3 `HEAD`。若 `R2_PUBLIC_DOMAIN` 对部分 key 返回 404，但 R2 S3 `HEAD` 命中，Gallery 列表应直接返回 R2 S3 短签 URL，历史详情读路径可返回 R2 S3 短签 URL 兜底；Web owner `/result` 视频仍应按真实结果接口单独验收，不要用历史详情 fallback 代替。
- 云正式边缘 Web 主模板必须保留 `assets.aivison.it.com` 到本地 MinIO 的 legacy 代理；不要为了维护 `web.aivison.it.com /api/` 删除 assets server。当前 `web.aivison.it.com /api/` 已指向云 Web API；RMB 支付入口继续使用 Cloudflare Tunnel 回源云 Payment API。如需紧急回滚 RMB 回源，用 `scripts/rollback_rmb_tunnel_to_local_prod.sh --execute` 切回本地 Payment API。切换/回滚脚本默认 dry-run，真实执行必须显式 `--execute`。
- 真实 `docker compose config` 会展开密钥，输出只能本地查看，不得贴到日志、文档或聊天中。
- 云正式 Central 高频观测接口已加入短缓存和 stale-while-revalidate；Dashboard stats 也有短缓存与 single-flight。不要通过前端 `_t` 或脚本高频击穿缓存。
- 云正式最新长期 SOP 见 `/docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`；历史门禁证据见 `/docs/正式云环境切换前准备清单.md`，迁移总手册见根目录 `正式服务_云发布环境迁移计划.md`。

## 3. 当前真实迁移口径
- 迁移入口在 `safe_deploy.sh` 第 4 步。
- 脚本会先寻找可用的 Alembic 可执行文件，再检查 `heads` 数量。
- 一旦发现多个 head，脚本会直接中止，要求先合并 migration，而不是带病部署。
- 通过多 head 检查后，脚本会立即执行 `alembic upgrade head`。
- 生产脚本在加载 `.env` 后显式导出 `BOT_TYPE=PROD`，避免 `config.py` 的默认 TEST 语义影响生产迁移环境选择。

这意味着知识库里以下旧说法都应删除：
- “等容器启动时自动迁移”
- “部署完新容器后再手动进容器跑 upgrade head 才是标准流程”

## 4. 服务重建注意事项
- `web-api`、`payment-api`、Dashboard、CS Bot 等通过镜像 `COPY` 代码的服务，修改代码后都要重建镜像，单纯 `restart` 不会拿到新代码。
- `workers` 更新环境变量时，应使用 `docker-compose up -d` 触发重新创建，而不是只做 `restart`。
- 当前仓库的测试环境与正式环境已经使用独立数据库；`safe_deploy_test.sh` 只会基于 `.env.test` 校验并迁移测试库，`safe_deploy.sh` 只会基于 `.env` 校验并迁移正式库，两套迁移应按各自环境分别执行，互不替代。
- 若启用隔离测试栈，应使用独立的 `.env.test`、`backend/docker-compose-test.yml` 与 `workers/docker-compose-test.yml`，并让测试入口服务指向独立的 Central API 端口与独立 Redis 队列。
- 隔离测试栈的最低要求是：测试 Bot/Web/Payment 使用测试库，Central API 使用独立 Redis DB 作为队列，测试 workers 连接测试 Central API；否则仍会与正式环境共用任务调度面。
- `workers/docker-compose-test.yml` 中的 `${...}` 插值不会读取 `env_file: ../.env.test` 的值；当前测试 compose 已让 `AGENT_SECRET_TOKEN` 从 `env_file` 注入，并将 `MINIO_INPUT_BUCKET` / `MINIO_RESULT_BUCKET` 默认到 `bot-data-test` / `comfyui-temp-test`。重建测试 worker 后仍要用 `docker exec <worker> env` 核对实际生效值，避免 401 或读写错误桶。
- `safe_deploy_test.sh` 里的测试 Web VPS 发布依赖宿主机可执行 `npm`，并通过 `frontend/scripts/deploy-edge-test.sh` 使用 SSH/SCP 把 `build:edge-test` 产物同步到边缘 VPS；若私钥缺失、`npm` 未安装或边缘域名不可达，脚本会中止而不是假装发布成功。
- 云正式本地 worker 使用 `workers/docker-compose-cloud-prod-worker.yml`。本地主服务器仍可能是 `docker-compose 1.29.2`，目标 worker `up` 触发 `KeyError: 'ContainerConfig'` 时，只删除目标正式 worker 容器和同 service label 残留，再 `up -d --no-deps`；不得使用 `--remove-orphans`，不得清理测试 worker 或旧本地 worker。
- 用户已确认云正式 worker 热更新可以不启用全站维护；但 worker 正在处理任务时重建会中断该 worker 当前单任务。紧急修复可直接更新，非紧急修复仍建议先评估队列和 worker 运行态。

## 4.1 workflow 资产事实源
- `workers/comfy_agent/workflows` 是唯一 workflow 运行时事实源；`backend/workflows` 已退出，Central API 不再挂载、COPY 或启动校验 workflow 目录。
- 修改 workflow JSON、`mappings.json` 或 workflow patcher 时，只更新 Worker 目录，并重建或重启会执行该 task type 的 Worker。
- Worker 初始化 `WorkflowPatcher` 时仍会校验 `workers/comfy_agent/workflows/mappings.json`，确保映射节点和输入名存在；Central API 只负责请求参数与队列，不再以 workflow 文件作为启动门禁。
- 若只重建 Central API 而未重建 Worker，workflow 变更不会生效；新增 task type 还必须同步 `TASK_TYPE_WORKFLOW_FILENAMES`、`mappings.json` 和目标 Worker 的 `SUPPORTED_TASK_TYPES`。

## 5. 常见问题与恢复约束
- MinIO 503 / 上传假死
  - 现象：Web 请求超时，甚至非上传接口也被拖慢。
  - 根因：Region 探测阻塞事件循环。
  - 处理：重启 MinIO，并保持 `_region_map` 离线映射策略。
- Nginx 404 / 502
  - `404` 常见于 `proxy_pass` 带错误路径
  - `502` 常见于后端服务或 Tailscale 链路不可达
- CS Bot 改代码不生效
  - 根因通常是只做了 `docker restart`
  - 处理必须是 `docker-compose up -d --build`
- 测试 worker 重建后出现 401 / 读错桶
  - 常见根因：把 `env_file` 当成 compose `${...}` 插值来源，或测试 worker 容器内实际 `AGENT_SECRET_TOKEN`、`MINIO_INPUT_BUCKET`、`MINIO_RESULT_BUCKET` 与 `.env.test` 口径不一致
  - 处理：核对 `workers/docker-compose-test.yml` 默认值是否仍为测试桶，重建后用 `docker exec <worker> env` 验证 `MINIO_INPUT_BUCKET=bot-data-test`、`MINIO_RESULT_BUCKET=comfyui-temp-test`，并确认 token 与测试 Central API 一致
- 云测试 R2 新对象公开域名返回 403
  - 现象：R2 S3 API `head_object` 成功，但 `https://r2-test.aivison.it.com/<new-key>` 返回 403
  - 处理：若只是图片结果，可临时使用 R2 S3 预签名 URL 闭环；若是 Web 视频结果，必须优先修复公开域名或改造 owner result fallback，否则 `/api/tasks/{task_id}/result` 会持续 `pending_result`
- 云正式 `/system/status`、管理后台 worker 监控卡顿
  - 常见根因：Central 状态观测重复扫描 Redis/Valkey、Dashboard stats 重查询、前端高频缓存击穿或 Valkey 连接抖动。
  - 处理：确认 Central 使用共享 Redis 客户端和约 10 秒观测缓存；确认 Dashboard stats 缓存未被 `_t` 参数击穿；确认 `/system/status` 和 `/system/workers` 只是观测接口，不参与任务分发。
- 本地 GPU 生成中“停几秒再继续”
  - 常见根因：ComfyUI 模型/LoRA 加载、显存切换、WebSocket 终态未及时返回、worker 转 `/history/{prompt_id}` 轮询收口。
  - 处理：查对应 `cloud-prod-comfy-agent-*` 日志和 ComfyUI `/system_stats`，不要直接归因为 Central 状态接口慢。

## 6. 文档维护口径
- 部署文档与运维技能必须和 `safe_deploy.sh` 的真实顺序保持一致。
- 若测试栈流程、`.env.test` 口径、`safe_deploy_test.sh` 或“测试优先发布”策略发生变化，必须同步更新运维技能、`AGENTS.md` 与本子模块文档。
- 任何涉及 Alembic 的说明，都应明确“先检查多 head，再在宿主机执行 upgrade head”。
- 任何涉及容器代码更新的说明，都应先核对卷挂载，再决定是 `restart` 还是 `--build`。
- 任何涉及 workflow 资产的说明，都应明确 Central 校验目录与 Worker 执行目录是否一致。
