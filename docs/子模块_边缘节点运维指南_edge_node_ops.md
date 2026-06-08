# 子模块: 边缘节点资源与运维 (Edge Node Ops)

## 1. 目标与范围

本文档记录 AllBot 当前两台海外 VPS 边缘节点的职责范围、资源配置、服务入口、运维红线和排障流程。边缘节点不是业务事实源；它们负责公网入口、静态资源、反向代理、legacy 媒体回源和 Telegram 大文件本地 API。

本文档不是实时监控面板。CPU、内存、磁盘、公网状态和服务端口都是采集时快照；做切流、清理、扩容或证书变更前必须重新采集。

最近一次采集：2026-06-08，Asia/Shanghai。

## 2. 边缘节点总览

| 节点 | 入口 | 主要职责 | 当前状态 |
| :--- | :--- | :--- | :--- |
| Web/Nginx 边缘 VPS | Tailscale `100.88.57.122`，公网 `154.17.30.113`，SSH `root@100.88.57.122` 使用 `frontend/ssh_key/id_rsa.pem` | `web.aivison.it.com` / `web-test.aivison.it.com` 静态站，`/api/` 反代，`assets.aivison.it.com` legacy MinIO 代理 | SSH 可用，Nginx/Tailscale active，根盘 96% 高风险 |
| Telegram Local API VPS | 公网 `69.63.220.115` | Telegram Local Bot API `8081`，文件 HTTP 服务 `8082`，支撑大文件下载/上传绕过官方 Bot API 限制 | 8081/8082/22 公网端口可达；当前主服务器未配置可用 SSH key，资源需补采 |

## 3. Web/Nginx 边缘 VPS

### 3.1 资源快照

| 项目 | 当前事实 |
| :--- | :--- |
| 主机名 | `web` |
| SSH | `ssh -i frontend/ssh_key/id_rsa.pem root@100.88.57.122` |
| 公网 IPv4 | `154.17.30.113` |
| Tailscale IPv4 | `100.88.57.122` |
| 操作系统 | Ubuntu 24.04 LTS |
| 内核 | Linux `6.8.0-35-generic` |
| 虚拟化 | KVM / QEMU |
| CPU | 2 vCPU，AMD EPYC 9655 |
| 内存 | 1.9GiB，总可用约 1.5GiB |
| Swap | 1.0GiB，当前未使用 |
| 系统盘 | `/dev/vda1` ext4，40G，总用量 36G，可用 1.7G，96% |
| 运行服务 | Nginx active，Tailscale active，Docker 未安装/未运行，cloudflared inactive |
| Nginx | `nginx/1.24.0 (Ubuntu)`，`nginx -t` 通过 |
| 监听端口 | 80/443/22，Tailscale 内部监听端口 |
| 静态目录 | `/root/dist`、`/root/dist-test`，各约 2.6M |

容量风险：
- 根盘只剩约 `1.7G`，这是当前 Web 边缘节点第一风险。
- `/var/cache/nginx` 约 `26G`，主要是 `minio_cache`。
- `/var/log/nginx` 约 `4.4G`，其中 `access.log` 约 `4.4G`，`error.log` 约 `54M`。
- 存在 `/etc/logrotate.d/nginx` 配置，但本次未看到 `/var/lib/logrotate/status` 或 `/etc/cron.daily/logrotate`，需要单独确认 logrotate 是否实际运行。

2026-06-08 17:10 Web 卡顿巡检补充：
- Web 边缘到云 Web API `100.107.220.127:8000` 约 `0.51-0.55s`；本地主服务器经公网访问 `web.aivison.it.com` API 可到 `1.6-2.8s`。
- 最近 30 分钟窗口曾观测到约 `202` 次 499，集中在 `/api/tasks/{id}/result`、`/api/gallery/posts`、`/api/gallery/my-favorites`、`/api/users/history` 等等待型接口。
- `assets.aivison.it.com` legacy 回源曾在 30 分钟内出现约 `37` 次 upstream 异常；其中大量为 `upstream prematurely closed connection`，少量为 `upstream timed out`。
- `/minio/health/live` 返回 200 只能证明本地 MinIO 基础健康，不代表具体历史图片/视频对象读取链路稳定；验收必须测真实对象 URL 或至少统计 `assets` error.log。

### 3.2 域名与路由

| 域名 | 边缘职责 | 当前 upstream |
| :--- | :--- | :--- |
| `web.aivison.it.com` | 正式 Web 静态站；`/api/` 反代正式云 Web API | `http://100.107.220.127:8000` |
| `web-test.aivison.it.com` | 测试 Web 静态站；`/api/` 反代云测试 Web API | `http://100.107.220.127:8001` |
| `assets.aivison.it.com` | legacy MinIO 只读/兼容回源，用于历史媒体 fallback | `http://100.99.254.53:9000` |

公网快照：

