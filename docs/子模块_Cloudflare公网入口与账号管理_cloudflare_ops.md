# 子模块: Cloudflare 公网入口与账号管理 (Cloudflare Ops)

> 不可变发布约束（2026-07-14）：测试与正式 Web 必须由本地主服务器发布 CLI 使用最小 Pages token 上传同一 Web tar，仅在发布时注入版本化公开 runtime config。生产加固候选只读检查正式项目，不自动修改设置；本轮已获后续测试 Pages mutation 授权，正式 Pages 发布、custom domain 和关闭 Git 自动部署仍需单独确认。

## 1. 目标与范围

本文档记录 AllBot 在 Cloudflare 上的账号级自动化、DNS、Tunnel、Access、Pages/R2 与公网管理入口的操作边界。它承接原网络文档中的 Cloudflare 细节；网络拓扑仍见 `docs/子模块_网络暴露与代理穿透_network_proxy.md`。

本文只记录非敏感 ID、域名、路径和 SOP。Cloudflare API token、Tunnel token、R2 secret、Access JWT、`.env` 和数据库 URL 不得进入 Git、文档、日志或聊天。

## 2. 当前账号事实

| 项目 | 当前值 |
| :--- | :--- |
| Account ID | `c7220eb751acc6f7ab8255b4a0394ef3` |
| Zone | `aivison.it.com` |
| Zone ID | `649f8ae1847d99655e1f3ccdbddc5128` |
| Access team domain | `chuzeyu.cloudflareaccess.com` |
| 当前 Access IdP | One-time PIN |
| 当前管理员 allowlist | `cv1347968277@gmail.com` |
| 自动化 token 主文件 | `/home/hfy/.cloudflare/allbot-cloudflare-admin.token` |
| 本地分析兼容 token 路径 | `/home/hfy/.cloudflare/allbot-local-analytics.token`，指向主文件的 symlink |
| Pages 发布 token | `/home/hfy/.config/allbot/cloudflare-pages.token`，仅 Pages Read/Write |
| token 文件权限 | 目录 `700`，文件 `600` |

2026-07-05 已将聊天中暴露过的旧 `allbot-local-analytics` token 禁用；本机主文件已轮换为新的 Cloudflare 自动化 token。2026-07-14 实测该 Account Token 可访问 DNS/Tunnel，但 Pages projects 和 token-management API 返回 403；它不能用于 Web 发布。独立 Pages token 已按 `600` 保存并通过 projects API 200 验证。任何出现在聊天中的 token 仍必须撤销，不能写入知识库或凭据文件。

## 3. 当前公网入口

