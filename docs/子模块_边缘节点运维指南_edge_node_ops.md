# 子模块: 边缘节点资源与运维 (Edge Node Ops)

## 1. 目标与范围

本文档记录 AllBot 当前两台海外 VPS 边缘节点的职责范围、资源配置、服务入口、运维红线和排障流程。边缘节点不是业务事实源；它们负责 legacy 媒体人工回滚/旧外链/迁移排障、测试静态站、历史回滚入口和 Telegram 大文件本地 API。2026-06-08 晚间起，正式 `web.aivison.it.com` 已切到 Cloudflare Pages，正式 Web API 独立走 `api.aivison.it.com` Cloudflare Tunnel；正式应用不再生成 `assets.aivison.it.com` legacy URL，排障时不要到 VPS Nginx 查正式 Web 静态站、正式 `/api/`、`web-cf-test.aivison.it.com` 或 `api-cf-test.aivison.it.com`。

本文档不是实时监控面板。CPU、内存、磁盘、公网状态和服务端口都是采集时快照；做切流、清理、扩容或证书变更前必须重新采集。

最近一次采集：2026-06-16，Asia/Shanghai。

## 2. 边缘节点总览

| 节点 | 入口 | 主要职责 | 当前状态 |
| :--- | :--- | :--- | :--- |
| Web/Nginx 边缘 VPS | Tailscale `100.88.57.122`，公网 `154.17.30.113`，SSH `root@100.88.57.122` 使用 `frontend/ssh_key/id_rsa.pem` | `assets.aivison.it.com` legacy MinIO 代理（人工回滚/旧外链/迁移排障）、`web-test.aivison.it.com` 测试静态站、正式 Web 回滚用 `/root/dist` | SSH 可用，Nginx/Tailscale active；2026-06-16 受控轮转日志后根盘约 84%；不再承接正式 `web.aivison.it.com` 主流量 |
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
| 系统盘 | `/dev/vda1` ext4，40G，总用量约 32G，可用约 6.3G，84% |
| 运行服务 | Nginx active，Tailscale active，Docker 未安装/未运行，cloudflared inactive |
| Nginx | `nginx/1.24.0 (Ubuntu)`，`nginx -t` 通过 |
| 监听端口 | 80/443/22，Tailscale 内部监听端口 |
| 静态目录 | `/root/dist` 为正式 Web 回滚副本，`/root/dist-test` 为测试 Web 静态站，各约 2.6M |

容量风险：
- 2026-06-16 清理前根盘一度达到 `97%`，主要来自未轮转 Nginx 日志与较大的 `minio_cache`。
- `/var/cache/nginx` 约 `26G`，主要是 `minio_cache`；当前 `proxy_cache_path max_size=25g` 对 40G 根盘仍偏高。
- `/var/log/nginx` 在 2026-06-16 受控轮转并压缩后约 `359M`；当时 `access.log` 从约 `4.8G` 压缩为 `access.log.1.gz` 约 `371M`。
- `logrotate 3.21.0` 已安装，`logrotate.timer` 已 enabled/active；`/etc/logrotate.d/nginx` 已去掉 `delaycompress`，让轮转后的 Nginx 日志当天压缩释放空间。
- 若根盘再次低于 10% 可用，优先检查 `logrotate.timer`、`/var/log/nginx` 增长和 `minio_cache` 命中/占用，再考虑缩小 cache 或扩盘。

2026-06-08 17:10 Web 卡顿巡检补充：
- Web 边缘到云 Web API `100.107.220.127:8000` 约 `0.51-0.55s`，该基线主要用于回滚、`web-test` 与 `assets` 排障；当前正式 API 公网入口是 `api.aivison.it.com`。
- 最近 30 分钟窗口曾观测到约 `202` 次 499，集中在 `/api/tasks/{id}/result`、`/api/gallery/posts`、`/api/gallery/my-favorites`、`/api/users/history` 等等待型接口。
- `assets.aivison.it.com` legacy 回源曾在 30 分钟内出现约 `37` 次 upstream 异常；其中大量为 `upstream prematurely closed connection`，少量为 `upstream timed out`。
- `/minio/health/live` 返回 200 只能证明本地 MinIO 基础健康，不代表具体旧外链/人工回滚对象读取链路稳定；验收该链路必须测真实对象 URL 或至少统计 `assets` error.log。