| URL | 状态 |
| :--- | :--- |
| `https://web.aivison.it.com` | 200 |
| `https://web.aivison.it.com/api/health` | 200 |
| `https://web-test.aivison.it.com` | 200 |
| `https://web-test.aivison.it.com/api/health` | 502，本轮保留测试边缘站但测试 API 入口可能未稳定运行 |
| `https://assets.aivison.it.com` | 根路径 403；这不等同于具体对象不可读，验收 legacy 对象时必须测真实 object URL |

### 3.3 Nginx 配置红线

配置入口：
- `/etc/nginx/sites-enabled/all_bot`
- `/etc/nginx/sites-enabled/web-test.aivison.it.com`
- 仓库模板：`all_bot_nginx_cloud_prod.conf`、`all_bot_nginx_web_test.conf`

对象存储代理红线：
- `assets.aivison.it.com` 代理 MinIO/S3 预签名 URL 时，`proxy_pass` 不得包含 URI 或尾部斜杠。
- 必须保持 `proxy_request_buffering off;`，避免大文件上传被 Nginx 缓冲到边缘磁盘。
- 下载缓存可保留 `proxy_cache minio_cache`，但当前 `max_size=25g` 已把 40G 根盘推到高风险状态；后续应缩小 cache、迁移 cache 目录或扩盘。
- 不要在 Nginx 层硬写 CORS 兜底。对象存储 CORS 应由 MinIO/R2 事实源配置。
- `client_max_body_size 50m;` 必须保留。

Web API/SSE 红线：
- `/api/` 需要 `proxy_buffering off; proxy_cache off; chunked_transfer_encoding off;`，避免 SSE 和任务状态流被缓存或分块延迟。
- 正式 Web `/api/` 当前应回源云 Web API `100.107.220.127:8000`，不要误改回本地主服务器旧入口。
- 测试 Web `/api/` 当前应回源云测试 Web API `100.107.220.127:8001`，不要误指正式 `8000`。

### 3.4 发布与回滚

正式 Web 静态站：

```bash
cd /home/hfy/APP/All_bot/frontend
npm run build
scp -i ssh_key/id_rsa.pem -r dist/* root@100.88.57.122:/root/dist/
```

测试 Web 静态站：

```bash
cd /home/hfy/APP/All_bot/frontend
npm run deploy:edge-test
```

Nginx 配置变更：

```bash
ssh -i frontend/ssh_key/id_rsa.pem root@100.88.57.122
nginx -t
nginx -s reload
```

操作边界：
- 改 `all_bot` 会影响正式 Web 和 `assets.aivison.it.com` legacy fallback。
- 改 `web-test.aivison.it.com` 只影响测试静态站和测试 `/api/`。
- 不要用 `systemctl restart nginx` 作为常规动作；优先 `nginx -t && nginx -s reload`。
- 不要删除 `/etc/letsencrypt`、`/root/dist`、`/root/dist-test`、`/etc/nginx/sites-available/*` 或备份目录。

### 3.5 容量处理建议

当前不建议在不了解访问高峰和 legacy 命中率的情况下直接清空缓存。推荐顺序：

1. 先备份 Nginx 配置与确认公网 health。
2. 核对 logrotate 是否安装并实际运行；若未运行，优先修复 logrotate。
3. 对超大 `access.log` 先执行受控轮转，而不是删除正在被 Nginx 打开的文件。
4. 对 `minio_cache` 先评估 legacy 访问量，再缩小 `proxy_cache_path max_size` 或按 cache 规则清理。
5. 根盘低于 10% 可用时，不要发布新静态资源、不要申请大量证书、不要扩大 cache。
6. 大日志分析优先使用 `tail`、按文件尾部 seek 或短窗口聚合；不要在线全量扫描 4GB 级 `access.log`，否则排障本身会增加边缘压力。
7. 若 499 激增但 5xx 很少，优先判断为用户端等待过久/链路慢/后端依赖慢导致主动断开，再结合云内、边缘到云、公网三段延迟定位。

只读采集命令：

```bash
ssh -i frontend/ssh_key/id_rsa.pem root@100.88.57.122 '
hostnamectl
lscpu | grep -E "Model name|^CPU\\(s\\)"
free -h
df -hT -x tmpfs -x devtmpfs
systemctl is-active nginx tailscaled cloudflared docker 2>/dev/null || true
nginx -t
du -sh /var/cache/nginx /var/log/nginx /root/dist /root/dist-test 2>/dev/null
'
```

Web 卡顿只读聚合命令示例：

```bash
ssh -i frontend/ssh_key/id_rsa.pem root@100.88.57.122 '
for i in 1 2 3; do
  curl -sS -o /dev/null -w "edge_to_cloud http=%{http_code} ttfb=%{time_starttransfer} total=%{time_total}\n" --max-time 8 http://100.107.220.127:8000/api/health
done
tail -n 5000 /var/log/nginx/access.log | awk "{print \$9}" | sort | uniq -c | sort -nr | head
tail -n 300 /var/log/nginx/error.log | grep -Ei "assets.aivison.it.com|upstream|timeout|connect|no space" | tail -n 80
'
```

## 4. Telegram Local API VPS

### 4.1 当前事实

