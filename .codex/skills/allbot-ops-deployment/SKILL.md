---
name: "allbot-ops-deployment"
description: "处理 Docker Compose 编排、safe_deploy/safe_deploy_test、Alembic 迁移和故障恢复。研发默认先发测试环境，正式发布需用户明确确认。"
---

# AllBot 运维指南与容器管理 (Ops & Deployment)

本技能用于规范 AllBot 的部署、迁移与系统级排障，必须以当前 `safe_deploy.sh` 与 `safe_deploy_test.sh` 的真实流程为准。

## 1. 模块功能描述
- **测试优先部署**：功能研发、联调、修复与配置调整默认先更新隔离测试栈，优先使用根目录 `safe_deploy_test.sh`；只有在用户明确要求正式发布或交付验收通过后，才允许使用 `safe_deploy.sh` 更新生产环境。
- **标准部署入口**：测试环境优先使用 `safe_deploy_test.sh`，生产环境使用 `safe_deploy.sh`，避免手工拼接多个目录的容器命令。
- **云测试控制面入口**：DigitalOcean SGP1 云端测试控制面使用 `scripts/safe_deploy_cloud_test.sh` 与 `deploy/docker-compose-cloud-test.yml`。云端运行 Central API、Web API、Dashboard Backend、imgproxy、测试 Bot，并通过 `CLOUD_TEST_DATABASE_URL` 连接 DigitalOcean 托管 PostgreSQL，通过 `CLOUD_TEST_REDIS_URL`/`CLOUD_TEST_WORKER_REDIS_URL` 连接 DigitalOcean 托管 Valkey；GPU worker 仍在本地主服务器以 `workers/docker-compose-cloud-worker-test.yml` 运行，并经 Tailscale 访问云端 Central API；对象存储事实源为 R2。
- **云正式切换前准备入口**：正式控制面迁云准备使用 `.env.cloud.prod`、`deploy/docker-compose-cloud-prod.yml`、`workers/docker-compose-cloud-prod-worker.yml`、`scripts/safe_deploy_cloud_prod.sh`、`scripts/start_cloud_prod_worker.sh` 与 `scripts/stop_local_prod_entry_preserve.sh`。这些文件只用于维护窗口前门禁、预启动和保留式停止，不代表正式切流授权；`cloud-tg-bot-prod` 使用 `bot` profile，默认不得启动。云正式 Web API 必须配置非占位 `JWT_SECRET_KEY`，preflight 应在启动前拦截缺失或默认值。
- **云正式旧媒体策略**：新数据写入 R2 `user-data-prod`；旧 `bot-data` 不再要求切换前全量强搬，改用 `scripts/backfill_history_r2_objects.py --visible-scope user-visible --source-storage legacy` 预热用户可见集合，并通过 `LEGACY_MINIO_*` 在 Web API / Dashboard 读路径启用本地 MinIO 只读 fallback。Worker 写路径不得配置 legacy MinIO。预热顺序推荐为原文件 `--media-only`、legacy 缩略图 copy-only、再用 `--source-storage current --generate-missing-thumbnails` 从已预热 R2 原文件生成缺失缩略图；历史详情/Gallery/Wan22 预览必须做返回 URL 可读验收，不能只验 S3 HEAD。
- **云正式边缘入口模板**：`all_bot_nginx_cloud_prod.conf` 是 Web 主模板，必须保留 `assets.aivison.it.com` 到本地 MinIO 的 legacy 代理，只把 `web.aivison.it.com /api/` 切到云 Web API；`all_bot_nginx_cloud_prod_rmb.conf` 是 RMB 独立模板。当前边缘 VPS 不一定有 `rmb.aivison.it.com` 证书，正式首选继续使用 Cloudflare Tunnel。维护窗口内用 `scripts/switch_rmb_tunnel_to_cloud_prod.sh --execute` 把 tunnel 回源切到云 Payment API；如需回滚，用 `scripts/rollback_rmb_tunnel_to_local_prod.sh --execute` 切回本地 Payment API。两个脚本默认 dry-run，准备阶段只能 dry-run。
- **云测试退役入口**：当云服务器后续只作为正式控制面使用时，使用 `scripts/cleanup_cloud_test_for_prod.sh` 退役云测试。脚本默认 dry-run，真实清理必须 `--execute`；只清云测试容器、本地 `cloud-comfy-agent-test-*`、托管 PostgreSQL `bot_db_test` 与 Valkey DB3/DB4，不删除 R2 `user-data-test`，不改 `web-test.aivison.it.com` 静态站。
- **迁移保护**：部署前检查 Alembic multiple heads；发现多 head 立即中止。
- **宿主机迁移执行**：通过后直接在宿主机执行 `alembic upgrade head`，不依赖容器启动时自动迁移；生产脚本加载 `.env` 后显式导出 `BOT_TYPE=PROD`。
- **分阶段重建**：按 workers -> central api -> 主服务群 -> dashboard -> 生产 Web 边缘静态站的顺序重建/发布。
- **生产单服务重建**：当用户明确要求只重建某个正式服务时，使用目标 compose 目录内的单 service 流程；必须避免全量 `safe_deploy.sh`、避免 `--remove-orphans`、避免旧版 `docker-compose` 直接 `--force-recreate` 触发 `ContainerConfig` 兼容错误。
- **故障恢复**：处理 MinIO 503、Nginx 404/502、容器代码未更新、环境变量未生效等典型问题。
- **测试 worker 变量陷阱**：`workers/docker-compose-test.yml` 内的 `${...}` 插值不会读取 `env_file: ../.env.test`；当前测试 compose 已使用测试桶默认值并让 `AGENT_SECRET_TOKEN` 来自 `env_file`，重建后仍必须核对容器内实际生效变量，避免 401 或读写错误桶。
- **workflow 资产事实源**：`workers/comfy_agent/workflows` 是唯一 workflow 目录。Central API 不再挂载、COPY 或启动校验 workflow；修改 workflow 时默认只更新 Worker 目录，并重建/重启对应 Worker。

