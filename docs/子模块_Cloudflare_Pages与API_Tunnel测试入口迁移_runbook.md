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

2026-06-08 18:36 CST：正式 R2 桶 `user-data-prod` 已追加 `https://web-cf-test.aivison.it.com` 与 `https://allbot-web-cf-test.pages.dev`，两者的 `PUT` 预检均返回 204。

2026-06-08 19:12 CST：正式 R2 桶 `user-data-prod` 已追加 `https://allbot-web-prod.pages.dev`；`https://allbot-web-prod.pages.dev` 与 `https://web.aivison.it.com` 的 `PUT` 预检均返回 204。

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

## 5. 正式切换准备

正式切换必须在 canary 人工验收通过后单独确认；不得因为 canary 通过就自动改 `web.aivison.it.com`。

### 5.1 正式 API 域名

`api.aivison.it.com` 应作为正式 Web API 独立入口，回源同一云 Web API：

| 字段 | 值 |
| :--- | :--- |
| Hostname | `api.aivison.it.com` |
| Type | `HTTP` |
| URL | `100.107.220.127:8000` |

正式切换前必须确认旧的本地主服务器 RMB tunnel 不再承接 `api.aivison.it.com`。历史上本地 `/home/hfy/.cloudflared/config.yml` 曾配置 `api.aivison.it.com -> 127.0.0.1:8003`，若仍生效会导致正式 API 502 或误打 Central。

验证：

```bash
curl -fsS https://api.aivison.it.com/api/health
curl -sS -o /dev/null -w "%{http_code} %{time_total}\n" \
  -X OPTIONS \
  -H "Origin: https://web.aivison.it.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization,content-type" \
  https://api.aivison.it.com/api/health
```

### 5.2 正式 Pages 项目

推荐创建独立 Pages 项目 `allbot-web-prod`，不要把 canary 项目直接改名承接生产。Git 集成配置：

| 字段 | 值 |
| :--- | :--- |
| Repo | `giraffu/All_bot` |
| Branch | `deploy` |
| Root directory | `frontend` |
| Build command | `npm ci && npm run build:cf-prod` |
| Build output directory | `dist` |
| Environment variable | `NODE_VERSION=24` |

`build:cf-prod` 使用 `frontend/.env.cf-prod`：

- `VITE_API_BASE_URL=https://api.aivison.it.com/api`
- `VITE_STORAGE_URL=https://assets.aivison.it.com`
- `VITE_TONCONNECT_MANIFEST_URL=https://web.aivison.it.com/tonconnect-manifest.json`

正式 Pages 默认域 `https://allbot-web-prod.pages.dev` 必须加入 Web API CORS allowlist，用于正式自定义域切换前做登录、上传、Gallery、History 与任务状态流验收。

### 5.3 正式 Web 域名切换

只有当 `allbot-web-prod.pages.dev`、`api.aivison.it.com`、R2 上传、登录、Gallery、History、任务状态流和结果页都验证通过后，才在 Pages custom domains 添加 `web.aivison.it.com`。

回滚方式：

- 若 Pages 静态站异常：把 `web.aivison.it.com` 从 Pages custom domain 移除或把 DNS 指回 Web/Nginx VPS。
- 若正式 API 域异常：将正式 Pages 重新部署为旧 API 入口，或临时恢复 `web.aivison.it.com/api` 的 VPS 反代。
- `assets.aivison.it.com` 本阶段不迁移，继续保留在 Web/Nginx VPS，直到 legacy/R2 回填另行完成。