| 域名 | Cloudflare 承接 | 当前回源/用途 | 保护要求 |
| :--- | :--- | :--- | :--- |
| `web.aivison.it.com` | Pages `allbot-web-prod` | 正式 Web 静态站 | Pages/Git 发布门禁 |
| `web-cf-test.aivison.it.com` | Pages `allbot-web-cf-test` | 不可变发布测试 Web；运行时配置指向测试 API/Bot/R2 | Pages 发布门禁，不指向正式 API |
| `r2-test.aivison.it.com` | R2 custom domain / `user-data-test` | 云测试结果公开读路径；浏览器上传仍使用 R2 S3 预签名 URL | 桶 CORS 必须覆盖当前测试 Pages Origin |
| `api-cf-test.aivison.it.com` | Tunnel `allbot-cloud-web-api-canary` / `6d129e6e-8f4a-4003-b0bc-60565910b2b9` | 云测试 Web API `http://100.82.124.91:8001` | 2026-07-14 已从错误的正式回源修正为测试回源 |
| `api.aivison.it.com` | Tunnel `allbot-cloud-web-api` / `07da3d9e-c610-41c8-ac71-71da8753a46e` | 云正式 Web API `http://100.107.220.127:8000` | Web API 自身鉴权，不启用 Access 登录页 |
| `rmb.aivison.it.com` | Cloudflare Tunnel | 不可变云正式 Payment API `http://100.107.220.127:8002` | 支付回调/结果页语义，切换走 RMB 脚本；`service` 与 `originRequest.httpHostHeader` 必须同步使用 `8002` |
| `worker-central.aivison.it.com` | Cloudflare Tunnel | RunPod 专用 Central | 不启用 Access 登录页；依赖 agent secret 与 WAF/rate limit |
| `worker-central-test.aivison.it.com` | Cloudflare Tunnel | 云测试 worker 专用 Central | 不启用 Access 登录页；依赖测试 agent secret |
| `qqcc-admin-test.aivison.it.com` | Tunnel `allbot-cloud-web-api-canary` / `6d129e6e-8f4a-4003-b0bc-60565910b2b9` + Access app `qqcc-admin-test` / `93c6a382-dcf5-498e-b702-6a21184fb753` | 云测试 QQCC Config Frontend `http://100.82.124.91:8088` | Access policy `qqcc-test-admin` / `4d1990fd-0c4f-45eb-8f2b-eeecf2b3d717` 仅允许 `cv1347968277@gmail.com` |
| `admin-test.aivison.it.com` | Tunnel `allbot-cloud-web-api-canary` + Access | 云测试 Dashboard Frontend `http://100.82.124.91:8086` | 仅允许管理员邮箱，并保留 Dashboard 应用登录 |
| `qqcc-admin.aivison.it.com` | Tunnel `allbot-admin-dashboard-prod` / `68599b55-d7f9-4e0c-9613-3d5fa396cb28` + Access app `qqcc-admin` / `7fbb3a9a-7156-46b5-857c-1b7e5d97c7fe` | QQCC 懒人 Bot 管理后台公网入口 | Access policy `qqcc` allow `cv1347968277@gmail.com` |
| `private-bot.aivison.it.com` | Tunnel `allbot-admin-dashboard-prod` / `68599b55-d7f9-4e0c-9613-3d5fa396cb28`，DNS record `69c4e68bf442dea05fefa71db28791b5` | QQCC 私有 Bot owner WebApp，回源 `http://100.107.220.127:8088` | 面向 owner 公开，不创建 Access app；应用层 ticket/JWT + 双层 Host 隔离 |
| `analytics.aivison.it.com` | Tunnel `allbot-local-analytics` / `79d456a9-6448-4677-8a1f-c128ffb256dd` + Access app `local-analytics` / `b05ae46f-fcdb-43d9-ac4e-50ab91daabac` | 本地主服务器只读分析平台 `http://127.0.0.1:8098` | Access policy `local-analytics-admin` allow `cv1347968277@gmail.com` + 应用层登录 |

2026-07-14 已关闭 `allbot-web-cf-test` Git integration 的 production 自动部署，并把 preview branch control 设置为 `none`；当前内容保持不变，后续只接受 release CLI 校验同一 tar 后的 Wrangler 上传。`allbot-web-prod` 未在本轮修改。

同日已为 `user-data-test` 桶补齐不可变 Pages 测试站直传 CORS。当前允许的 Origin 为 `https://web.aivison.it.com`、`https://web-cf-test.aivison.it.com`、`https://allbot-web-cf-test.pages.dev`，方法为 `GET/PUT/HEAD`，允许任意请求头并暴露 `ETag`。桶 CORS 变更需要具备 R2 Storage Write 管理权限；对象读写 key 即使能上传，也可能无权读取或修改桶 CORS，必须按目标 API/操作实测能力，且不得回显凭据。

2026-07-16 已为云测试 QQCC Config Web 上线 `qqcc-admin-test.aivison.it.com`。该 hostname 插入 `allbot-cloud-web-api-canary` Tunnel 的 catch-all 404 之前，回源测试 Tailscale origin `http://100.82.124.91:8088`；proxied CNAME DNS record 为 `4d257ea98980b057d8d2ef15a2063fdb`。公网未登录请求已验证返回 Cloudflare Access 302，Access allow policy 只允许 `cv1347968277@gmail.com`，应用层 QQCC Config 登录继续保留。测试私有 Bot 总 gate 仍关闭，因此本轮没有创建 `private-bot-test.aivison.it.com` DNS、Tunnel ingress 或公开 Owner WebApp。

