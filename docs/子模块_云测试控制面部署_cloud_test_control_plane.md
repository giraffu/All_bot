# 子模块: 云测试控制面部署 (Cloud Test Control Plane)

## 1. 目标与边界
本模块记录 DigitalOcean SGP1 独立测试 Droplet `allbot-do-sgp1-test-control` 上的云端测试控制面部署方式。当前云端测试栈用于验证 Web API、Central API、Dashboard Backend、Dashboard Frontend、同机测试 PostgreSQL、同机测试 Redis、R2 对象存储、imgproxy 与测试 Bot。

当前推荐形态是云端运行测试控制面、测试数据库、测试缓存与测试 Bot，本地主服务器运行 8 个 cloud-worker 测试容器并继续使用武汉局域网内的 ComfyUI/GPU 节点。云端与本地主服务器之间使用 Tailscale 私有网络互联；SSH 端口转发只作为应急方案。

## 2. 真实入口
- 远程主机别名：`allbot-do-sgp1-test-control`
- 远程代码目录：`/home/deploy/APP/All_bot`
- Compose 文件：`deploy/docker-compose-cloud-test.yml`
- 推荐维护式更新脚本：`scripts/update_cloud_test_with_maintenance.sh`
- 远端控制面重建脚本：`scripts/safe_deploy_cloud_test.sh`
- 环境文件：`.env.cloud.test`
- 本地 cloud-worker Compose 文件：`workers/docker-compose-cloud-worker-test.yml`
- 本地停止测试栈脚本：`scripts/stop_local_test_preserve.sh`
- 本地启动 cloud-worker 脚本：`scripts/start_cloud_worker_test.sh`

`.env.cloud.test` 只允许保存在本机和云端目标目录，已通过 `.gitignore` 忽略，不得提交到仓库。

核心运行变量：

```bash
CLOUD_TEST_BIND_IP=100.82.124.91
CLOUD_TEST_CONTROL_HOST=100.82.124.91
CLOUD_TEST_TAILSCALE_IP=100.82.124.91
MINIO_ENDPOINT=c7220eb751acc6f7ab8255b4a0394ef3.r2.cloudflarestorage.com
MINIO_BUCKET=user-data-test
MINIO_INPUT_BUCKET=user-data-test
MINIO_RESULT_BUCKET=user-data-test
MINIO_TEMPLATE_BUCKET=user-data-test
MINIO_SECURE=true
MINIO_PUBLIC_URL=
R2_BUCKET=user-data-test
R2_PUBLIC_DOMAIN=https://r2-test.aivison.it.com
RUNPOD_MODEL_BUCKET=allbot-model-cache
RUNPOD_MODEL_PREFIX=img2img_lora/2026-06-10
RUNPOD_MODEL_ENDPOINT=https://c7220eb751acc6f7ab8255b4a0394ef3.r2.cloudflarestorage.com
RUNPOD_MODEL_SECURE=true
CLOUD_TEST_DATABASE_URL=postgresql+asyncpg://postgres:<password>@postgres-test:5432/bot_db_test
CLOUD_TEST_REDIS_URL=redis://:<password>@redis-test:6379/3
CLOUD_TEST_WORKER_REDIS_URL=redis://:<password>@redis-test:6379/4
```

`CLOUD_TEST_BIND_IP` 用于云端服务端口绑定；当前绑定云测试 Tailscale IP `100.82.124.91`，不直接开放公网。`CLOUD_TEST_CONTROL_HOST` 用于本地 GPU worker 访问云端 Central API，也应填 `100.82.124.91`。当前云测试对象存储直接使用 Cloudflare R2 S3 兼容接口，`MINIO_*` 是项目内兼容变量名但值指向 R2；`MINIO_PUBLIC_URL` 继续留空，`R2_PUBLIC_DOMAIN` 使用已验证的新对象公网域名。Web owner 视频结果接口只在 R2 公网 URL 可解析时返回成功，若临时清空 `R2_PUBLIC_DOMAIN`，视频任务可能在 99% / `pending_result` 等待结果 URL。

云测试 R2 变量分层：

| 变量 | 当前值或来源 | 作用 |
| :--- | :--- | :--- |
| `MINIO_*` / `R2_*` | `user-data-test` + `https://r2-test.aivison.it.com` | 用户上传、任务输入/结果、模板、历史/Gallery 媒体；不要把模型权重放入该桶 |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | `.env.cloud.test` 真实值；RunPod Pod 内使用 `allbot_cloud_test_r2_access_key` / `allbot_cloud_test_r2_secret_key` secret | 只读写 `user-data-test` |
| `RUNPOD_MODEL_*` | `allbot-model-cache` + `RUNPOD_MODEL_PREFIX`/`RUNPOD_MODEL_MANIFEST_KEY` | RunPod/LAN AIO 模型 manifest 与模型权重缓存；`img2img_lora` 默认 `img2img_lora/2026-06-10`，Wan22 cloud-test 视频主路径使用 split 前缀 `image_to_video/2026-06-13-test` 与 `wan22_video_v2/2026-06-13-test`；`i2i_pro` 使用 `i2i_pro/2026-06-14-test`；SCAIL-2 LAN AIO runtime 与 RunPod cloud-test profile 共用 `scail2/2026-06-17-test`；`wan22_aio_video/2026-06-12-test` 只作为历史全集/回滚 manifest |
| `RUNPOD_MODEL_ACCESS_KEY` / `RUNPOD_MODEL_SECRET_KEY` | `.env.cloud.test` 可保存真实值，供本地 dry-run HEAD/上传脚本使用 | 只读写 `allbot-model-cache`，不能复用 `user-data-test` 的 R2 key |
| `RUNPOD_MODEL_ACCESS_KEY_REF` / `RUNPOD_MODEL_SECRET_KEY_REF` | `allbot_model_cache_r2_access_key` / `allbot_model_cache_r2_secret_key` | RunPod create JSON 中的模型桶 secret 引用字符串，不是密钥本体 |

