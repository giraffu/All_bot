# 子模块: 云测试控制面部署 (Cloud Test Control Plane)

## 1. 目标与边界
本模块记录 DigitalOcean SGP1 Droplet `allbot-do-sgp1-control-01` 上的云端测试控制面部署方式。当前云端测试栈用于验证 Web API、Central API、Dashboard Backend、DigitalOcean 托管 PostgreSQL、DigitalOcean 托管 Valkey、R2 对象存储、imgproxy 与测试 Bot。

当前推荐形态是云端运行测试控制面与测试 Bot，本地主服务器运行 7 个 cloud-worker 测试容器并继续使用武汉局域网内的 ComfyUI/GPU 节点。云端与本地主服务器之间使用 Tailscale 私有网络互联，SSH 端口转发只作为应急方案。

## 2. 真实入口
- 远程主机别名：`allbot-do-sgp1-control`
- 远程代码目录：`/home/deploy/APP/All_bot`
- Compose 文件：`deploy/docker-compose-cloud-test.yml`
- 部署脚本：`scripts/safe_deploy_cloud_test.sh`
- 环境文件：`.env.cloud.test`
- 本地 cloud-worker Compose 文件：`workers/docker-compose-cloud-worker-test.yml`
- 本地停止测试栈脚本：`scripts/stop_local_test_preserve.sh`
- 本地启动 cloud-worker 脚本：`scripts/start_cloud_worker_test.sh`

`.env.cloud.test` 只允许保存在本机和云端目标目录，已通过 `.gitignore` 忽略，不得提交到仓库。

Tailscale 相关运行变量：

```bash
CLOUD_TEST_BIND_IP=<云服务器 Tailscale IPv4>
CLOUD_TEST_TAILSCALE_IP=<云服务器 Tailscale IPv4>
MINIO_ENDPOINT=<R2 S3 endpoint host>
MINIO_BUCKET=user-data-test
MINIO_INPUT_BUCKET=user-data-test
MINIO_RESULT_BUCKET=user-data-test
MINIO_TEMPLATE_BUCKET=user-data-test
MINIO_SECURE=true
MINIO_PUBLIC_URL=
R2_BUCKET=user-data-test
R2_PUBLIC_DOMAIN=https://r2-test.aivison.it.com
CLOUD_TEST_REDIS_URL=rediss://default:<password>@<valkey-host>:25061/3
CLOUD_TEST_WORKER_REDIS_URL=rediss://default:<password>@<valkey-host>:25061/4
```

`CLOUD_TEST_BIND_IP` 用于云端服务端口绑定；`CLOUD_TEST_TAILSCALE_IP` 用于本地 GPU worker 访问云端 Central API。当前云测试对象存储直接使用 Cloudflare R2 S3 兼容接口，`MINIO_*` 是项目内兼容变量名但值指向 R2；`MINIO_PUBLIC_URL` 继续留空，`R2_PUBLIC_DOMAIN` 使用已验证的新对象公网域名。Web owner 视频结果接口只在 R2 公网 URL 可解析时返回成功，若临时清空 `R2_PUBLIC_DOMAIN`，视频任务可能在 99% / `pending_result` 等待结果 URL。

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
从本地主服务器同步代码后，在云端执行：

```bash
ssh allbot-do-sgp1-control
cd /home/deploy/APP/All_bot
./scripts/safe_deploy_cloud_test.sh
```

脚本执行顺序：
1. 校验 `CLOUD_TEST_DATABASE_URL`、`CLOUD_TEST_REDIS_URL`、`CLOUD_TEST_WORKER_REDIS_URL`。
2. 构建 Central API、Web API、Dashboard Backend 镜像。
3. 检查 Alembic 只有一个 head。
4. 初始化或迁移云测试数据库。
5. 重启控制面服务与 imgproxy。
6. 校验 Central API、Web API、Dashboard API 健康检查。

启动测试 Bot：

```bash
docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml \
  --profile bot up -d bot-test
```

