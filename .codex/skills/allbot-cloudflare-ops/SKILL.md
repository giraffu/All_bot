---
name: "allbot-cloudflare-ops"
description: "处理 AllBot Cloudflare 账号自动化、API Token、DNS、Tunnel、Access、Pages、R2 与公网管理域名配置。配置或排障 Cloudflare 公网入口、本地分析平台/管理后台公网访问、Token 轮换、Access allowlist、Tunnel public hostname 时必须调用本技能。"
---

# AllBot Cloudflare Ops

本技能是 Cloudflare 操作的短入口。账号事实、当前公网配置和 SOP 以专项文档为准；技能正文只保留路由、红线和最小验证。

## 1. 必读入口

按任务只读必要资料：

| 场景 | 必读资料 |
| :--- | :--- |
| Cloudflare token、DNS、Tunnel、Access、Pages/R2 管理 | `docs/子模块_Cloudflare公网入口与账号管理_cloudflare_ops.md` |
| 公网入口拓扑、Tailscale、Nginx/VPS、灾备回源 | `docs/子模块_网络暴露与代理穿透_network_proxy.md` |
| 本地数据分析平台公网入口 | `docs/子模块_本地数据分析平台_local_analytics_platform.md` |
| 云正式 Web/API/RMB/worker tunnel | `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`、`allbot-ops-deployment` |
| Pages 发布、边缘 VPS、legacy 静态回滚 | `docs/子模块_边缘节点运维指南_edge_node_ops.md` |

若操作会改变生产公网入口、Access 策略、DNS、Tunnel 回源或 Pages 发布，叠加 `allbot-ops-deployment`。若更新 docs/skills，叠加 `allbot-kb-auto-updater`。

## 2. 稳定事实

- Cloudflare 自动化令牌主文件：`/home/hfy/.cloudflare/allbot-cloudflare-admin.token`；兼容链接：`/home/hfy/.cloudflare/allbot-local-analytics.token`。
- 令牌值不得出现在聊天、文档、Git、日志、`systemctl status` 输出、`docker compose config` 输出或 shell history 中。
- 当前 zone 为 `aivison.it.com`；账号、zone、Access、Tunnel 的非敏感 ID 记录在 Cloudflare 专项文档中。
- `analytics.aivison.it.com` 当前通过本地主服务器用户级 `cloudflared-local-analytics.service` 回源 `http://127.0.0.1:8095`，并由 Cloudflare Access + 本地应用登录双层保护。
- `qqcc-admin.aivison.it.com` 是现有受保护管理入口参考基线：Cloudflare Access allow policy 只允许 `cv1347968277@gmail.com`。
- `private-bot.aivison.it.com` 已于 2026-07-12 通过 `allbot-admin-dashboard-prod` Tunnel 正式上线，公开回源 QQCC Config Frontend `100.107.220.127:8088`；它不创建 Access app，依赖 owner ticket/JWT 与 origin/backend 双层 Host 隔离。`qqcc-admin.aivison.it.com` 仍由原 Access app 独立保护。
- Cloudflare Account-owned token 不适合用 `/user/tokens/verify` 作为唯一验证；以 DNS、Zero Trust Access、Tunnel、Pages/R2 目标 API 的只读探测结果为准。

## 3. 操作红线

- 未经用户明确要求，不创建、修改或删除公网 DNS、public hostname、Access app/policy、Tunnel、Pages custom domain 或 R2 bucket policy。
- 不把本地分析 `8095`、Dashboard `8086/8043`、QQCC Config `8088/8045`、数据库、Redis、MinIO 管理端口裸露到公网。公网管理/分析入口必须有 Cloudflare Access 或等价身份层，且敏感数据服务还要保留应用层登录。
- Token 轮换必须先写新文件、`chmod 600`、只读验证新 token，再禁用旧 token；聊天中出现过的 token 视为已泄露，必须尽快替换或禁用。
- Cloudflare Access 策略默认用管理员邮箱 allowlist；扩大到组织/域名/所有人前必须向用户确认风险。
- worker / RunPod 专用 Central hostname 不启用会拦截机器请求的 Access 登录页；它们依赖 agent secret 和 WAF/rate limit。
- 用户级 cloudflared service 受登录会话和 linger 影响；没有 sudo 或未启用 linger 时，不声称已经具备系统级开机自启韧性。
- QQCC owner Host 面向普通 owner，不套管理员邮箱 Access allowlist；它依赖应用层单次 ticket/JWT，且 origin Nginx 只能放行 owner 页面/API，backend 还要再次按 Host 对跨域 owner/admin API 返回 404。owner 不发送 XFO，CSP 的 `connect-src` 只能 `'self'`，仅 `frame-ancestors 'self' https://*.telegram.org https://telegram.org` 允许 Telegram WebView。admin Host 必须显式独立、继续 Access 保护，admin/unknown 保持 `DENY` + `frame-ancestors 'none'`，unknown Host 必须在 origin 404；Tunnel localhost 回源不能让 source IP allowlist 成为唯一隔离。Owner ticket exchange 使用独立 `50r/s`、`burst=500` limiter，不能复用 admin login 的 `2r/s`、`burst=5` 窄桶。Owner API body limit 要按路径保持 4KiB ticket/credentials、1MiB config、55MiB demo-media，不能全局放大。Telegram webhook API Host 也不能启用浏览器登录页。

## 4. 标准流程

### 只读探测

1. 从 token 文件读取到局部变量，命令结束后 `unset CF_API_TOKEN`。
2. 先列出目标 DNS record、Access app/policy、Tunnel 和 public hostname，再判断是否需要 mutation。
3. 输出只记录非敏感 ID、域名、状态和权限边界，不输出 token、connector install token、tunnel credentials 或完整 systemd status。

### 新增受保护公网入口

1. 先确认本地/云端 origin 已有自己的认证、健康检查和端口绑定边界。
2. 创建或复用 Cloudflare Tunnel，并把凭据保存到受限权限文件。
3. 创建 proxied DNS CNAME 指向 `<tunnel-id>.cfargotunnel.com`。
4. 创建 Access app 与 allow policy，管理/分析入口默认只允许 `cv1347968277@gmail.com`。
5. 验证未登录公网访问先跳 Cloudflare Access，Access 通过后再进入应用登录或应用页面。
6. 同步更新 Cloudflare 专项文档、网络文档、对应业务文档和知识库矩阵。

### Token 轮换

1. 确认旧 token 是否出现在聊天、日志或文件中。
2. 写入新 token 到 `/home/hfy/.cloudflare/allbot-cloudflare-admin.token`，目录 `700`、文件 `600`；兼容路径用 symlink，不复制明文。
3. 用 DNS/Access/Tunnel API 只读探测验证新 token。
4. 禁用旧 token，记录 token 名称、用途和禁用结论，不记录明文。
5. 用精确 token 扫描仓库，确认没有明文落盘。

## 5. 最小验证

常用验证命令见 `docs/子模块_Cloudflare公网入口与账号管理_cloudflare_ops.md`。交付时至少说明：

- 读到的目标 DNS/Access/Tunnel 当前状态。
- 是否执行了 mutation；若执行，列出域名、Access app/policy、Tunnel、DNS record 的非敏感 ID。
- 公网未登录行为是否符合预期，例如 `curl -I https://analytics.aivison.it.com` 返回 Access 跳转。
- 本地 connector 或用户级 systemd service 是否 active。
- 是否完成文档同步和 token 明文扫描。