正式 Pages 使用 catalog 的 `public-web` 模块。从完整 main SHA 构建环境中立
artifact 后，以精确 `repository@sha256:digest` 调用 `release.py deploy
--env prod --module public-web ... --confirm-prod`。Pages adapter 在 mutation
前只读确认 production branch 为 `main`、自动 production/preview 部署关闭、
正式 custom domain active，并保存当前 canonical deployment 作为 previous；
任何一项不满足都只报告失败，不自动 PATCH 项目设置。

Wrangler 上传成功不等于正式域已切换。发布器随后通过 Pages API锁定 `environment=production`、branch=`main`、commit hash 等于目标完整 SHA、latest stage success 的 deployment ID，要求项目 `canonical_deployment.id` 指向它，并从 `https://web.aivison.it.com/allbot-runtime-config.js?release_sha=<sha>` 校验 JavaScript 内的 `release_sha` 与 `runtime_config_revision`。后续阶段失败时，事务恢复调用官方 `POST /accounts/{account_id}/pages/projects/{project_name}/deployments/{deployment_id}/rollback` 恢复旧 production deployment，并再次核对 canonical ID；rollback API 或 canonical 验证失败时必须保持生成维护。

QQCC 私有 Bot owner WebApp Host 由 `PRIVATE_QQCC_BOT_OWNER_HOST` / `PRIVATE_QQCC_BOT_OWNER_WEBAPP_URL` 提供。2026-07-12 已在现有 `allbot-admin-dashboard-prod` Tunnel 的 catch-all 404 前新增 `private-bot.aivison.it.com -> http://100.107.220.127:8088`，并创建 proxied CNAME；该 Host 明确没有 Access app。上线后已验证 owner 首页 200、未认证 owner API 401、owner Host 上管理员 API与 `/api/health` 404，原 `qqcc-admin` 公网入口仍返回 Access 302。

该 owner Host 面向普通 owner 公开，不能套用只允许管理员邮箱的 QQCC Admin Access policy，否则 Telegram WebApp 用户无法兑换 ticket。应用层使用 5 分钟单次 ticket + 12 小时 owner JWT；Nginx 通过 `PRIVATE_QQCC_BOT_OWNER_HOST` 只允许 owner 页面和 `/api/private-bots/owner/**`，管理员及其它 API 返回 404，backend 还会再次按 owner/admin Host 对跨 Host API 返回 404。owner 页不发送 `X-Frame-Options`，CSP 的 `connect-src` 只允许 `'self'`，仅以 `frame-ancestors 'self' https://*.telegram.org https://telegram.org` 允许 Telegram WebView 嵌入；admin/unknown Host 继续 `DENY` + `frame-ancestors 'none'`。ticket exchange 使用独立 `50r/s`、`burst=500`、`nodelay` limiter，以适应 cloudflared 汇聚的 origin 地址，不复用 admin login 的 `2r/s`、`burst=5` 窄桶。管理员入口由独立 `QQCC_CONFIG_ADMIN_HOST` 匹配，`qqcc-admin.aivison.it.com` 必须继续由现有 Access allowlist 保护；未知 Host 的 default server 直接 404。Tunnel 常从 localhost 回源，因此 Host/应用鉴权是权威边界，源 IP allowlist 只能作为附加防护。Telegram webhook 复用 `api.aivison.it.com/api/private-bots/webhook/<public_id>`，不启用 Access 登录页，依赖不可预测 public ID、Telegram secret header、状态校验、Redis 去重和边缘限流。

`analytics.aivison.it.com` 的本机配置：

| 项目 | 当前值 |
| :--- | :--- |
| Tunnel 配置 | `/home/hfy/.cloudflared/allbot-local-analytics.yml` |
| Tunnel 凭据 | `/home/hfy/.cloudflared/allbot-local-analytics.json`，权限 `600` |
| 用户级 systemd | `/home/hfy/.config/systemd/user/cloudflared-local-analytics.service` |
| 应用登录 env | `local_analytics_platform/.env`，权限 `600`，Git 忽略 |
| 应用管理员密码 | `/home/hfy/.local-analytics-platform/admin-password.txt`，权限 `600` |

当前 `cloudflared-local-analytics.service` 是用户级 systemd 服务；若 `loginctl show-user hfy -p Linger` 返回 `Linger=no`，则不能把它等同于系统级开机自启服务。需要更强韧性时，应在具备 sudo 条件后迁移为 system service 或启用 linger。