切换前先在本地主服务器停止本地测试栈但保留数据：

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
  -> /api/ 反代到云端 Web API http://100.107.220.127:8001
```

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

### 4.1 DigitalOcean 托管 PostgreSQL 候选库
2026-06-06 已创建 DigitalOcean SGP1 托管 PostgreSQL 候选集群，用于云测试闭环、正式库迁移演练与后续生产切换评估。

非敏感连接与规格信息：

```text
Cluster: allbot-pg-sgp1-01
Engine: PostgreSQL 18
Edition: Standard
Configuration: Primary only
Region: SGP1
VPC: default-sgp1 / 10.104.0.0/20
RAM: 2 GB
CPU: 1 vCPU
Disk: 30 GiB
Monthly cost: $30.45
User: doadmin
Host: allbot-pg-sgp1-01-do-user-38256221-0.j.db.ondigitalocean.com
Port: 25060
Default database: defaultdb
SSL mode: require
```

密码、CA 证书和完整 `DATABASE_URL` 只允许写入 `.env.cloud.test`、云端受控 secret/env 文件或本地密码管理器，不得写入仓库文档。当前本地正式库与云测试容器均为 PostgreSQL 15，目标托管库为 PostgreSQL 18；迁移正式数据前必须完成 `pg_dump`/`pg_restore` 恢复演练、Alembic head 校验和应用健康检查。

云测试服务必须通过 `.env.cloud.test` 显式设置 `CLOUD_TEST_DATABASE_URL` 连接托管 PostgreSQL；`web-api-test`、`dashboard-backend-test`、`bot-test` 均使用该连接串。该变量必须使用 `postgresql+asyncpg://...` 格式，DigitalOcean 托管库连接需追加 `?ssl=require`。

2026-06-06 云测试数据库迁移结果：
- 已在托管 PostgreSQL 集群中创建 `bot_db_test`。
- 已从云端容器库 `cloud-postgres-test` 导出 `bot_db_test` 并恢复到托管库；迁移用临时 dump 备份已在验证后清理。
- 已在云端 `.env.cloud.test` 写入 `CLOUD_TEST_DATABASE_URL`，连接串不进入仓库文档。
- 已执行 `alembic upgrade head` 与基础种子数据同步。
- 已重建 `cloud-web-api-test`、`cloud-dashboard-backend-test`、`cloud-tg-bot-test`；应用侧验证数据库为 `bot_db_test`，PostgreSQL server version 为 `180004`，`users` 表记录数为 203。
- 已从 compose 中移除容器版 Postgres；云端 `cloud-postgres-test` 容器、`postgres:15` 镜像与 `deploy_cloud-postgres-test-data` volume 均已删除。当前测试服务的事实数据库为 DigitalOcean 托管 PostgreSQL。

## 5. 服务与端口
所有服务端口默认绑定到云主机 `127.0.0.1`。配置 `CLOUD_TEST_BIND_IP=<云服务器 Tailscale IPv4>` 后，测试入口端口会绑定到 Tailscale IP，不直接暴露公网。

| 服务 | 容器名 | 本机端口 | 用途 |
| :--- | :--- | :--- | :--- |
| Central API | `cloud-central-api-test` | `8004` | 任务控制面 API，本地 cloud-worker 访问 |
| Web API | `cloud-web-api-test` | `8001` | Web BFF / 主 API |
| Dashboard Backend | `cloud-dashboard-backend-test` | `8044` | Dashboard 后端 |
| imgproxy | `cloud-imgproxy-test` | `8084` | 图片代理 |

云测试缓存与队列不再使用云端容器版 Redis，事实源为 DigitalOcean Managed Caching for Valkey：

```text
Cluster: allbot-valkey-sgp1-01
Engine: Valkey 8
Region: SGP1
Configuration: Primary only
RAM: 1 GB
CPU: 1 vCPU
Disk: 10 GiB
Eviction policy: noeviction
REDIS_URL: DB 3
WORKER_REDIS_URL: DB 4
```