Cloudflare R2 页面里显示的 `cfat_...` API token 只用于 Cloudflare API，不是 S3 access key；云测试 `.env.cloud.test` 和知识库都不保存该 token。实际 S3 客户端只使用 access key id / secret access key / endpoint / bucket。

RunPod 云测试远程 worker 使用独立 worker Central 域名 `worker-central-test.aivison.it.com`，回源云测试 Central `http://100.82.124.91:8004`。2026-06-11 已在 `allbot-do-sgp1-test-control` 安装 `cloudflared` 2026.6.0，并以 Cloudflare Tunnel `RunPod-test` token 安装 systemd 服务 `cloudflared.service`；服务已能连接 Cloudflare。该 tunnel 已配置 Published application / Public hostname：

```text
Hostname: worker-central-test.aivison.it.com
Service:  http://100.82.124.91:8004
```

验收：`https://worker-central-test.aivison.it.com/health` 返回 Central API OK，`/system/status` 可读云测试队列状态。该域名只供 remote worker / RunPod Pod 访问 Central agent API，不得复用 `api.aivison.it.com`，也不要开启会拦截 worker 请求的 Cloudflare Access 登录页；先依赖 `AGENT_SECRET_TOKEN` 鉴权，并在 Cloudflare 侧加 WAF/rate limit。`cloudflared.service` 由 token-based install 创建，`systemctl status cloudflared` 可能显示 tunnel token，排障时不得把完整输出贴入文档或聊天。

Web 前端上传参考图/视频时会先调用云端 Web API 获取预签名地址，再由浏览器直接 `PUT` 到 R2 S3 endpoint。R2 `user-data-test` 桶必须配置 CORS，否则前端会显示 `Network error during upload`：

```json
[
  {
    "AllowedOrigins": [
      "https://web-test.aivison.it.com",
      "https://web.aivison.it.com"
    ],
    "AllowedMethods": ["GET", "PUT", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

## 3. 部署命令
常规测试环境更新优先在本地主服务器仓库根目录执行维护式脚本：

```bash
scripts/update_cloud_test_with_maintenance.sh --execute
```

该脚本默认流程：
1. 在云测试 `cloud-web-api-test` / `cloud-tg-bot-test` 写入生成维护标记，阻止新的生成任务提交。
2. 等待 Central Redis `comfy:queue:pending` 与 `comfy:queue:running` 同时清空。
3. 用 `rsync` 同步当前工作区代码到 `allbot-do-sgp1-test-control:/home/deploy/APP/All_bot`，保留远端 `logs/`、`runtime/`，清理并排除 `node_modules/`、`backups/`、临时模板素材等运行时或本地数据目录，并继续排除通配 `.env.*`，避免误同步正式或本地密钥文件。
4. 单独同步本地 `.env.cloud.test` 到远端 `.env.cloud.test`；同步前远端会创建 `.env.cloud.test.bak.<timestamp>` 备份，目标文件权限设为 `600`，并用校验和确认远端文件与本地一致。若需要保留远端 env，可显式加 `--skip-env-sync`。
5. 在远端执行 `scripts/safe_deploy_cloud_test.sh` 重建 Central API、Web API、Dashboard Backend、Dashboard Frontend 与 imgproxy。
6. 若测试 Bot 原本在运行，按 `bot` profile 重建并拉起 `bot-test`；若原本未运行，默认保持停止，避免抢占测试 token。
7. 默认执行 `frontend npm run deploy:edge-test` 发布 `web-test.aivison.it.com` 静态前端。
8. 验证 cloud-test compose、健康检查、Central `/system/workers` 与队列快照；队列快照按 `CLOUD_TEST_WORKER_REDIS_URL` 的 DB 读取。成功后解除生成维护；失败时维护标记保持开启，避免半更新状态继续进新任务。

常用参数：
- `--bot-mode start|skip|stop|auto`：默认 `auto`，只在 Bot 原本运行时重建并启动。
- `--env-file FILE`：指定要同步到远端 `.env.cloud.test` 的本地测试环境文件，默认读取仓库根目录 `.env.cloud.test`。
- `--skip-env-sync`：不更新远端 `.env.cloud.test`，仅使用远端现有环境文件。
- `--skip-edge-web`：只更新控制面，不发布边缘测试 Web 静态站。
- `--keep-maintenance`：部署成功后仍保持 Web/Bot 生成维护，便于人工验收后再手动解除。
- `--skip-drain`：跳过排空等待，仅用于明确接受测试环境中断的紧急更新。

测试 Web/Bot compose 挂载 `../runtime/cloud-test:/app/runtime-flags`，并通过 `GENERATION_MAINTENANCE_FILE=/app/runtime-flags/GENERATION_MAINTENANCE` 读取生成维护标记。维护式脚本会先写远端 `runtime/cloud-test/GENERATION_MAINTENANCE`，因此重建后的新容器仍会保持维护状态，直到脚本最后解除。

专项情况下，也可以从本地主服务器同步代码后，在云端只执行控制面重建子步骤：

```bash
ssh allbot-do-sgp1-test-control
cd /home/deploy/APP/All_bot
./scripts/safe_deploy_cloud_test.sh
```

`safe_deploy_cloud_test.sh` 执行顺序：
1. 校验 `CLOUD_TEST_DATABASE_URL`、`CLOUD_TEST_REDIS_URL`、`CLOUD_TEST_WORKER_REDIS_URL` 与同机 Postgres/Redis 密码。
2. 启动并等待 `postgres-test`、`redis-test` 健康。
3. 构建 Central API、Web API、Dashboard Backend、Dashboard Frontend 镜像。
4. 检查 Alembic 只有一个 head。
5. 初始化或迁移云测试数据库。
6. 重启控制面服务、Dashboard Frontend 与 imgproxy。
7. 校验 Central API、Web API、Dashboard API、Dashboard Frontend 健康检查。

启动测试 Bot：

```bash
docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml \
  --profile bot up -d bot-test
