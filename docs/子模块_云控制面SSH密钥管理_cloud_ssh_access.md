# 子模块: 云控制面 SSH 密钥管理 (Cloud SSH Access)

## 1. 目标与范围

本文档记录 AllBot 云控制面服务器的 SSH 密钥、登录入口、权限边界和轮换策略。当前包含正式云控制面 Droplet 与独立云测试控制面 Droplet；两者必须用清晰 Host 别名区分，避免误把测试操作打到正式服务。

武汉局域网 GPU 节点的 SSH 管理独立记录在 `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md`，不要把 GPU 节点密码或私钥混入云控制面文档。

本文档不记录私钥内容、云服务密码、token、R2 key、数据库密码或任何可直接登录生产环境的敏感凭据。

最近一次更新：2026-07-30，Asia/Shanghai。

## 2. 当前 SSH 密钥

正式 Droplet：

| 项目 | 当前值 |
| :--- | :--- |
| Droplet 名称 | `allbot-do-sgp1-control-01` |
| 区域 | DigitalOcean Singapore `SGP1` |
| 公网 IPv4 | `159.223.39.217` |
| VPC/私网 IPv4 | `10.104.0.2` |
| 系统 | Ubuntu 24.04.3 LTS |
| 规格 | Basic Regular `$96/mo`，8 vCPU / 16GB RAM / 320GB SSD / 6TB transfer |
| 默认研发登录用户 | `deploy` |
| root 初始化入口 | `allbot-do-sgp1-control-root` |

独立测试 Droplet：

| 项目 | 当前值 |
| :--- | :--- |
| Droplet 名称 | `allbot-do-sgp1-test-control` |
| 区域 | DigitalOcean Singapore `SGP1` |
| 公网 IPv4 | `168.144.128.133` |
| Tailscale IPv4 | `100.82.124.91` |
| VPC/私网 IPv4 | `10.104.0.5` |
| 系统 | Ubuntu 24.04 LTS |
| 规格 | Basic Regular `$12/mo`，1 vCPU / 2GB RAM / 50GB SSD / 2TB transfer |
| 默认研发登录用户 | `deploy` |
| root 初始化入口 | `allbot-do-sgp1-test-control-root` |

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

Host allbot-do-sgp1-test-control-root
    HostName 168.144.128.133
    User root
    IdentityFile ~/.ssh/allbot_do_sgp1_control_20260606_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
    StrictHostKeyChecking accept-new

Host allbot-do-sgp1-test-control
    HostName 168.144.128.133
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

云测试环境运维使用：

```bash
ssh allbot-do-sgp1-test-control
```

只在初始化、救援或明确需要 root 时使用：

```bash
ssh allbot-do-sgp1-control-root
```

## 5. SSH 故障诊断最小闭环

SSH 故障统一先加载 `allbot-cloud-ssh`。不要从“连接不上”直接跳到重启、重置
密码、放宽防火墙或重建实例；先按名称解析、TCP、SSH 握手、认证、会话五个
阶段确定第一个失败点。

最小证据：

```bash
ssh -G <host-alias> | sed -n \
  '/^hostname /p;/^user /p;/^port /p;/^identityfile /p;/^identitiesonly /p;/^proxyjump /p'
nc -vz -w 5 <hostname> <port>
ssh -vv -o BatchMode=yes -o ConnectTimeout=10 <host-alias>
```

错误分流：

| 现象 | 优先核对 |
| :--- | :--- |
| 名称无法解析 | Host 别名、DNS、云控制台实时 IP |
| 连接超时 | 实例状态、路由、来源 IP、云防火墙、主机防火墙 |
| 连接被拒绝 | `sshd` 状态、监听端口、`ListenAddress` |
| `Permission denied (publickey)` | 用户、`IdentityFile`、公钥安装、目录/文件权限 |
| 主机标识变化 | 带外核对实例与新指纹，确认后精确清理旧记录 |
| 偶发断线 | 路径丢包、NAT/防火墙 idle timeout、主机负载，再评估保活 |