History 归档媒体可通过该受控公网入口在输入/输出单元格内预览。正文接口仍要求
应用层签名 session，边缘继续要求 Cloudflare Access；响应必须使用
`Cache-Control: private, no-store`，浏览器只获得 opaque 媒体 ID，不获得 NAS
endpoint、对象键或凭据。loopback 快照网关与 NAS 服务不得增加 public hostname。

## 4. 安全边界

- 不把 token 明文写入 `.env.cloud.*`、Compose env、systemd unit、Git、文档、日志或聊天。
- 不打印 `systemctl status cloudflared*` 的完整输出；该输出可能包含 token 或 credentials 路径上下文。排障时用 `is-active`、`journalctl` 精准 grep 非敏感错误。
- 管理/分析入口必须启用 Cloudflare Access 或等价身份层；涉及 shadow 数据、本地分析或管理后台时，还必须保留应用层登录。
- worker 专用 hostname 不启用 Access 登录页，否则会拦截机器请求；应依赖 agent secret、WAF/rate limit 和最小可见 API。
- QQCC owner public Host 与 admin Host 必须按 Host 分离：公开 Host 不得反代 `/api/private-bots/admin/**`、`/api/qqcc/**` 或通用管理员 API；管理员 Host 不得因为 owner WebApp 上线而移除 Access。
- Cloudflare mutation 前必须先读当前 DNS、Access app/policy、Tunnel 和 origin 健康状态；不要直接覆盖。
- R2 lifecycle mutation 必须先读回完整当前规则并保留非目标项。生产临时区
  只允许 `staging/` 前缀 1 天过期，不得用全桶过期或扩展到任何持久前缀。
  不使用 `user-data-test` 验证生产 lifecycle，不修改 `allbot-model-cache`。
- Token 轮换先验证新 token，再禁用旧 token；聊天中出现过的 token 一律视为泄露。

## 5. Token 使用与验证

只在单条命令内读取 token，命令结束后 unset：

```bash
CF_API_TOKEN="$(tr -d '\r\n' < /home/hfy/.cloudflare/allbot-cloudflare-admin.token)"
CF_ACCOUNT_ID="c7220eb751acc6f7ab8255b4a0394ef3"
CF_ZONE_ID="649f8ae1847d99655e1f3ccdbddc5128"

curl -fsS -H "Authorization: Bearer ${CF_API_TOKEN}" \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/apps?per_page=100" \
  | jq -r '.result[] | [.name, .domain, .id] | @tsv'

curl -fsS -H "Authorization: Bearer ${CF_API_TOKEN}" \
  "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records?per_page=100" \
  | jq -r '.result[] | [.name, .type, .content, (.proxied|tostring)] | @tsv'

curl -fsS -H "Authorization: Bearer ${CF_API_TOKEN}" \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/cfd_tunnel?per_page=100" \
  | jq -r '.result[] | [.name, .id, .created_at] | @tsv'

unset CF_API_TOKEN
```

`cfat_` Account-owned token 应使用 `/accounts/${CF_ACCOUNT_ID}/tokens/verify` 验证；不要使用 `/user/tokens/verify`，后者会把有效的账户级 token 报成 `Invalid API Token`。本项目还必须以目标 API 只读探测成功确认实际权限。若某个 API 返回 403，应先核对 account ID 与 token 权限是否覆盖该产品，不要把 403 误判为 Cloudflare 服务异常。

## 6. 新增受保护公网入口 SOP

1. 明确入口用途、数据敏感级别、origin 地址、健康检查和是否已有应用层认证。
2. 若是管理后台、本地分析、配置后台，先启用应用层登录或确认已有独立后台账号。
3. 创建或复用 Cloudflare Tunnel；credentials 文件放在宿主机受限目录，权限 `600`。
4. 配置 public hostname 回源到最小 origin 地址，例如本地分析的 `http://127.0.0.1:8098` 或 Tailscale IP，不回源到 `0.0.0.0` 裸端口。
5. 创建 proxied DNS CNAME 指向 `<tunnel-id>.cfargotunnel.com`。
6. 创建 Access app 与 allow policy，默认只允许 `cv1347968277@gmail.com`。
7. 验证公网未登录访问先 302 到 Access；Access 通过后再进入应用层登录或应用页面。
8. 同步更新本文件、网络文档、对应业务文档、`AGENTS.md`/Skill 路由和知识库矩阵。