```

若历史本地测试栈仍在本地主服务器运行，切换云测试前先停止并保留数据：

```bash
./scripts/stop_local_test_preserve.sh
```

随后启动本地 cloud-worker 测试栈：

```bash
./scripts/start_cloud_worker_test.sh
```

公网测试 Web 入口继续使用边缘 VPS 的 `web-test.aivison.it.com`，不直接暴露云端 Vite 端口。当前形态是：

```text
web-test.aivison.it.com
  -> Tailscale 内的 web VPS 100.88.57.122
  -> /root/dist-test 静态前端
  -> /api/ 反代到云端测试 Web API
```

当前 `/api/` upstream 为云测试 Tailscale Web API `http://100.82.124.91:8001`。

发布静态前端：

```bash
cd frontend
npm run deploy:edge-test
```

VPS Nginx 配置文件为 `/etc/nginx/sites-available/web-test.aivison.it.com`，修改后必须执行 `nginx -t && nginx -s reload`。仓库模板为根目录 `all_bot_nginx_web_test.conf`。

## 4. 数据库初始化策略
当前历史 `initial_baseline` Alembic 迁移不是完整的空库建表迁移，它依赖一批历史表已经存在。因此云端全新测试库不能直接先跑 `alembic upgrade head`。

`safe_deploy_cloud_test.sh` 的云测试策略是：
- 若云测试库没有 `users` 表：使用当前 ORM `Base.metadata.create_all()` 初始化当前测试 schema，然后 `alembic stamp head`，再同步基础种子数据。
- 若云测试库已经存在 schema：执行 `alembic upgrade head`，再同步基础种子数据。

该策略只用于云测试控制面，不改变生产发布脚本的迁移口径。

### 4.1 同机测试 PostgreSQL
2026-06-09 新建独立测试 Droplet 后，云测试数据库改回同机容器 `postgres-test`，避免为短期测试环境单独承担托管 PostgreSQL 成本，也避免误连正式托管库。

当前事实：
- 容器名：`cloud-postgres-test`
- 镜像：`postgres:15`
- 数据卷：`cloud-postgres-test-data`
- 数据库：`bot_db_test`
- 应用连接：`CLOUD_TEST_DATABASE_URL=postgresql+asyncpg://postgres:<password>@postgres-test:5432/bot_db_test`

密码和完整连接串只允许写入 `.env.cloud.test`、云端受控 secret/env 文件或本地密码管理器，不得写入仓库文档。若未来重新使用托管 PostgreSQL，必须单独更新本文档和运维 Skill，并确认 Trusted sources、SSL 与迁移演练。

## 5. 服务与端口
所有入口服务端口绑定到云测试 Tailscale IP `100.82.124.91`，不直接暴露公网。若临时设置 `CLOUD_TEST_BIND_IP=0.0.0.0`，必须同时配置源 IP 白名单，只允许边缘 VPS 和本地主服务器访问测试 API 端口。

| 服务 | 容器名 | 本机端口 | 用途 |
| :--- | :--- | :--- | :--- |
| Central API | `cloud-central-api-test` | `8004` | 任务控制面 API，本地 cloud-worker 访问 |
| Web API | `cloud-web-api-test` | `8001` | Web BFF / 主 API |
| Dashboard Backend | `cloud-dashboard-backend-test` | `8044` | Dashboard 后端 |
| Dashboard Frontend | `cloud-dashboard-frontend-test` | `8087` | Dashboard 云端 Nginx 前端，仅 Tailscale/受控来源访问 |
| imgproxy | `cloud-imgproxy-test` | `8084` | 图片代理 |