## 2. 操作规范
- 修改数据库结构时：
  - 先更新模型
  - 生成 migration
  - 确保只有一个 Alembic head
  - 测试研发阶段先通过 `safe_deploy_test.sh` 或测试库宿主机 Alembic 验证升级
  - 只有在用户明确要求正式发布时，才通过 `safe_deploy.sh` 或生产库宿主机 Alembic 执行升级
- 修改未挂载源码卷的服务代码时：必须 `--build` 重建镜像，不能只 `restart`。
- 功能研发默认目标环境是隔离测试栈：`.env.test`、`backend/docker-compose-test.yml`、`workers/docker-compose-test.yml`、`deploy/docker-compose-test.yml`。
- 若用户明确要把测试控制面部署到 DigitalOcean Droplet，使用 `scripts/safe_deploy_cloud_test.sh`。该脚本使用 `.env.cloud.test`，要求 `CLOUD_TEST_DATABASE_URL` 指向 DigitalOcean 托管 PostgreSQL，`CLOUD_TEST_REDIS_URL`/`CLOUD_TEST_WORKER_REDIS_URL` 指向 DigitalOcean 托管 Valkey；云端不再启动容器版 Redis。服务端口默认绑定到云主机 `127.0.0.1`，配置 `CLOUD_TEST_BIND_IP` 后绑定到云服务器 Tailscale IP，`.env.cloud.test` 不得提交。当前云测试对象存储直连 R2：`MINIO_SECURE=true`，`MINIO_BUCKET/MINIO_INPUT_BUCKET/MINIO_RESULT_BUCKET/MINIO_TEMPLATE_BUCKET=user-data-test`、`MINIO_PUBLIC_URL=`、`R2_PUBLIC_DOMAIN=https://r2-test.aivison.it.com`；Web owner 视频结果依赖 R2 公网 URL，缺失会停在 99% / `pending_result`。Web 直传依赖 R2 桶 CORS，`user-data-test` 必须允许 `web-test.aivison.it.com`/`web.aivison.it.com` 的 `GET/PUT/HEAD`。
- 云测试公网 Web 入口继续使用 `web-test.aivison.it.com` 的边缘 VPS 静态站；前端静态资源由 `frontend npm run deploy:edge-test` 发布到 `web` VPS `/root/dist-test`，VPS Nginx 的 `/api/` 必须反代到云端测试 Web API `http://100.107.220.127:8001`。
- 云端全链路切换前，先用 `scripts/stop_local_test_preserve.sh` 停止本地主服务器原测试栈但保留数据，再用 `scripts/start_cloud_worker_test.sh` 启动 7 个 `cloud-comfy-agent-test-*` 本地 GPU worker。
- 云测试 `bot-test` 默认禁用 TON 链上支付轮询；若需要支付联调，先确认测试库 checkpoint 与通知目标，再通过 `.env.cloud.test` 显式设置 `CLOUD_TEST_TON_PAYMENT_POLLING_ENABLED=true`。
- 云正式准备阶段先运行 `scripts/safe_deploy_cloud_prod.sh --preflight-only`、`scripts/start_cloud_prod_worker.sh --preflight-only` 和 `scripts/stop_local_prod_entry_preserve.sh --dry-run`；真正预启动控制面需显式传 `--start-control-plane`，worker 需显式传 `--start`，本地正式入口停止需显式传 `--execute`。
- 云测试退役阶段先运行 `scripts/cleanup_cloud_test_for_prod.sh --dry-run` 核对对象；真实清理时传 `--execute`，不得同时执行正式切流、正式 Bot 启动或边缘 Nginx reload。
- 云正式 `.env.cloud.prod` 不得提交；所有真实密钥只能来自该忽略文件。`.dockerignore` 必须忽略 `.env.*`，避免 root Docker image 把私有云正式变量 COPY 进镜像。
- 云正式迁移期若启用 `LEGACY_MINIO_*`，必须确认 `LEGACY_MINIO_PUBLIC_URL` 是浏览器可读 URL；该配置只用于历史媒体读取 fallback，不是新数据写入目标。
- 云正式 compose 渲染会展开密钥；真实 `docker compose config` 输出不得贴到日志、文档或聊天中。
- 云正式首发 worker 只包含 7 个 `cloud-prod-comfy-agent-*`；`worker_remote_01/02` 未纳入首发时，必须确认没有独占任务类型缺口。
- 云正式支付控制若仅依赖现有 Web `MAINTENANCE`，Bot RMB/Stars callback 仍可能创建订单；本轮正式切换口径已确认接受该低频风险。维护窗口先只开启 Web 维护状态并等待当前队列自然归零，不立即停止本地 Bot 或旧 worker；最终 dump 前再停止本地 Bot/旧入口，并导出 `orders` 中 `PENDING`/`CREATED` 待处理订单最终快照。
- 测试完成前，不得默认重建生产 Bot、生产 Web API、生产 Payment API、生产 Central API 或正式 Dashboard。
- 交付前必须把“测试环境已验证通过、准备正式发布”作为显式阶段切换条件，不得自行跳过用户验收。
- 若重建本地隔离测试 worker，必须额外核对容器内实际生效的 `AGENT_SECRET_TOKEN`、`MINIO_INPUT_BUCKET=bot-data-test`、`MINIO_RESULT_BUCKET=comfyui-temp-test`；不要误以为 compose `${...}` 插值会自动读取 `.env.test` 的 `env_file` 值。若重建云测试 cloud-worker，则核对 `MINIO_ENDPOINT=<R2 endpoint host>`、`MINIO_INPUT_BUCKET=user-data-test`、`MINIO_RESULT_BUCKET=user-data-test`、`MINIO_TEMPLATE_BUCKET=user-data-test`、`MINIO_SECURE=true`。
- 修改 workflow JSON、`mappings.json` 或 workflow patcher 时，默认以 `workers/comfy_agent/workflows` 为运行时事实源；Central API 不再维护 backend 副本，也不再执行 workflow 启动校验。