## 7. 本地分析公网入口恢复

本地主服务器侧检查：

```bash
systemctl --user is-active cloudflared-local-analytics.service
loginctl show-user hfy -p Linger
curl -fsS http://127.0.0.1:8098/api/health
curl -sS http://127.0.0.1:8098/api/auth/session
```

公网检查：

```bash
curl -I https://analytics.aivison.it.com
```

未登录时应返回 Cloudflare Access 跳转，目标域包含 `chuzeyu.cloudflareaccess.com`。Access 通过后应进入本地分析平台 `/login`，而不是直接看到数据页。

如果 tunnel 服务异常，先读取非敏感状态：

```bash
systemctl --user is-active cloudflared-local-analytics.service
journalctl --user -u cloudflared-local-analytics.service --since "10 min ago" --no-pager
```

日志里若包含 token、credentials 或完整 connector 命令，不要复制到聊天或文档。

## 8. Token 轮换 SOP

1. 在 Cloudflare 控制台创建新 token，权限按当前任务选择；若要作为总管自动化 token，应至少验证 DNS、Access、Tunnel 和目标 Pages/R2 API。
2. 在本机写入主文件并限制权限：

```bash
install -d -m 700 /home/hfy/.cloudflare
install -m 600 /dev/null /home/hfy/.cloudflare/allbot-cloudflare-admin.token
# 手工粘贴 token 后立即确认权限；不要把 token 写入命令历史。
chmod 600 /home/hfy/.cloudflare/allbot-cloudflare-admin.token
ln -sfn /home/hfy/.cloudflare/allbot-cloudflare-admin.token /home/hfy/.cloudflare/allbot-local-analytics.token
```

3. 执行第 5 节只读探测，确认新 token 可用。
4. 禁用旧 token，尤其是曾经出现在聊天或截图里的 token。
5. 扫描仓库确认没有当前 token 明文：

```bash
token="$(tr -d '\r\n' < /home/hfy/.cloudflare/allbot-cloudflare-admin.token)"
rg --hidden --follow -S -q -f <(printf '%s\n' "$token") /home/hfy/APP/All_bot \
  --glob '!**/.git/**' \
  --glob '!**/node_modules/**' \
  --glob '!**/.venv/**' \
  --glob '!**/venv/**' \
  --glob '!**/__pycache__/**'
unset token
```

该命令无输出且退出码为 1 表示未匹配到明文。

## 9. 变更与回滚

- 删除或停用公网入口前，先确认没有用户、worker、支付回调、管理后台或自动化依赖该域名。
- Access app/policy 删除前，记录域名、app ID、policy ID 和当前 allowlist；不要记录 token。
- Tunnel 删除前，先停对应 connector，再删除 DNS CNAME，最后删除 tunnel 资源，避免保留悬空公网域名。
- 本地分析公网入口回滚可先停用户级 service 或临时禁用 DNS/Access app，但不要删除本地应用登录、shadow 数据或 token 主文件。
- 正式 Web/API/RMB 回源变化按云正式和网络文档执行，不在 Cloudflare 控制台里自由手改多处。

## 10. 文档维护

以下变化必须同步更新本文档、`docs/子模块_网络暴露与代理穿透_network_proxy.md`、相关业务文档、`.codex/skills/allbot-cloudflare-ops/SKILL.md` 和 `docs/knowledge_base_audit_matrix.md`：

- 新增、删除或改名 Cloudflare zone、Pages 项目、Tunnel、public hostname、Access app/policy。
- `analytics.aivison.it.com`、`qqcc-admin.aivison.it.com`、`api.aivison.it.com`、`rmb.aivison.it.com`、worker-central 或测试入口回源变化。
- Cloudflare token 路径、权限、轮换状态或禁用状态变化。
- Access allowlist、IdP、MFA/OTP 策略变化。
- 管理/分析入口从 Tailscale 迁到公网，或从用户级 cloudflared 迁到系统级 service。