2026-06-16 容量治理补充：
- 已安装并启用 `logrotate.timer`，备份原 `/etc/logrotate.d/nginx` 后移除 `delaycompress`，执行 `logrotate -f /etc/logrotate.d/nginx` 轮转并压缩现有 Nginx 日志。
- 同步执行 `journalctl --vacuum-size=100M` 和 `apt-get clean`；根盘从约 `37G used / 1.5G free / 97%` 降至约 `32G used / 6.3G free / 84%`。
- `web-test.aivison.it.com` 验证返回 200；`assets.aivison.it.com` 根路径返回 403 属预期，不代表具体旧外链/人工回滚对象不可读。
- 本轮未缩小 `minio_cache`。若需要继续释放空间，可将 `proxy_cache_path max_size` 从 `25g` 缩到约 `15g-16g`，预计释放约 `8G-10G`，代价是 legacy assets 回源流量和冷缓存延迟上升。

### 3.2 域名与路由

| 域名 | 边缘职责 | 当前 upstream |
| :--- | :--- | :--- |
| `web.aivison.it.com` | 已由 Cloudflare Pages `allbot-web-prod` 承接；VPS 只保留回滚副本 | 不经过 VPS；前端调用 `https://api.aivison.it.com/api` |
| `web-test.aivison.it.com` | 测试 Web 静态站；`/api/` 反代云测试 Web API | `http://100.82.124.91:8001` |
| `assets.aivison.it.com` | legacy MinIO 只读/兼容回源，仅用于人工回滚、旧外链和迁移排障；正式应用不再生成该域名 URL | `http://100.99.254.53:9000` |

不在 Web VPS 上的历史 Cloudflare canary 入口：

| 域名 | 承接方 | 说明 |
| :--- | :--- | :--- |
| `web.aivison.it.com` | Cloudflare Pages | 正式静态站，项目 `allbot-web-prod`，构建模式 `frontend npm run build:cf-prod` |
| `api.aivison.it.com` | Cloudflare Tunnel on `allbot-do-sgp1-control` | 正式 Web API 入口，回源 `http://100.107.220.127:8000` |
| `web-cf-test.aivison.it.com` | Cloudflare Pages | 历史 canary 静态站；如未配置，不作为当前测试入口 |
| `api-cf-test.aivison.it.com` | Cloudflare Tunnel on `allbot-do-sgp1-control` | 历史 canary API；如未配置，不作为当前测试入口 |

公网快照：

| URL | 状态 |
| :--- | :--- |
| `https://web.aivison.it.com` | 200，Cloudflare Pages |
| `https://api.aivison.it.com/api/health` | 200，正式 Web API |
| `https://web.aivison.it.com/api/health` | 返回 Pages SPA HTML；不再作为 API 健康检查 |
| `https://web-test.aivison.it.com` | 200 |
| `https://web-test.aivison.it.com/api/health` | 应返回测试 Web BFF health；502 时先查 `web-test` upstream 与云测试白名单 |
| `https://assets.aivison.it.com` | 根路径 403；这不等同于具体对象不可读，验收旧外链/人工回滚对象时必须测真实 object URL |

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
- 正式 `web.aivison.it.com` 不再通过 VPS `/api/` 反代；前端生产包必须使用 `VITE_API_BASE_URL=https://api.aivison.it.com/api`。
- 若回滚到 VPS `/root/dist`，`/api/` 才需要 `proxy_buffering off; proxy_cache off; chunked_transfer_encoding off;`，避免 SSE 和任务状态流被缓存或分块延迟。
- 测试 Web `/api/` 当前应回源云测试 Tailscale Web API `100.82.124.91:8001`。不要误指正式 `8000`。

### 3.4 发布与回滚

正式 Web 静态站当前通过 Cloudflare Pages 发布：

```bash
cd /home/hfy/APP/All_bot/frontend
npm run build:cf-prod
```

