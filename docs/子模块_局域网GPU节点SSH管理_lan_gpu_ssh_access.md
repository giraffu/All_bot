# 子模块: 局域网 GPU 节点 SSH 管理 (LAN GPU SSH Access)

## 1. 目标与范围

本文档记录本地主服务器到武汉局域网 GPU 节点的 SSH 登录入口、密钥、权限边界和验证流程。该 SSH 入口用于 ComfyUI/GPU 节点环境检查、模型文件核对、日志查看、研发联调和故障恢复。

GPU 节点硬件、容器、ComfyUI 实例、模型挂载和单容器运维边界见 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`。

本文档不记录 SSH 密码、私钥内容、R2 key、数据库密码、`.env.cloud.prod` 或任何可直接登录生产环境的敏感凭据。

最近一次更新：2026-06-08，Asia/Shanghai。

## 2. 当前 SSH Key

| 项目 | 当前值 |
| :--- | :--- |
| 用途 | 本地主服务器到局域网 GPU 节点运维登录 |
| 算法 | `ssh-ed25519` |
| 私钥路径 | `/home/hfy/.ssh/allbot_lan_gpu_ops_20260608_ed25519` |
| 公钥路径 | `/home/hfy/.ssh/allbot_lan_gpu_ops_20260608_ed25519.pub` |
| 公钥指纹 | `SHA256:kvI633eQW/iO4y25rLPPJML8AVDpHCeJKu9tFRxXbEQ` |
| 文件权限 | `~/.ssh` 为 `700`，私钥为 `600`，公钥为 `644` |

私钥只允许保存在本地主服务器 `/home/hfy/.ssh/`。不得提交到 Git、不得粘贴到聊天或文档、不得复制到云控制面。

校验指纹：

```bash
ssh-keygen -lf ~/.ssh/allbot_lan_gpu_ops_20260608_ed25519.pub
```

## 3. SSH Config

本地主服务器 `/home/hfy/.ssh/config` 已配置以下 Host：

```sshconfig
Host allbot-gpu-226 gpu-226
    HostName 192.168.1.226
    User ubantu
    IdentityFile ~/.ssh/allbot_lan_gpu_ops_20260608_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
    StrictHostKeyChecking accept-new

Host allbot-gpu-177 gpu-177
    HostName 192.168.1.177
    User ubantui
    IdentityFile ~/.ssh/allbot_lan_gpu_ops_20260608_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
    StrictHostKeyChecking accept-new

Host allbot-gpu-252 gpu-252
    HostName 192.168.1.252
    User user
    IdentityFile ~/.ssh/allbot_lan_gpu_ops_20260608_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
    StrictHostKeyChecking accept-new

Host allbot-gpu-002 gpu-002
    HostName 192.168.1.2
    User chuzeyu
    IdentityFile ~/.ssh/allbot_lan_gpu_ops_20260608_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
    StrictHostKeyChecking accept-new
```

日常登录示例：

```bash
ssh allbot-gpu-177
ssh gpu-252
```

## 4. 节点清单

| SSH Host | IP | 用户 | ComfyUI 端口 | 生产 Worker |
| :--- | :--- | :--- | :--- | :--- |
| `allbot-gpu-226` | `192.168.1.226` | `ubantu` | `8188` | `cloud_prod_worker_01` |
| `allbot-gpu-177` | `192.168.1.177` | `ubantui` | AIO `8190`、`8191`；旧 `8188`/`8189` stopped rollback | `lan_aio_prod_gpu177_gpu0_image_to_video_01`、`lan_aio_prod_gpu177_gpu1_ltx_video_01` |
| `allbot-gpu-252` | `192.168.1.252` | `user` | `8188`、`8189` | `cloud_prod_worker_04`、`cloud_prod_worker_05` |
| `allbot-gpu-002` | `192.168.1.2` | `chuzeyu` | AIO `8190`、`8191`；旧 `8188`/`8189` stopped rollback | `lan_aio_prod_gpu002_gpu0_scail2_01`、`lan_aio_prod_gpu002_gpu1_image_to_video_01` |

当前 4 台节点均可用 key-based SSH 登录；`sudo -n true` 均不通过，表示不是免密 sudo。需要 root 级操作时，必须由人工确认远端 sudo 密码或在维护窗口内操作。

## 5. 标准验证命令

SSH 连通性：

```bash
for host in allbot-gpu-226 allbot-gpu-177 allbot-gpu-252 allbot-gpu-002; do
  ssh -o BatchMode=yes "$host" 'hostname; whoami; nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv,noheader,nounits'
