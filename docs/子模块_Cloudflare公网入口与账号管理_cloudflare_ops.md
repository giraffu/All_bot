# 子模块: Cloudflare 公网入口与账号管理 (Cloudflare Ops)

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
| token 文件权限 | 目录 `700`，文件 `600` |

2026-07-05 已将聊天中暴露过的旧 `allbot-local-analytics` token 禁用；本机主文件已轮换为新的 Cloudflare 自动化 token。当前 token 的可用性以 DNS、Access、Tunnel 等目标 API 的只读探测为准；若未来需要管理 API Token 本身，必须先单独验证 token-management API 权限，不要假设所有账号能力都已覆盖。

## 3. 当前公网入口

| 域名 | Cloudflare 承接 | 当前回源/用途 | 保护要求 |
| :--- | :--- | :--- | :--- |
| `web.aivison.it.com` | Pages `allbot-web-prod` | 正式 Web 静态站 | Pages/Git 发布门禁 |
| `api.aivison.it.com` | Tunnel `allbot-cloud-web-api` / `07da3d9e-c610-41c8-ac71-71da8753a46e` | 云正式 Web API `http://100.107.220.127:8000` | Web API 自身鉴权，不启用 Access 登录页 |
| `rmb.aivison.it.com` | Cloudflare Tunnel | 云正式 Payment API `http://100.107.220.127:8021` | 支付回调/结果页语义，切换走 RMB 脚本 |
| `worker-central.aivison.it.com` | Cloudflare Tunnel | 远程 worker / RunPod 专用 Central | 不启用 Access 登录页；依赖 agent secret 与 WAF/rate limit |
| `worker-central-test.aivison.it.com` | Cloudflare Tunnel | 云测试 worker 专用 Central | 不启用 Access 登录页；依赖测试 agent secret |
| `qqcc-admin.aivison.it.com` | Tunnel `allbot-admin-dashboard-prod` / `68599b55-d7f9-4e0c-9613-3d5fa396cb28` + Access app `qqcc-admin` / `7fbb3a9a-7156-46b5-857c-1b7e5d97c7fe` | QQCC 懒人 Bot 管理后台公网入口 | Access policy `qqcc` allow `cv1347968277@gmail.com` |
| `analytics.aivison.it.com` | Tunnel `allbot-local-analytics` / `79d456a9-6448-4677-8a1f-c128ffb256dd` + Access app `local-analytics` / `b05ae46f-fcdb-43d9-ac4e-50ab91daabac` | 本地主服务器只读分析平台 `http://127.0.0.1:8095` | Access policy `local-analytics-admin` allow `cv1347968277@gmail.com` + 应用层登录 |
| `assets.aivison.it.com` | Web/Nginx VPS | legacy MinIO 人工回滚、旧外链、迁移排障 | 不作为新生成媒体主路径 |
| `web-test.aivison.it.com` | Web/Nginx VPS | 云测试静态站 + `/api/` 反代云测试 Web API | 测试环境，不指向正式 API |

`analytics.aivison.it.com` 的本机配置：

| 项目 | 当前值 |
| :--- | :--- |
| Tunnel 配置 | `/home/hfy/.cloudflared/allbot-local-analytics.yml` |
| Tunnel 凭据 | `/home/hfy/.cloudflared/allbot-local-analytics.json`，权限 `600` |
| 用户级 systemd | `/home/hfy/.config/systemd/user/cloudflared-local-analytics.service` |
| 应用登录 env | `local_analytics_platform/.env`，权限 `600`，Git 忽略 |
| 应用管理员密码 | `/home/hfy/.local-analytics-platform/admin-password.txt`，权限 `600` |

当前 `cloudflared-local-analytics.service` 是用户级 systemd 服务；若 `loginctl show-user hfy -p Linger` 返回 `Linger=no`，则不能把它等同于系统级开机自启服务。需要更强韧性时，应在具备 sudo 条件后迁移为 system service 或启用 linger。

## 4. 安全边界

- 不把 token 明文写入 `.env.cloud.*`、Compose env、systemd unit、Git、文档、日志或聊天。
- 不打印 `systemctl status cloudflared*` 的完整输出；该输出可能包含 token 或 credentials 路径上下文。排障时用 `is-active`、`journalctl` 精准 grep 非敏感错误。
- 管理/分析入口必须启用 Cloudflare Access 或等价身份层；涉及 shadow 数据、本地分析或管理后台时，还必须保留应用层登录。
- worker 专用 hostname 不启用 Access 登录页，否则会拦截机器请求；应依赖 agent secret、WAF/rate limit 和最小可见 API。
- Cloudflare mutation 前必须先读当前 DNS、Access app/policy、Tunnel 和 origin 健康状态；不要直接覆盖。
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

Account-owned token 不一定能通过 `/user/tokens/verify` 体现真实能力；本项目以目标 API 只读探测成功作为有效性判断。若某个 API 返回 403，应先判断 token 权限是否覆盖该产品，不要把 403 误判为 Cloudflare 服务异常。

## 6. 新增受保护公网入口 SOP

1. 明确入口用途、数据敏感级别、origin 地址、健康检查和是否已有应用层认证。
2. 若是管理后台、本地分析、配置后台，先启用应用层登录或确认已有独立后台账号。
3. 创建或复用 Cloudflare Tunnel；credentials 文件放在宿主机受限目录，权限 `600`。
4. 配置 public hostname 回源到最小 origin 地址，例如 `http://127.0.0.1:8095` 或 Tailscale IP，不回源到 `0.0.0.0` 裸端口。
5. 创建 proxied DNS CNAME 指向 `<tunnel-id>.cfargotunnel.com`。
6. 创建 Access app 与 allow policy，默认只允许 `cv1347968277@gmail.com`。
7. 验证公网未登录访问先 302 到 Access；Access 通过后再进入应用层登录或应用页面。
8. 同步更新本文件、网络文档、对应业务文档、`AGENTS.md`/Skill 路由和知识库矩阵。

## 7. 本地分析公网入口恢复

本地主服务器侧检查：

```bash
systemctl --user is-active cloudflared-local-analytics.service
loginctl show-user hfy -p Linger
curl -fsS http://127.0.0.1:8095/api/health
curl -sS http://127.0.0.1:8095/api/auth/session
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