### 2.1 生产单服务重建标准流程
用户明确要求“只重建某个正式服务”时，先确认目标 service 存在，再按以下规则处理：

1. **加载生产环境变量再运行 compose**：`env_file` 只传给容器，不参与 compose 文件里的 `${...}` 插值；进入 `workers/`、`backend/`、`dashboard/` 等子目录执行生产 compose 前，必须先 `source /home/hfy/APP/All_bot/.env` 并 `export BOT_TYPE=PROD`。
2. **先 build，后替换目标容器**：先执行 `docker-compose build <service>`；构建成功后，只删除目标 service 的精确容器或 compose label 残留，再执行 `docker-compose up -d --no-deps <service>`。
3. **不要直接 force recreate**：当前宿主机可能使用 `docker-compose 1.29.2`，对新镜像元数据直接执行 `docker-compose up -d --no-deps --build --force-recreate <service>` 可能报 `KeyError: 'ContainerConfig'`。若已经触发该错误，只清理目标 service 的残留容器后重试，不要清理整组服务。
4. **不要清理 orphan**：workers 目录下测试栈容器可能被正式 compose 识别为 orphan。除非用户明确要求清理测试栈，否则不要加 `--remove-orphans`。
5. **避免误伤全组服务**：单服务重建时禁止执行未带 service 名的 `docker-compose rm -fsv`、`docker-compose up -d --build` 或 `docker rm -f $(docker ps -a -q -f name=comfy-agent)`。

生产 `comfy-agent-2` 这类 worker 的推荐流程：

```bash
set -euo pipefail
set -a
source /home/hfy/APP/All_bot/.env
export BOT_TYPE=PROD
set +a

cd /home/hfy/APP/All_bot/workers
docker-compose config --services | rg '^comfy-agent-2$'
docker-compose build comfy-agent-2
docker rm -f comfy-agent-2 2>/dev/null || true
docker ps -aq \
  --filter "label=com.docker.compose.project=workers" \
  --filter "label=com.docker.compose.service=comfy-agent-2" \
  | xargs -r docker rm -f
docker-compose up -d --no-deps comfy-agent-2
```