done
```

Docker / Compose：

```bash
for host in allbot-gpu-226 allbot-gpu-177 allbot-gpu-252 allbot-gpu-002; do
  ssh "$host" 'command -v docker; docker compose version 2>/dev/null || docker-compose version 2>/dev/null || true'
done
```

ComfyUI 健康：

```bash
curl -fsS http://192.168.1.226:8188/system_stats
curl -fsS http://192.168.1.177:8188/system_stats
curl -fsS http://192.168.1.177:8189/system_stats
curl -fsS http://192.168.1.252:8188/system_stats
curl -fsS http://192.168.1.252:8189/system_stats
curl -fsS http://192.168.1.2:8188/system_stats
curl -fsS http://192.168.1.2:8189/system_stats
```

关键 ComfyUI 节点：

```bash
for base in \
  http://192.168.1.226:8188 \
  http://192.168.1.177:8188 \
  http://192.168.1.177:8189 \
  http://192.168.1.252:8188 \
  http://192.168.1.252:8189 \
  http://192.168.1.2:8188 \
  http://192.168.1.2:8189
do
  echo "== $base =="
  curl -fsS "$base/object_info/FL_RIFE" | head -c 120; echo
  curl -fsS "$base/object_info/RIFE%20VFI" | head -c 120; echo
  curl -fsS "$base/object_info/UNETLoader" | head -c 120; echo
  curl -fsS "$base/object_info/VHS_VideoCombine" | head -c 120; echo
done
```

## 6. 当前环境快照

| ComfyUI URL | ComfyUI | PyTorch | RIFE 节点备注 |
| :--- | :--- | :--- | :--- |
| `http://192.168.1.226:8188` | `0.17.0` | `2.10.0+cu130` | `FL_RIFE` 存在，`RIFE VFI` 为空 |
| `http://192.168.1.177:8188` | `0.18.2` | `2.11.0+cu130` | `FL_RIFE` 与 `RIFE VFI` 均存在 |
| `http://192.168.1.177:8189` | `0.18.2` | `2.11.0+cu130` | `FL_RIFE` 与 `RIFE VFI` 均存在 |
| `http://192.168.1.252:8188` | `0.18.5` | `2.11.0+cu128` | `FL_RIFE` 与 `RIFE VFI` 均存在 |
| `http://192.168.1.252:8189` | `0.22.0` | `2.11.0+cu128` | `FL_RIFE` 与 `RIFE VFI` 均存在 |
| `http://192.168.1.2:8188` | `0.19.5` | `2.11.0+cu128` | `FL_RIFE` 与 `RIFE VFI` 均存在 |
| `http://192.168.1.2:8189` | `0.22.0` | `2.11.0+cu128` | `FL_RIFE` 与 `RIFE VFI` 均存在 |

`192.168.1.177:8189` 是 `cloud_prod_worker_03` 使用的 ComfyUI 端口。2026-06-08 已在 `comfy1` 容器内补齐 `socksio` 并重启，使 `comfyui_fill-nodes` 正常加载 `FL_RIFE`；worker compose 不再需要 `WAN22_RIFE_NODE_CLASS`。

## 7. 权限与安全边界

- SSH 登录默认使用普通用户，非 root。
- 远端当前不是免密 sudo；涉及驱动、系统服务、Docker daemon、ComfyUI 服务安装路径等 root 操作时，需要维护窗口和人工确认。
- 不在文档、Git、compose 或 `.env.cloud.prod` 中保存 SSH 密码。
- 若短期必须使用密码下发公钥，只允许用临时 askpass/交互流程；完成后删除临时脚本并改回 key-based 登录。
- 建议后续逐台轮换弱密码，稳定后禁用密码登录或限制为局域网来源。
- 不建议把局域网 GPU 节点暴露到公网；云控制面访问本地执行面仍走本地主服务器的 worker/relay/Tailscale 架构。

## 8. 轮换与撤销

需要轮换 LAN GPU SSH key 时：

1. 在本地主服务器生成新 key，文件名带日期。
2. 把新公钥追加到 4 台 GPU 节点对应用户的 `~/.ssh/authorized_keys`。
3. 更新 `/home/hfy/.ssh/config` 的 `IdentityFile`。
4. 用 `ssh -o BatchMode=yes <host> true` 验证 4 台均可免密登录。
5. 删除旧公钥。
6. 更新本文档的 key 路径、指纹和更新时间。

不要先删除旧公钥再验证新公钥，避免把管理机锁在节点外。