普通 Web Console 仍依赖网络、SSH 端口和 Droplet Agent；网络或 `sshd` 失效时
使用 Recovery Console。任何远端配置、云防火墙、重启、密码或密钥 mutation
仍需明确授权，并在修改 `sshd` 前保留现有会话、运行 `sshd -t`、验证新会话。

参考资料：

- [DigitalOcean：连接 Droplet 的 SSH 前提](https://docs.digitalocean.com/products/droplets/how-to/connect-with-ssh/)
- [DigitalOcean：SSH 连接故障诊断](https://docs.digitalocean.com/support/how-to-troubleshoot-ssh-connectivity-issues/)
- [DigitalOcean：Droplet Console 与 Recovery Console](https://docs.digitalocean.com/products/droplets/how-to/connect-with-console/)
- [DigitalOcean：私网 Droplet 与 ProxyJump](https://docs.digitalocean.com/products/droplets/how-to/connect-private-droplet/)

## 6. 云服务器初始化安全基线

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

## 7. `$96/mo` Droplet 的使用边界

DigitalOcean Basic Regular `$96/mo` Droplet 的页面规格为 `8 vCPU / 16GB RAM / 320GB SSD / 6TB transfer`。2026-06-16 原地扩容后，它当前承接正式生产控制面；PostgreSQL、Valkey 与对象存储仍不在该 Droplet 上长期自托管。

- Postgres 使用托管数据库或外部数据库，不在这台 Droplet 上长期自托管生产库。
- Redis/Valkey 使用托管服务或外部 Redis，不在这台 Droplet 上承载完整生产 Redis。
- MinIO 不迁到这台 Droplet；公开媒体走 Cloudflare R2，本地 MinIO 只作为武汉热缓存。
- 本地 GPU 和 ComfyUI 不迁移；本地 worker compose、LAN AIO 与 RunPod 都通过 Central worker 协议接入。当前容量必须以 `/system/workers` 为准，不写死为固定数量。
- `web-api`、Dashboard backend、imgproxy 的 worker/concurrency 需要按 8 vCPU 与 PostgreSQL 连接池预算控制，不照搬主服务器的宽松配置。
- 云端运行目录为 `/home/deploy/APP/All_bot`；日常热修应先备份被覆盖文件，不能假设远端目录一定是完整 Git 工作区。

建议初始运行参数：

| 服务 | `$96/mo` 当前建议 |
| :--- | :--- |
| `web-api` | 当前按 `uvicorn --workers 4` 与 `DB_POOL_SIZE=6`、`DB_MAX_OVERFLOW=6` 控制，后续扩进程数前先复核 DB 连接池 |
| `dashboard-backend` | 当前保持 `gunicorn -w 1`，优先靠短缓存/single-flight 降低 stats 压力 |
| `imgproxy` | 并发 4-6 起步，优先处理 R2 URL |
| `tg-bot` | 单实例，确保全网只有一个生产 bot |
| `payment-api` | 单实例，重点验证回调幂等 |
| Central API | 单实例，端口只允许本机/Tailscale |

升级触发条件：

- App 节点 CPU 连续 15 分钟超过 70%。
- 可用内存长期低于 1.5GB 或出现 OOM。
- Web API p95 延迟明显上升，或 Cloudflare 502/504 增加。
- Postgres/Valkey 连接池耗尽。
- Central queue/running 状态正常但 API 响应变慢，且状态观测缓存、Dashboard stats 缓存和 Valkey 连接复用后仍无法缓解。
- Dashboard 查询影响 Web/API 响应。

若触发以上任一条件，应升级到 `8 vCPU / 16GB RAM / 320GB SSD / 6TB transfer` 的 `$96/mo` 规格，或把 Dashboard/后台任务拆到第二台节点。

## 8. 轮换与撤销

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