测试机 systemd 服务 `allbot-cloud-test-firewall.service` 管理公网保护规则，脚本路径为 `/usr/local/sbin/allbot-cloud-test-firewall.sh`，规则写入 Docker `DOCKER-USER` 链。当前公网 eth0 上的 `8001/8004/8044/8084/8087` 全部 drop；Tailscale `tailscale0` 不受该规则影响。

云测试缓存与队列使用同机容器 `redis-test`，不复用正式 Valkey/Redis：

Dashboard Backend 使用同一云测试 Redis 配置持久化 RunPod operation store；本地单测可注入 in-memory fake，但云测试/正式验证 RunPod 管理时应确认 `REDIS_URL` 或 `DASHBOARD_RUNPOD_OPERATION_REDIS_URL` 可用。

```text
Container: cloud-redis-test
Image: redis:7-alpine
Volume: cloud-redis-test-data
REDIS_URL: DB 3
WORKER_REDIS_URL: DB 4
Auth: CLOUD_TEST_REDIS_PASSWORD
```

Tailscale 主链路验证：

```bash
curl -fsS http://<CLOUD_TEST_CONTROL_HOST>:8004/health
./scripts/start_cloud_worker_test.sh
```

VS Code Remote 或本地 SSH 仍可通过端口转发作为应急访问：

```bash
ssh -N \
  -L 8001:100.82.124.91:8001 \
  -L 8044:100.82.124.91:8044 \
  -L 8087:100.82.124.91:8087 \
  -L 8004:100.82.124.91:8004 \
  allbot-do-sgp1-test-control
```

## 6. 验证命令
```bash
cd /home/deploy/APP/All_bot
docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml ps
curl -fsS http://100.82.124.91:8004/health
curl -fsS http://100.82.124.91:8001/api/health
curl -fsS http://100.82.124.91:8044/api/health
curl -fsS http://100.82.124.91:8087/api/health
docker stats --no-stream
df -h /
```

2026-06-09 独立测试 Droplet 首次部署验证结果：
- Central API、Web API、Dashboard API 健康检查通过。
- 同机 Postgres/Redis 均为 healthy，Postgres/Redis 端口未发布到公网。
- 启动 `bot-test` 前已确认本地测试 Bot 停止，避免测试 token 双实例 polling。
- Droplet 根分区约 48GB，首次构建后已用约 9.2GB。

2026-06-13 RunPod `wan22_video_v2` 云测试 Web 端验收口径：
- 验收必须通过测试 Web API `http://100.82.124.91:8001/api/tasks/generate` 提交 `wan22_video_v2` preview/5s 任务，不能只做 worker 直测。
- 合格结果应同时满足：RunPod worker 接单、Central `task_type=wan22_video_v2`、终态 `done`、Web result `success`、MP4 与 `extra_outputs.last_frame` 均可下载。
- 验收结束后必须恢复临时禁用的云测试 worker，删除 RunPod Pod，并确认 `list-pods` / `reconcile-managed-pods` 的 managed count 为 0。

2026-06-14 RunPod `i2i_pro` 云测试 Web 端验收口径：
- `i2i_pro` 不是新增业务任务类型；它是 RunPod runtime profile，可同时支持执行面 `i2i_pro`、`t2i-pornmaster-turbo` 与 `face_swap`。
- 验收必须通过测试 Web API `http://100.82.124.91:8001/api/tasks/generate` 串行提交 `i2i_pro`、Web `txt2img`、`face_swap` 三单，不能只做 worker 直测。
- RunPod env 需渲染为 `RUNPOD_TASK_TYPE=i2i_pro`、`SUPPORTED_TASK_TYPES=i2i_pro,t2i-pornmaster-turbo,face_swap`、`POOL_RUNTIME_PROFILE=i2i_pro`、`AGENT_ID` 前缀 `runpod_test_i2i_pro`，并带 `TASK_TYPE_WORKFLOW_OVERRIDES={"t2i-pornmaster-turbo":"txt2img_from_i2i_pro.json","face_swap":"face_swap_v2.json"}`。
- 模型 manifest 使用 `allbot-model-cache/i2i_pro/2026-06-14-test/manifest.json`，六个模型文件总计约 `36.11 GiB`；首次 canary 使用 `RUNPOD_CONTAINER_DISK_GB=120`，GPU 只请求 `NVIDIA GeForce RTX 4090`。
- 镜像基线使用与现有图生图 / Wan22 RunPod 一致的 `yanwk/comfyui-boot:cu128-slim`；不得使用 `cu130`，若真实 canary 仍遇驱动不兼容，再降级到 `cu124`。
- 合格结果应同时满足：RunPod worker heartbeat 出现为 `runpod_test_i2i_pro_*`、三单 Central `task_type` 分别为 `i2i_pro`、`t2i-pornmaster-turbo`、`face_swap`、每单 `pop_evidence.agent_id` 均匹配 RunPod worker、终态 `done`、Web result `success`、图片可下载。
- 若当前保留了云正式手动备用 RunPod Pod，执行 `i2i_pro` cloud-test canary 时必须显式开启 `--allow-existing-prod-managed-pods` 或 `RUNPOD_CANARY_ALLOW_EXISTING_PROD_MANAGED_PODS=true`；该开关只忽略 `allbot-runpod-prod-*-manual-` 已知正式手动备用名称前缀，任何 cloud-test 残留 managed Pod 仍会阻止执行。
- 失败排障时可用 `--no-cleanup` 保留本次新建的 `i2i_pro` Pod；复跑 Web 任务使用 `--reuse-pod-id i2i_pro=<pod_id>`，不得重复创建诊断 Pod。
- 验收结束后必须恢复临时禁用的非 RunPod cloud-test `i2i_pro/t2i-pornmaster-turbo/face_swap` worker，删除本次新建的 RunPod Pod，并确认 `list-pods` / `reconcile-managed-pods` 的非忽略 managed count 为 0；既有 prod 手动备用 Pod 必须保持运行。