Tailscale 主链路验证：

```bash
curl -fsS http://<云服务器 Tailscale IPv4>:8004/health
./scripts/start_cloud_worker_test.sh
```

VS Code Remote 或本地 SSH 仍可通过端口转发作为应急访问：

```bash
ssh -N \
  -L 8001:127.0.0.1:8001 \
  -L 8044:127.0.0.1:8044 \
  -L 8004:127.0.0.1:8004 \
  allbot-do-sgp1-control
```

## 6. 验证命令
```bash
cd /home/deploy/APP/All_bot
docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml ps
curl -fsS http://127.0.0.1:8004/health
curl -fsS http://127.0.0.1:8001/api/health
curl -fsS http://127.0.0.1:8044/api/health
docker stats --no-stream
df -h /
```

2026-06-06 首次部署验证结果：
- Central API、Web API、Dashboard API 健康检查通过。
- 空载控制面容器合计内存约 0.8GB。
- Droplet 根分区约 154GB，首次构建后已用约 8.9GB。

2026-06-06 R2 切换验证结果：
- 本地测试 MinIO 历史对象已镜像到 R2 `user-data-test` 桶根路径：`bot-data-test` 约 1.10GiB，`comfyui-temp-test` 约 749.91MiB，`bot-template-test` 为空。
- 历史样本 key `242/output_images/01c4cd38-e7e9-4587-90e2-f5d15c7a1147.mp4` 在 R2 S3 API 中 HEAD 成功。
- 云端 Web API 容器实际生效：`MINIO_ENDPOINT=<R2 endpoint host>`、`MINIO_BUCKET=user-data-test`、`MINIO_SECURE=true`、`MINIO_PUBLIC_URL=`、`R2_PUBLIC_DOMAIN=https://r2-test.aivison.it.com`。
- 云端 Web API 使用 R2 预签名 URL 读写烟测通过，预签名 host 为 R2 S3 endpoint，读取状态 200。
- `https://r2-test.aivison.it.com` 已验证可读取新写入 Web 视频结果，例如 `history/<task_id>/original.mp4` 返回 200；云测试 Web owner 视频结果依赖该公网域名完成 `/api/tasks/{task_id}/result` 成功态返回。
- R2 `user-data-test` 已配置 Web 直传 CORS，允许 `https://web-test.aivison.it.com` 与 `https://web.aivison.it.com` 执行 `GET/PUT/HEAD`；`OPTIONS` 预检返回 204，实际预签名 `PUT` 上传与 `HEAD` 验证均返回 200。

2026-06-06 边缘测试 Web 切换验证结果：
- `frontend npm run deploy:edge-test` 已将当前测试前端静态资源同步到 `web` VPS `/root/dist-test`。
- VPS Nginx `web-test.aivison.it.com` 已备份原配置，并将 `/api/` upstream 从本地主服务器测试 API 改为云端 `http://100.107.220.127:8001`。
- `nginx -t` 通过并已 reload。
- `https://web-test.aivison.it.com` 返回 200，`https://web-test.aivison.it.com/api/health` 返回云端 Web BFF `{"status":"ok","message":"Web BFF is running"}`。

2026-06-06 云端测试容器瘦身结果：
- 已从 compose 中移除 `postgres-test`、`minio-test`、`minio-init`、`payment-api-test`、`web-frontend-test`、`dashboard-frontend-test` 及其 volumes；云端已删除旧 Postgres volume、MinIO/Node/Payment 可选镜像与 build cache。
- 云端保留核心容器：Central API、Web API、Dashboard Backend、imgproxy、bot-test。公网测试 Web 入口使用边缘 VPS 静态站。
- Dashboard Backend 仅供少量管理员使用，云测试连接池显式压缩为 `DB_POOL_SIZE=1`、`DB_MAX_OVERFLOW=2`；当前 2 个 gunicorn worker 的 Dashboard 数据库连接上限为 6，避免空闲连接占用托管库连接额度。