Cloudflare Pages 项目 `allbot-web-prod` 使用 Git 集成，生产分支 `deploy`，构建命令 `npm ci && npm run build:cf-prod`。VPS `/root/dist` 仅作为紧急回滚副本；需要回滚到 VPS 时才使用：

Cloudflare Pages 当前构建环境会按项目检测结果使用 Node 24 / npm 10（2026-06-28 实测为 `nodejs@24.13.1`、`npm@10.9.2`）。涉及 `frontend/package-lock.json`、Vite、Tailwind、optional/peer dependency 的前端发布，不能只用本机默认 npm 验证；推送 `deploy` 前先用 Pages 同款 npm 复现依赖安装和构建：

```bash
cd /home/hfy/APP/All_bot/frontend
npx -y npm@10.9.2 ci --progress=false
npx -y npm@10.9.2 run build:cf-prod
```

若 Pages 日志在 `npm clean-install --progress=false` 阶段报 `npm ci can only install packages when your package.json and package-lock.json or npm-shrinkwrap.json are in sync`，并出现类似 `Missing: @emnapi/runtime@1.11.1 from lock file`，说明 lockfile 对 npm 10 不完整。使用同版本 npm 只刷新 lockfile 后提交：

```bash
cd /home/hfy/APP/All_bot/frontend
npx -y npm@10.9.2 install --package-lock-only --progress=false
npx -y npm@10.9.2 ci --progress=false
npx -y npm@10.9.2 run build:cf-prod
```

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
- 改 `all_bot` 会影响 `assets.aivison.it.com` legacy 人工回滚/旧外链入口和正式 Web 回滚副本；当前正式 `web.aivison.it.com` 主流量不经过该 Nginx server。
- 改 `web-test.aivison.it.com` 只影响测试静态站和测试 `/api/`。
- 不要用 `systemctl restart nginx` 作为常规动作；优先 `nginx -t && nginx -s reload`。
- 不要删除 `/etc/letsencrypt`、`/root/dist`、`/root/dist-test`、`/etc/nginx/sites-available/*` 或备份目录。

### 3.5 容量处理建议

当前不建议在不了解访问高峰和 legacy 命中率的情况下直接清空缓存。推荐顺序：

1. 先备份 Nginx 配置与确认公网 health。
2. 核对 logrotate 是否安装并实际运行；当前应看到 `logrotate.timer` 为 enabled/active，若未运行，优先修复 logrotate。
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
| `web.aivison.it.com` 白屏或静态资源 404 | Cloudflare Pages 项目 `allbot-web-prod`、Pages 部署、custom domain、前端构建产物；不要优先查 VPS `/root/dist` |
| `api.aivison.it.com/api/health` 502/504 | 云机 Cloudflare Tunnel connector、public hostname、云 Web API `100.107.220.127:8000` |
| Web API 普遍慢但云内 health 毫秒级 | 比较 Cloudflare Tunnel 公网、云内 API、R2 公开域名/短签和前端串行请求；统计 499 高频端点 |
| `api-cf-test.aivison.it.com/api/health` 502 | 先查 Cloudflare Tunnel connector 是否在云机 active、public hostname 是否回源 `100.107.220.127:8000`；不要查 Web VPS Nginx |
| `web-cf-test.aivison.it.com` 白屏或 404 | 先查 Cloudflare Pages 部署、custom domain、构建产物和 `VITE_API_BASE_URL`；不要查 `/root/dist` |
| `web-test.aivison.it.com/api/health` 502 | 测试 Web API `100.82.124.91:8001` 是否运行、边缘 VPS Tailscale 是否在线；不要误改正式站 |
| legacy 旧外链或人工回滚媒体打不开/加载慢 | `assets.aivison.it.com` Nginx MinIO proxy、Tailscale 到 `100.99.254.53:9000`、真实 object URL；不要只看 `/minio/health/live` |
| `/api/tasks/{id}/result`、Gallery、History 大量 499 | 用户端等待过久断开；联动查 Web API R2 result timeout、R2 公开域名/短签、边缘公网延迟；若响应出现 `assets` URL，按 legacy 退出回归缺陷处理 |
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
- Cloudflare Pages/API Tunnel canary 入口创建、下线或升级为正式入口。