2026-06-17 RunPod `scail2` 云测试 Web 端验收口径：
- 本能力只做 cloud-test RunPod，不接云正式，不复用 `gpu-002/8190`。LAN AIO SCAIL-2 runtime 可继续给测试环境手工/worker 使用；RunPod canary 执行时会短暂 disable 支持 SCAIL-2 的非 RunPod cloud-test worker，通常是 `cloud_worker_test_08`，结束必须恢复。
- 模型权重转存到模型缓存桶 `allbot-model-cache/scail2/2026-06-17-test`，不能放进 `user-data-test`。入口为 `scripts/prepare_scail2_model_r2_bundle.py --env-file .env.cloud.test` dry-run，确认 6 个 HuggingFace direct URL、LoRA 路径 `loras/Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors` 和 manifest key 后，才加 `--execute` 写入 R2。
- 镜像由 `.github/workflows/runpod_scail2_profile_image.yml` 构建并推送 `ghcr.io/giraffu/allbot-comfy-runpod-scail2:<tag>`。镜像必须包含 ComfyUI SCAIL-2 core 节点、VideoHelperSuite、KJNodes、rgthree、Frame-Interpolation、Fill-Nodes、ffmpeg、sshd/bootstrap，不得 baked 任何 `.safetensors` 权重。RunPod env 使用 `RUNPOD_IMAGE_NAME_SCAIL2=<GHCR ref>`、`RUNPOD_USE_TEMPLATE_SCAIL2=false`、`RUNPOD_MODEL_PREFIX_SCAIL2=scail2/2026-06-17-test`、`RUNPOD_MODEL_MANIFEST_KEY_SCAIL2=scail2/2026-06-17-test/manifest.json`。
- RunPod env 需渲染为 `RUNPOD_TASK_TYPE=scail2`、`SUPPORTED_TASK_TYPES=scail2_action_transfer,scail2_video_replacement`、`POOL_RUNTIME_PROFILE=scail2`、`AGENT_ID` 前缀 `runpod_test_scail2`，`MINIO_RESULT_BUCKET=user-data-test`，`RUNPOD_MODEL_BUCKET=allbot-model-cache`，`containerDiskInGb=120`，GPU 优先 `NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 4090`，并带 `dockerStartCmd=["bash","-lc","exec bash /opt/allbot/runpod_bootstrap_from_git.sh"]`。
- `runpod canary --task-type scail2` 会上传/复用 Nomadoor 样例参考图与 motion video，串行提交 `scail2_action_transfer 5s` 与 `scail2_video_replacement 5s` 两个 Web 任务。合格结果应同时满足：RunPod worker heartbeat 出现为 `runpod_test_scail2_*`、两个 Central `task_type` 分别正确、每单 `pop_evidence.agent_id` 均匹配 RunPod worker、终态 `done`、Web result `success`、MP4 可下载/播放。
- 失败排障可用 `--no-cleanup` 保留本次 SCAIL-2 Pod；复跑使用 `--reuse-pod-id scail2=<pod_id>`，不得重复创建诊断 Pod。验收结束后必须恢复 `cloud_worker_test_08` 原 control 状态，删除本次 RunPod Pod，并确认 managed cloud-test Pod 清理正常。

2026-06-21 LTX 高级图生视频扩展云测试验收口径：
- LTX 用户侧仍通过 Web/Bot 的高级图生视频入口提交并写历史为 `ltx_video`；当前用户入口只开放单首帧与首尾帧，执行面分别分流为 `ltx_video`、`ltx_video_flf2v`。目标 LTX worker 仍建议声明 `SUPPORTED_TASK_TYPES=ltx_video,ltx_video_flf2v,ltx_video_v2v_audio`，并加载三份 LTX workflow，以兼容历史/队列中的 V2V Audio 任务。
- 常规验收应通过测试 Web 或测试 Bot 分别提交单首帧、首尾帧两单，不能只做 worker 直测。合格结果应同时满足：Central 中两单执行类型分别正确、目标 LTX worker 接单、终态 `done`、Web result/history 成功、输出 MP4 可下载。
- 首尾帧模式必须检查 `extra_outputs.last_frame` 可下载，并从结果页或历史详情触发“扩展生成”后能把该尾帧预填为下一段 LTX 起始帧。
- 如需回归 `ltx_video_v2v_audio` 兼容执行面，应使用受控直测或临时入口单独验证；除 MP4 可播放外，还必须用实际播放器或 `ffprobe` 检查输出存在音频流。
- 现有 `ltx_video` 单首帧路径应保持旧 workflow 与结果表现不变；若只改了新工作流，仍要至少提交一单旧 I2V 做回归。

