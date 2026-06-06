# 子模块: 云控制面 SSH 密钥管理 (Cloud SSH Access)

## 1. 目标与范围

本文档记录 AllBot 云控制面服务器的 SSH 密钥、登录入口、权限边界和轮换策略。云控制面当前用于 DigitalOcean Singapore Droplet，承载 Bot、Web API、Payment API、Central API、Dashboard、imgproxy、反向代理与监控等控制面服务。

本文档不记录私钥内容、云服务密码、token、R2 key、数据库密码或任何可直接登录生产环境的敏感凭据。

最近一次更新：2026-06-06，Asia/Shanghai。

## 2. 当前 SSH 密钥

当前 Droplet：

| 项目 | 当前值 |
| :--- | :--- |
| Droplet 名称 | `allbot-do-sgp1-control-01` |
| 区域 | DigitalOcean Singapore `SGP1` |
| 公网 IPv4 | `159.223.39.217` |
| VPC/私网 IPv4 | `10.104.0.2` |
| 系统 | Ubuntu 24.04.3 LTS |
| 规格 | Basic Regular `$48/mo`，4 vCPU / 8GB RAM / 160GB SSD / 5TB transfer |
| 默认研发登录用户 | `deploy` |
| root 初始化入口 | `allbot-do-sgp1-control-root` |

| 项目 | 当前值 |
| :--- | :--- |
| 用途 | DigitalOcean Singapore 云控制面登录 |
| DigitalOcean SSH key 名称 | `allbot-do-sgp1-control-20260606` |
| 算法 | `ssh-ed25519` |
| 私钥路径 | `/home/hfy/.ssh/allbot_do_sgp1_control_20260606_ed25519` |
| 公钥路径 | `/home/hfy/.ssh/allbot_do_sgp1_control_20260606_ed25519.pub` |
| 公钥指纹 | `SHA256:K3tTbjmz8Oau7mSliQcBeTs44YsqHGpQKGsg9TE6Rjo` |
| 文件权限 | `~/.ssh` 为 `700`，私钥为 `600`，公钥为 `644` |

私钥只能保存在本地管理机，不得提交到 Git、不得粘贴到网页、不得发送给第三方。DigitalOcean 控制台只需要粘贴 `.pub` 公钥内容。

查看公钥内容：

```bash
cat ~/.ssh/allbot_do_sgp1_control_20260606_ed25519.pub
```

校验指纹：

```bash
ssh-keygen -lf ~/.ssh/allbot_do_sgp1_control_20260606_ed25519.pub
```

## 3. DigitalOcean 创建 Droplet 时填写

创建 Droplet 的 SSH key 表单：

| 字段 | 填写方式 |
| :--- | :--- |
| SSH 密钥内容 | 粘贴 `cat ~/.ssh/allbot_do_sgp1_control_20260606_ed25519.pub` 的完整输出 |
| SSH 密钥名称 | `allbot-do-sgp1-control-20260606` |

不要粘贴私钥文件 `/home/hfy/.ssh/allbot_do_sgp1_control_20260606_ed25519` 的内容。

## 4. VS Code / Codex SSH Config

当前本地 `/home/hfy/.ssh/config` 已配置两个 Host：

```sshconfig
Host allbot-do-sgp1-control-root
    HostName 159.223.39.217
    User root
    IdentityFile ~/.ssh/allbot_do_sgp1_control_20260606_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
    StrictHostKeyChecking accept-new

Host allbot-do-sgp1-control
    HostName 159.223.39.217
    User deploy
    IdentityFile ~/.ssh/allbot_do_sgp1_control_20260606_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
    StrictHostKeyChecking accept-new
```

日常 VS Code Remote-SSH、Codex 远程研发和常规运维默认使用：

```bash
ssh allbot-do-sgp1-control
```

只在初始化、救援或明确需要 root 时使用：

```bash
ssh allbot-do-sgp1-control-root
```

## 5. 云服务器初始化安全基线

首次登录后建议按下面顺序收口：

1. 更新系统包并重启到最新内核。
2. 创建非 root 运维用户，例如 `deploy`，加入 `sudo` 组。
3. 把同一个公钥写入 `/home/deploy/.ssh/authorized_keys`。
4. 确认 `deploy` 用户可免密登录后，再调整 SSH 服务。
5. 禁用密码登录：`PasswordAuthentication no`。
6. 稳定后禁用 root 登录或改为 `PermitRootLogin prohibit-password`。
7. 防火墙只开放 `22`、`80`、`443`，后续 SSH 尽量限制来源 IP 或改走 Tailscale。
8. 安装 Tailscale，让云控制面和武汉本地 GPU/主服务器走出站组网。
9. Central API、Postgres、Valkey、Dashboard 管理接口不得公网裸露。

## 6. `$48/mo` Droplet 的使用边界

DigitalOcean Basic Regular `$48/mo` Droplet 的页面规格为 `4 vCPU / 8GB RAM / 160GB SSD / 5TB transfer`。它可以作为云测试栈和过渡生产控制面使用，但必须满足下面条件：

- Postgres 使用托管数据库或外部数据库，不在这台 Droplet 上长期自托管生产库。
- Redis/Valkey 使用托管服务或外部 Redis，不在这台 Droplet 上承载完整生产 Redis。
- MinIO 不迁到这台 Droplet；公开媒体走 Cloudflare R2，本地 MinIO 只作为武汉热缓存。
- 本地 GPU 和 ComfyUI 不迁移；`comfy-agent-1..7` 通过 Tailscale 访问云 Central API。
- `web-api`、Dashboard backend、imgproxy 的 worker/concurrency 需要按 4 vCPU 控制，不照搬主服务器的宽松配置。

建议初始运行参数：

| 服务 | `$48/mo` 初始建议 |
| :--- | :--- |
| `web-api` | 2-3 个 Uvicorn worker 起步，压测后再调 |
| `dashboard-backend` | 1-2 个 worker 起步 |
| `imgproxy` | 并发 4-6 起步，优先处理 R2 URL |
| `tg-bot` | 单实例，确保全网只有一个生产 bot |
| `payment-api` | 单实例，重点验证回调幂等 |
| Central API | 单实例，端口只允许本机/Tailscale |

升级触发条件：

- App 节点 CPU 连续 15 分钟超过 70%。
- 可用内存长期低于 1.5GB 或出现 OOM。
- Web API p95 延迟明显上升，或 Cloudflare 502/504 增加。
- Postgres/Valkey 连接池耗尽。
- Central queue/running 状态正常但 API 响应变慢。
- Dashboard 查询影响 Web/API 响应。

若触发以上任一条件，应升级到 `8 vCPU / 16GB RAM / 320GB SSD / 6TB transfer` 的 `$96/mo` 规格，或把 Dashboard/后台任务拆到第二台节点。

## 7. 轮换与撤销

需要轮换 SSH key 的场景：

- 私钥可能泄露。
- 管理机丢失或被入侵。
- 运维人员变化。
- 云控制面切换供应商或重建。

轮换流程：

1. 生成新 key，命名带日期。
2. 把新公钥加入 DigitalOcean Team 和目标服务器 `authorized_keys`。
3. 使用新 key 验证登录。
4. 删除旧公钥。
5. 更新本文档的 key 名称、路径和指纹。
6. 确认旧 key 无法登录。

不要先删旧 key 再验证新 key，避免把自己锁在服务器外面。
