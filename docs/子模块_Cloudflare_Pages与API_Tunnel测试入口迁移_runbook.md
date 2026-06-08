# 子模块: Cloudflare Pages 与 API Tunnel 测试入口迁移 Runbook

## 1. 目标

本 runbook 用于把 Web canary 从旧 Web/Nginx VPS 前置链路中拆出来：

- `web-cf-test.aivison.it.com` 由 Cloudflare Pages 承接静态前端。
- `api-cf-test.aivison.it.com` 由运行在 `allbot-do-sgp1-control` 云机上的 Cloudflare Tunnel 回源云 Web API `http://100.107.220.127:8000`。
- `assets.aivison.it.com` 本轮不迁移，继续由 Web/Nginx VPS 代理 legacy MinIO。

这是小范围人工验收入口，不切正式用户流量。

## 2. Cloudflare 人工操作暂停点

### 2.1 API Tunnel

在 Cloudflare Zero Trust 控制台：

1. 进入 `Networks` -> `Tunnels` -> `Create tunnel`。
2. 类型选择 `cloudflared`，名称使用 `allbot-cloud-web-api-canary`。
3. 复制 Cloudflare 给出的 Linux/Debian connector install 命令。命令里包含 token，不要粘贴到聊天、文档或 Git。
4. 登录云机执行该命令：

```bash
ssh allbot-do-sgp1-control
sudo cloudflared service install <Cloudflare 控制台给出的 token>
sudo systemctl status cloudflared --no-pager
```

5. 在该 tunnel 的 Public Hostname 中添加：

| 字段 | 值 |
| :--- | :--- |
| Subdomain | `api-cf-test` |
| Domain | `aivison.it.com` |
| Type | `HTTP` |
| URL | `100.107.220.127:8000` |

6. 确认 Cloudflare 控制台 connector 状态为 Healthy。

### 2.2 Pages Git 集成

在 Cloudflare Workers & Pages 控制台：

1. `Create` -> `Pages` -> `Connect to Git`。
2. 选择仓库 `giraffu/All_bot`，分支 `deploy`。
3. 项目名使用 `allbot-web-cf-test`。
4. Build settings：

| 字段 | 值 |
| :--- | :--- |
| Root directory | `frontend` |
| Build command | `npm ci && npm run build:cf-test` |
| Build output directory | `dist` |
| Environment variable | `NODE_VERSION=24` |

5. 首次 deploy 成功后，在 Pages `Custom domains` 添加 `web-cf-test.aivison.it.com`。

### 2.3 R2 CORS

如果 `user-data-prod` 或相关 R2 桶还没有放行 canary Origin，需要在 R2 bucket CORS 中加入：

| 字段 | 值 |
| :--- | :--- |
| AllowedOrigins | `https://web-cf-test.aivison.it.com` |
| AllowedMethods | `GET`, `PUT`, `HEAD` |
| AllowedHeaders | `*` |
| ExposeHeaders | `ETag` |

保留已有 `https://web.aivison.it.com` 和 `https://web-test.aivison.it.com`，不要用这次 canary 配置覆盖掉旧规则。

## 3. 我方执行与验证

Cloudflare API Tunnel healthy 后，先验证 API 入口：

```bash
curl -fsS https://api-cf-test.aivison.it.com/api/health
```

然后只热更云端 `web-api-prod` 让 CORS allowlist 生效：

```bash
ssh allbot-do-sgp1-control
cd /home/deploy/APP/All_bot
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml build web-api-prod
docker compose --env-file .env.cloud.prod -f deploy/docker-compose-cloud-prod.yml up -d --no-deps web-api-prod
```

Pages custom domain 可用后，在仓库根目录运行：

```bash
bash scripts/check_cloudflare_canary.sh
```

人工 Web 验收至少覆盖：

- 首页无白屏，静态资源 200。
- 登录态 token 能跨域调用 `api-cf-test`。
- 任务状态流正常，不被缓存或断流。
- Gallery、History、任务结果页可读。
- legacy 媒体仍通过 `assets.aivison.it.com` 读取。

## 4. 回滚与边界

- canary 失败时，删除或停用 `web-cf-test` Pages custom domain 和 `api-cf-test` public hostname 即可，不影响 `web.aivison.it.com`。
- `web.aivison.it.com`、正式 `api.aivison.it.com`、`assets.aivison.it.com` 本轮不切换。
- 不能复用本地主服务器现有 RMB tunnel 暴露 Web API；API connector 必须在云控制面机器上运行。
- 不要把 Cloudflare tunnel token、`.env.cloud.prod`、Bot token 或 R2 密钥写入文档、日志或聊天。