2026-06-06 R2 切换验证结果：
- 本地测试 MinIO 历史对象已镜像到 R2 `user-data-test` 桶根路径：`bot-data-test` 约 1.10GiB，`comfyui-temp-test` 约 749.91MiB，`bot-template-test` 为空。
- 历史样本 key `242/output_images/01c4cd38-e7e9-4587-90e2-f5d15c7a1147.mp4` 在 R2 S3 API 中 HEAD 成功。
- 云端 Web API 容器实际生效：`MINIO_ENDPOINT=<R2 endpoint host>`、`MINIO_BUCKET=user-data-test`、`MINIO_SECURE=true`、`MINIO_PUBLIC_URL=`、`R2_PUBLIC_DOMAIN=https://r2-test.aivison.it.com`。
- 云端 Web API 使用 R2 预签名 URL 读写烟测通过，预签名 host 为 R2 S3 endpoint，读取状态 200。
- `https://r2-test.aivison.it.com` 已验证可读取新写入 Web 视频结果，例如 `history/<task_id>/original.mp4` 返回 200；云测试 Web owner 视频结果依赖该公网域名完成 `/api/tasks/{task_id}/result` 成功态返回。
- R2 `user-data-test` 已配置 Web 直传 CORS，允许 `https://web-test.aivison.it.com` 与 `https://web.aivison.it.com` 执行 `GET/PUT/HEAD`；`OPTIONS` 预检返回 204，实际预签名 `PUT` 上传与 `HEAD` 验证均返回 200。

2026-06-09 边缘测试 Web 切换结果：
- VPS Nginx `web-test.aivison.it.com` 只影响测试静态站和测试 `/api/`，不得修改正式 `web.aivison.it.com`。
- `/api/` upstream 已切到云测试 Tailscale Web API `http://100.82.124.91:8001`。
- 公网 eth0 测试端口已由 `allbot-cloud-test-firewall.service` drop。

2026-06-09 云端测试容器口径：
- 云端核心容器：Postgres、Redis、Central API、Web API、Dashboard Backend、Dashboard Frontend、imgproxy、bot-test。
- 云端不运行 Web 前端 dev 容器，公网测试 Web 入口使用边缘 VPS 静态站；Dashboard 测试前端由 `cloud-dashboard-frontend-test` 提供，默认端口 `8087`，只面向 Tailscale/受控来源。
- Dashboard Backend 仅供少量管理员使用，云测试连接池显式压缩为 `DB_POOL_SIZE=1`、`DB_MAX_OVERFLOW=2`。
- Dashboard Backend 使用项目 `config.py`，`BOT_TYPE=TEST` 时必须显式设置 `DATABASE_URL_TEST` 与 `REDIS_URL_TEST`，否则 `.env.cloud.test` 里的旧测试变量会覆盖 compose 中的 `DATABASE_URL`/`REDIS_URL`。

## 7. Tailscale 接入边界
- 本地主服务器已安装 Tailscale；云服务器需安装 Tailscale 并加入同一 tailnet。
- 云测试机当前 Tailscale IPv4 为 `100.82.124.91`。
- 推荐给云服务器使用 `tag:allbot-cloud-test`，并用 ACL 只放行本地主服务器与 Web 边缘访问云测试端口。
- 当前不使用 subnet router，不把武汉家庭内网 `192.168.1.0/24` 暴露给云端。
- 云端 PostgreSQL 与 Redis 均为同机 Docker 容器，不发布公网端口。
- 若 Tailscale 不可用，可临时回退 SSH `-L` 转发，或短期使用公网 IP + 源 IP 白名单；后者只允许测试 API 端口，不得开放数据库/缓存端口，恢复后必须收回公网白名单。

## 8. Bot Profile

`bot-test` profile 默认禁止启动。只有确认本地主服务器上的 `tg-bot-test` 已停止，且测试 token 不会双实例冲突时，才允许手动启动：

```bash
docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml \
  --profile bot up -d bot-test
```

云测试 `bot-test` 默认设置 `TON_PAYMENT_POLLING_ENABLED=false`，避免空云测试库启动后回扫真实 TON 商户地址的历史交易并污染测试订单/用户数据。只有需要专门联调 TON 支付履约时，才在 `.env.cloud.test` 中显式设置 `CLOUD_TEST_TON_PAYMENT_POLLING_ENABLED=true`，并先确认测试库 checkpoint 与通知目标可控。