若目标 worker 正在处理任务，非紧急情况下应先告知用户会中断该 worker 当前任务，并尽量等待任务完成或确认可以中断；正式全量发布仍走 `safe_deploy.sh` 的队列门禁流程。

## 3. 核心红线
- 不要在普通功能研发过程中默认执行 `safe_deploy.sh`、生产 compose 或任何正式环境重建动作。
- 不要把“帮我改功能/修 Bug/做联调”自动理解为“允许正式部署”；除非用户明确提出上线、交付、发布、同步生产。
- 不要再写“容器下次启动会自动应用 Alembic 变更”，这不是当前标准流程。
- 不要在存在 multiple heads 的情况下继续部署。
- 不要让生产 Alembic 迁移依赖 `config.py` 的默认 `BOT_TYPE`；生产脚本应显式 `BOT_TYPE=PROD`，测试脚本显式 `BOT_TYPE=TEST`。
- 不要忽略卷挂载差异直接判断“代码已生效”。
- 不要把 `docker restart` 当作代码发布手段，特别是 `web-api`、Dashboard、CS Bot 等 COPY 型服务。
- 不要把 `env_file` 与 compose `${...}` 插值混为一谈；测试 worker 的 compose 默认值必须保持测试环境口径，重建后用 `docker exec <worker> env` 核对。
- 不要在单服务生产重建时使用 `--remove-orphans`、无 service 名的 compose 命令或全组 `docker rm` 过滤器；只允许清理目标 service 的容器和同 service label 残留。
- 不要把 workflow 放到 Central API 或 backend 目录后期待 Worker 执行；必须更新 `workers/comfy_agent/workflows` 并确认目标 Worker 支持该 task type。
- 不要默认启动云端 `bot-test` profile；除非已经确认本地主服务器的 `tg-bot-test` 停止，避免同一个测试 Telegram token 双实例冲突。
- 不要默认启动 `cloud-tg-bot-prod`；云正式控制面预启动只包含 Central/Web/Payment/Dashboard/imgproxy，正式 Bot polling 必须留到边缘入口切换和本地 Bot 停止之后。
- 不要把 cloud-prod 准备脚本当成正式切流授权；`safe_deploy_cloud_prod.sh` 不会 reload 边缘 Nginx，`stop_local_prod_entry_preserve.sh` 默认 dry-run，正式维护窗口仍需用户明确确认。
- 不要用云测试退役脚本清 R2 `user-data-test` 或边缘 `web-test.aivison.it.com`；这两个资源若要清理必须另起单独计划。
- 不要把云端 Tailscale 接入做成 subnet router；当前只允许本地主服务器访问云端测试端口，不暴露武汉家庭内网。

## 4. 测试与验证
- 测试研发阶段先验证隔离测试栈健康检查、关键 API 可达、测试库/测试 Redis/测试中控链路正确。
- 只有在测试环境完成功能验证并得到用户确认后，才进入正式环境部署验证。
- 验证 migration 在空库可顺利 `upgrade head`。
- 验证重建后容器确实运行的是新镜像，而不是旧容器旧代码。
- 云测试控制面验证至少包括 `docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml ps`，以及 `8004/health`、`8001/api/health`、`8044/api/health` 三个健康检查；全链路还要确认 `/system/workers` 能看到 7 个 `cloud_worker_test_*` heartbeat。
- 云正式准备验证至少包括：cloud-prod control compose config、worker compose config、`.env.cloud.prod` 占位值/重复 key/`API_TOKEN == AUTH_TOKEN` 检查、R2 `user-data-prod` list/head、Telegram Local Bot API reachability，以及 `8003/health`、`8000/api/health`、`8021/pay/result`、`8043/api/health` 健康检查。正式 Bot profile 不在准备阶段启动。
- 若测试 worker 涉及认证或对象存储，额外验证实际生效的 `AGENT_SECRET_TOKEN`、输入桶和结果桶与目标环境一致；云测试 R2 直连还要验证 R2 S3 `list/head`、Web API 预签名 URL 读取 200，以及从 `https://web-test.aivison.it.com` Origin 发起的 R2 `PUT` CORS 预检返回 204/200。
- 生产单服务重建后必须验证：目标容器 `Up`、`RestartCount=0`、最近日志无 `ERROR/Traceback/Exception`、关键非敏感环境变量符合正式口径。worker 需额外确认 heartbeat、Central API、ComfyUI WebSocket、MinIO 桶名正常；日志和总结中不要输出密钥值。