2026-06-06 云测试 Valkey 切换结果：
- 已创建 DigitalOcean Managed Caching for Valkey `allbot-valkey-sgp1-01`，规格为 1GB RAM / 1vCPU / 10GiB Disk / Primary only / SGP1 / Valkey 8。
- eviction policy 选择 `noeviction`，避免任务队列、锁、heartbeat 或 pending finalizer 被自动淘汰。
- 云测试 `.env.cloud.test` 中 `CLOUD_TEST_REDIS_URL` 指向 DB 3，`CLOUD_TEST_WORKER_REDIS_URL` 指向 DB 4。
- 云测试 compose 已移除 `redis-test` 服务和 `cloud-redis-test-data` volume；云端旧 `cloud-redis-test` 容器与 `deploy_cloud-redis-test-data` volume 已删除。
- Dashboard Backend 使用项目 `config.py`，`BOT_TYPE=TEST` 时必须显式设置 `DATABASE_URL_TEST` 与 `REDIS_URL_TEST`，否则 `.env.cloud.test` 里的旧测试变量会覆盖 compose 中的 `DATABASE_URL`/`REDIS_URL`。
- Dashboard Backend 启动时若遇到 DigitalOcean 托管 PostgreSQL DNS 短暂解析失败，`dashboard/backend/main.py` 会对 `init_db()` 做启动期短重试，并在启动完成后继续后台重试修复健康状态；Dashboard `/api/health` 返回 503 且 `database_error` 为 DNS 错误时，优先核对 `DATABASE_URL_TEST`/PostgreSQL DNS/Trusted sources，不要误判为 Valkey 故障。

## 7. Tailscale 接入边界
- 本地主服务器已安装 Tailscale；云服务器需安装 Tailscale 并加入同一 tailnet。
- 推荐给云服务器使用 `tag:allbot-cloud-test`，并用 ACL 只放行本地主服务器访问云测试端口。
- 当前不使用 subnet router，不把武汉家庭内网 `192.168.1.0/24` 暴露给云端。
- 云端 PostgreSQL 与 Valkey 均使用 DigitalOcean 托管服务，Trusted sources 只允许云 Droplet/VPC 访问，不向公网开放。
- 若 Tailscale 不可用，可临时回退 SSH `-L` 转发，但不作为长期 worker 链路。

## 8. Bot Profile

`bot-test` profile 默认禁止启动。只有确认本地主服务器上的 `tg-bot-test` 已停止，且测试 token 不会双实例冲突时，才允许手动启动：

```bash
docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml \
  --profile bot up -d bot-test
```

云测试 `bot-test` 默认设置 `TON_PAYMENT_POLLING_ENABLED=false`，避免空云测试库启动后回扫真实 TON 商户地址的历史交易并污染测试订单/用户数据。只有需要专门联调 TON 支付履约时，才在 `.env.cloud.test` 中显式设置 `CLOUD_TEST_TON_PAYMENT_POLLING_ENABLED=true`，并先确认测试库 checkpoint 与通知目标可控。

GPU worker 不在云服务器运行；本地 `workers/docker-compose-cloud-worker-test.yml` 会启动 7 个 `cloud-comfy-agent-test-*` 容器，经 Tailscale 连接云端 Central API，并通过 R2 S3 endpoint 直接读写 `user-data-test`。

## 9. 回滚
回滚到本地主服务器测试栈：

```bash
docker-compose --env-file .env.cloud.test -f workers/docker-compose-cloud-worker-test.yml stop
ssh allbot-do-sgp1-control 'cd /home/deploy/APP/All_bot && docker compose --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml --profile bot stop bot-test'
docker-compose --env-file .env.test -f deploy/docker-compose-test.yml start
docker-compose --env-file .env.test -f backend/docker-compose-test.yml start
docker-compose --env-file .env.test -f workers/docker-compose-test.yml start
```