GPU worker 不在云服务器运行；本地 `workers/docker-compose-cloud-worker-test.yml` 经 `CLOUD_TEST_CONTROL_HOST` 连接云端 Central API，并通过 R2 S3 endpoint 直接读写 `user-data-test`。默认常驻只保留 `cloud-comfy-agent-test-1` 与 `cloud-comfy-agent-test-8`：test-1 指向 `gpu-226:8188`，test-8 / `cloud_worker_test_08` 指向 gpu-002 SCAIL-2 LAN AIO runtime `http://192.168.1.2:8190`。`cloud-comfy-agent-test-2..7` 会复用正式 LAN AIO ComfyUI runtime，已加 compose profile 且默认停止；它们只允许在 smoke/canary 窗口按需启动，并默认 `PREFETCH_ENABLED=false`、`PIPELINE_ENABLED=false`、`PIPELINE_MAX_RUNNING_TASKS=1`，避免抢占正式生成容量。test-8 可通过 `.env.cloud.test` 的 `CLOUD_TEST_WORKER_08_TASK_TYPE_WORKFLOW_OVERRIDES` 做测试专用 workflow 覆盖；当前可把动作迁移/视频换人/视频换脸 v10 two-stage 分别指向 `SCAIL-2_Animation_multi-char_audio.api.json`、`SCAIL-2_Replacement_audio.api.json`、`SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json`。v10 视频换脸还通过 `CLOUD_TEST_WORKER_08_FACE_SWAP_V10_*` 打开 worker8 预处理：先调用 `192.168.1.226:8188` 的 `face_swap_v2.json` 对驱动视频第一帧做图片换脸，再提交 SCAIL-2 视频换人式 workflow。这只是测试 worker 能力，正式 SCAIL-2 worker 仍按正式发布计划单独变更。

2026-06-18 03:06 只读快照：云测试 Central `queue_size=0`，`active_workers=8`，`healthy_workers=5`，`error_workers=3`，`quarantined_workers=0`。该状态是瞬时运行态；执行测试验收前必须重新查 `/system/workers` 并按目标任务类型确认 worker 健康。

### 8.1 Shared LAN AIO cloud-test worker
`cloud-comfy-agent-test-2..7` 是共享正式 LAN AIO runtime 的云测试 worker，默认不常驻：

| Worker | Profile | 默认 ComfyUI | 任务类型 | 口径 |
| :--- | :--- | :--- | :--- | :--- |
| `cloud_worker_test_02` | `shared-aio-canary` | `192.168.1.177:8190` | `image_to_video,video_insert` | gpu-177 GPU0 AIO |
| `cloud_worker_test_03` | `shared-aio-canary` | `192.168.1.177:8191` | `ltx_video,*` | gpu-177 GPU1 LTX AIO |
| `cloud_worker_test_04` | `shared-aio-canary` | `192.168.1.252:8190` | `img2img,img2img_lora` | gpu-252 GPU0 AIO |
| `cloud_worker_test_05` | `wan22-canary` | 无健康默认入口 | `wan22_video_v2` | 默认指向 `127.0.0.1:9` 占位，必须先换成有效 RunPod/LAN endpoint |
| `cloud_worker_test_06` | `shared-aio-canary` | `192.168.1.252:8190` | `img2img,img2img_lora` | 备用 img2img shared AIO |
| `cloud_worker_test_07` | `shared-aio-canary` | `192.168.1.2:8191` | `image_to_video,video_insert` | gpu-002 slot1 image_to_video AIO |

启动共享 AIO canary 前，先确认正式队列压力可接受，且目标端口 `/system_stats` 返回 200。真实启动只针对目标服务，不要 `up` 整个 compose：

```bash
COMPOSE_PROFILES=shared-aio-canary docker-compose \
  --env-file .env.cloud.test \
  -f workers/docker-compose-cloud-worker-test.yml \
  up -d --no-deps cloud-comfy-agent-test-2 cloud-comfy-agent-test-3
```

结束窗口后立即停掉，避免云测试任务长期占用正式 AIO：

```bash
docker stop \
  cloud-comfy-agent-test-2 cloud-comfy-agent-test-3 \
  cloud-comfy-agent-test-4 cloud-comfy-agent-test-5 \
  cloud-comfy-agent-test-6 cloud-comfy-agent-test-7
```

`cloud-comfy-agent-test-5` 不随 `shared-aio-canary` 启动；`wan22_video_v2` 当前默认应走 RunPod canary 或先显式设置 `CLOUD_TEST_WORKER_05_COMFY_API_URL` / `CLOUD_TEST_WORKER_05_COMFY_WS_URL` 到健康 endpoint。

### 8.2 Worker 6/7 GPU pool 控制测试
`cloud-comfy-agent-test-6` 与 `cloud-comfy-agent-test-7` 用于 GPU pool 小范围验证时，可以临时覆盖任务类型、runtime profile 和 Comfy URL；默认配置写在 `.env.cloud.test`，临时命令行覆盖仍可用于一次性 canary：