| 项目 | 当前事实 |
| :--- | :--- |
| 公网 IPv4 | `69.63.220.115` |
| SSH | `root@69.63.220.115`，22 端口可达；当前主服务器默认 key 与 `frontend/ssh_key/id_rsa.pem` 均登录失败 |
| 主要职责 | Telegram Local Bot API 和文件 HTTP 服务 |
| API 端口 | `8081`，根路径返回 404 属正常现象，真实健康需用 `/bot<TOKEN>/getMe` |
| 文件端口 | `8082`，公网可达 |
| 资源快照 | 因 SSH key 未打通，本轮未采集 CPU/内存/磁盘/Docker 细节 |

生产配置契约：
- `.env.cloud.prod.example` 中默认 `TELEGRAM_API_BASE_URL=http://69.63.220.115:8081`
- `.env.cloud.prod.example` 中默认 `TELEGRAM_FILE_API_BASE_URL=http://69.63.220.115:8082`
- `scripts/safe_deploy_cloud_prod.sh` preflight 会检查 Telegram Local API base URL。

### 4.2 预期服务形态

Telegram Local API 节点预期运行：
- `telegram-bot-api` 容器或同等服务，监听 `8081`。
- HTTP 文件服务，监听 `8082`，只读暴露 `telegram-bot-api` 写入的本地文件目录。
- 共享目录通常为 `/var/lib/telegram-bot-api`。

示意命令只作为形态参考，真实恢复前必须先 SSH 登录节点核对现有容器、挂载、镜像和 token 来源：

```bash
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker inspect tg-local-api --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
curl -fsS http://127.0.0.1:8081/bot<TOKEN>/getMe
curl -fsS http://127.0.0.1:8082/
```

### 4.3 运维红线

- 不要在文档、日志或聊天中输出 Bot token。涉及 `getMe` 时只能在本机或目标 VPS 上执行，不要粘贴完整 URL。
- 不要清空 `/var/lib/telegram-bot-api`，否则正在处理的大文件可能丢失。
- 不要同时重建 `telegram-bot-api` 和文件服务；先确认 Bot 是否正在处理大文件。
- 若 8081 故障，Bot 可能无法通过 Local Bot API 收发大文件。
- 若 8082 故障，Bot 可能拿到 file path 但下载文件时报 404/403/timeout。
- 当前主服务器未纳入该 VPS 的 SSH 免密管理；需要补齐 SSH key 后，才能把它纳入完整资源巡检和日志排障。

公网只读探测：

```bash
nc -vz -w 5 69.63.220.115 22
nc -vz -w 5 69.63.220.115 8081
nc -vz -w 5 69.63.220.115 8082
curl -sS -o /dev/null -w "%{http_code} %{time_total}\n" --max-time 10 http://69.63.220.115:8081
curl -sS -o /dev/null -w "%{http_code} %{time_total}\n" --max-time 10 http://69.63.220.115:8082
```

## 5. 双边缘排障入口

| 故障现象 | 优先检查 |
| :--- | :--- |
| `web.aivison.it.com` 白屏或静态资源 404 | Web 边缘 `/root/dist`、Nginx `web.aivison.it.com` server、Cloudflare DNS/cache |
| Web `/api/health` 502/504 | Web 边缘 Nginx upstream、Tailscale 到云 Web API `100.107.220.127:8000` |
| Web API 普遍慢但云内 health 毫秒级 | 比较边缘到云、公网域名、Cloudflare/Tailscale 链路；统计 499 高频端点 |
| `web-test.aivison.it.com/api/health` 502 | 测试 Web API `100.107.220.127:8001` 是否运行；不要误改正式站 |
| legacy 历史媒体打不开或加载慢 | `assets.aivison.it.com` Nginx MinIO proxy、Tailscale 到 `100.99.254.53:9000`、真实 object URL；不要只看 `/minio/health/live` |
| `/api/tasks/{id}/result`、Gallery、History 大量 499 | 用户端等待过久断开；联动查 Web API R2 result timeout、legacy object_exists failure、边缘公网延迟 |
| 上传中文/空格文件 403 | 检查 `assets` proxy_pass 是否带 URI 或尾斜杠 |
| 上传大文件卡住 | 检查 `proxy_request_buffering off`、边缘根盘空间、Tailscale 链路 |
| Telegram 大文件下载 404/403 | Telegram Local API 节点 `8082`、文件服务挂载目录和 monkey patch 路径拼接 |
| Telegram API timeout | Telegram Local API 节点 `8081`、`telegram-bot-api` 容器日志、Bot Local API base URL |

## 6. 文档维护规则

以下事件发生后必须更新本文档、`docs/子模块_系统资源与容量画像_resource_inventory.md` 和相关 skills：
- 边缘 VPS 新增、下线、换 IP、换 SSH key。
- `web.aivison.it.com`、`web-test.aivison.it.com`、`assets.aivison.it.com` upstream 变化。
- Telegram Local API `8081/8082` 节点迁移或容器名、挂载目录变化。
- Nginx cache/log 生命周期调整。
- Web 边缘根盘扩容、清理或 cache 迁移。
- Cloudflare Tunnel / RMB 入口回源策略变化。
