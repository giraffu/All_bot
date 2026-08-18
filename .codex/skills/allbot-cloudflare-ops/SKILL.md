---
name: "allbot-cloudflare-ops"
description: "处理 AllBot Cloudflare Token、DNS、Tunnel、Access、Pages、R2、TLS/CORS 与公网域名。用户报告域名打不开、404/502、重定向循环、证书/TLS、DNS 解析、Tunnel 回源、Access 登录、Pages 发布或 R2 公网/CORS 异常，或要求配置/轮换策略时必须使用。"
---

# AllBot Cloudflare Ops

本 Skill 只保留授权边界、事实源和安全流程。域名清单、账号/zone ID、回源地址、
allowlist、当前权限和上线记录都是易变事实，只从专项文档与 Cloudflare 只读 API
获取，不复制到 Skill。

## 1. 按需阅读

| 场景 | 先读 |
| --- | --- |
| Token、DNS、Tunnel、Access、Pages/R2 | `docs/子模块_Cloudflare公网入口与账号管理_cloudflare_ops.md` |
| 公网拓扑、代理、Tailscale、回源 | `docs/子模块_网络暴露与代理穿透_network_proxy.md` |
| 本地分析公网入口 | `docs/子模块_本地数据分析平台_local_analytics_platform.md` |
| test/prod Web、API、管理后台发布 | 对应控制面文档 + `allbot-ops-deployment` |
| QQCC owner/admin/webhook Host 隔离 | `docs/子模块_QQCC用户私有Bot平台_qqcc_private_bot_platform.md` |

先读目标一行，再用 API 只读回读当前 DNS、Tunnel ingress、Access app/policy、
Pages project/deployment 或 R2 配置。文档中的运行态也必须复核。

## 2. 事实源与凭据

- Token 文件路径、非敏感账号/zone 标识和域名拓扑由 Cloudflare 专项文档维护；
  token 值不得进入聊天、Git、文档、日志、shell history 或 compose 展开输出。
- Token 名称不代表权限。先使用与 token 类型匹配的 verify endpoint，再对目标
  产品 API 做最小只读探测；403 不能被解释为已授权。
- Pages 成功证据来自 API 中 production deployment、完整 SHA、stage、
  canonical deployment 和正式域名 runtime revision；CLI 返回的临时 URL
  不是完整验收。
- Tunnel/DNS/Access 的 live API 是当前事实源；systemd、origin 和应用健康还需
  在各自控制面独立验证。

## 3. 操作红线

- 未经用户明确要求，不创建、修改或删除 DNS、public hostname、Access
  app/policy、Tunnel ingress、Pages custom domain/deployment 或 R2 policy。
- 管理、分析、数据库、Redis、对象存储管理端口不得裸露公网。浏览器管理入口
  必须有 Cloudflare Access 或等价身份层，并保留应用层鉴权。
- 面向普通用户/owner 的 WebApp 不能错误套用管理员邮箱 allowlist；必须依赖
  应用 ticket/JWT、严格 Host allowlist、origin/backend 双重路由隔离。
- Telegram webhook 和 Worker Central 等机器入口不能启用浏览器 Access 登录
  页；使用 webhook secret、agent secret、WAF/rate limit 等机器认证。
- Access 默认最小 allowlist；扩大到组织、域名或所有人前必须再次确认。
- Token 轮换顺序：写新文件并限制权限 → 只读验证目标 API → 切换消费者 →
  禁用旧 token。聊天中出现过的 token 按泄露处理。
- Tunnel localhost 回源时 source IP 不是权威隔离；Host、应用鉴权和 default
  404 必须独立成立。
- 生产公网入口或正式 Pages mutation 同时受 `allbot-ops-deployment` 的生产
  授权、不可变 SHA、事务和回滚门禁约束。

## 4. 标准流程

1. 明确 env、zone、hostname、产品、目标资源和用户授权范围。
2. 从受限 token 文件读入局部变量；只输出非敏感 ID、状态与权限结论。
3. 列出目标当前态与相邻规则，确认顺序、catch-all、Host 和回源。
4. 先形成变更计划、验证项和精确回滚对象；未授权时停在 dry-run/只读阶段。
5. mutation 后立即 API 回读，再验证未登录行为、授权行为、origin/app 健康和
   非目标入口未漂移。
6. 更新专项文档的稳定拓扑或 SOP；一次操作结果进入 evidence/archive，不回写
   Skill。

## 5. 最小验证

- Token：文件权限、正确 verify endpoint、目标产品 API 最小权限、旧 token
  禁用状态。
- DNS/Tunnel：proxied 状态、ingress 顺序、catch-all、origin 连通和非目标
  hostname 不变。
- Access：未登录重定向/拒绝、allow/deny 身份、应用层登录、机器入口无登录页。
- Pages：project branch/自动部署策略、完整 SHA、canonical deployment、正式
  域名 runtime revision 和可执行 rollback ID。
- R2：目标 bucket/CORS/public policy 与实际客户端权限分别验证，不混用 API
  token 和 S3 credential。
- 交付说明只读或 mutation、目标资源、授权来源、回读证据、回滚对象及仍需
  运行态复核的项目，不输出任何 secret。