在改动测试 worker 前，先从 Controller 生成备用端口 canary plan / compose 供审阅；该步骤只渲染 dry-run 输出，不启动或重启任何 ComfyUI 容器：

```bash
python scripts/gpu_pool_controller.py runtime-plan \
  --assignment lan-002-8188-worker-06 \
  --profile video_basic \
  --host-port 8190
python scripts/gpu_pool_controller.py runtime-render \
  --assignment lan-002-8188-worker-06 \
  --profile video_basic \
  --host-port 8190
```

```bash
set -a
source .env.cloud.test
set +a

CENTRAL="http://${CLOUD_TEST_CONTROL_HOST}:8004"
AUTH_HEADER="Authorization: Bearer ${AGENT_SECRET_TOKEN}"

curl -fsS -X POST -H "$AUTH_HEADER" -H 'Content-Type: application/json' \
  -d '{"state":"disabled","reason":"gpu-pool canary","ttl_seconds":900}' \
  "$CENTRAL/api/agent/task/control/cloud_worker_test_06"
curl -fsS -X POST -H "$AUTH_HEADER" -H 'Content-Type: application/json' \
  -d '{"state":"draining","reason":"gpu-pool canary","ttl_seconds":900}' \
  "$CENTRAL/api/agent/task/control/cloud_worker_test_07"

docker ps -aq --filter name=cloud-comfy-agent-test-6 --filter name=cloud-comfy-agent-test-7 \
  | xargs -r docker rm -f

# 该片段是历史 video_basic canary 兼容入口；新视频验证优先使用 canonical image_to_video / wan22_video_v2 split profile。
CLOUD_TEST_WORKER_06_TASK_TYPES='video_insert,image_to_video' \
CLOUD_TEST_WORKER_06_RUNTIME_PROFILE='video_basic_canary' \
CLOUD_TEST_WORKER_06_COMFY_API_URL='http://192.168.1.2:8190' \
CLOUD_TEST_WORKER_06_COMFY_WS_URL='ws://192.168.1.2:8190/ws' \
CLOUD_TEST_WORKER_07_TASK_TYPES='img2img,img2img_lora' \
CLOUD_TEST_WORKER_07_RUNTIME_PROFILE='img2img_lora_canary' \
CLOUD_TEST_WORKER_07_COMFY_API_URL='http://192.168.1.2:8191' \
CLOUD_TEST_WORKER_07_COMFY_WS_URL='ws://192.168.1.2:8191/ws' \
docker-compose --env-file .env.cloud.test -f workers/docker-compose-cloud-worker-test.yml \
  up -d --no-deps cloud-comfy-agent-test-6 cloud-comfy-agent-test-7
```

验证点：
- `/system/workers` 能看到 `cloud_worker_test_06/07` 的 `types`、`node_id=gpu-002`、`gpu_index`、`runtime_profile` 与 `pool_managed=true` 随容器环境更新。
- 备用端口 canary 时，`cloud_worker_test_06/07` 的 `COMFY_API_URL` / `COMFY_WS_URL` 指向当次显式设置的 AIO runtime 端口；如果复用正式 AIO，必须控制任务窗口和并发。
- `disabled/draining` 状态下，带 `agent_id` 的 `/api/agent/task/pop` 返回空任务，不影响其它 worker。
- 本地主服务器旧版 `docker-compose 1.29.2` 可能在 `--force-recreate` 时报 `KeyError: 'ContainerConfig'`；只删除目标 6/7 容器再 `up -d --no-deps`，不要 `--remove-orphans`。

恢复默认状态。当前默认不是重新启动 6/7，而是停止共享 AIO 测试 worker：

```bash
docker ps -aq --filter name=cloud-comfy-agent-test-6 --filter name=cloud-comfy-agent-test-7 \
  | xargs -r docker stop

curl -fsS -X POST -H "$AUTH_HEADER" -H 'Content-Type: application/json' \
  -d '{"state":"disabled","reason":"restore shared-aio cloud-test default stopped"}' \
  "$CENTRAL/api/agent/task/control/cloud_worker_test_06"
curl -fsS -X POST -H "$AUTH_HEADER" -H 'Content-Type: application/json' \
  -d '{"state":"disabled","reason":"restore shared-aio cloud-test default stopped"}' \
  "$CENTRAL/api/agent/task/control/cloud_worker_test_07"
```

## 9. 停止与退役
云测试控制面是当前唯一受支持的测试环境，不再维护“回滚到本地主服务器旧测试栈”的标准方案。需要暂停云测试时，先停测试 Bot，再停本地 cloud-worker 测试栈；云端控制面是否停止取决于当次维护目标。

```bash
docker-compose --env-file .env.cloud.test -f workers/docker-compose-cloud-worker-test.yml stop
ssh allbot-do-sgp1-test-control 'cd /home/deploy/APP/All_bot && docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml --profile bot stop bot-test'
```

旧本地测试 compose 和 `safe_deploy_test.sh` 仅作为历史迁移/人工取证材料保留。若必须短时启动，应另起临时排障计划，确认不会抢占测试 token、GPU、Redis 队列、对象桶或边缘 `web-test` 入口，结束后立即停止并保留数据。
