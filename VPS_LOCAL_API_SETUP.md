# 自建 Telegram Local Bot API Server 部署指南

本文档记录了如何在一台全新的海外 VPS 上部署 Telegram 官方的 Local Bot API Server，以解决国内服务器使用商业 VPN 代理上传大文件（视频/图片）被 QoS 限速（如 300KB/s）的问题，实现跑满物理宽带上行（如 20MB/s）的满速传输。

## 1. 核心优势
- **突破速度瓶颈**：不再受限于商业 VPN 的单线程限速，利用 HTTP(s) 直连海外 VPS 跑满物理上行带宽。
- **突破文件大小限制**：将官方 API 默认的 50MB 文件上传限制提升至 **2000MB (2GB)**。
- **不影响现有内网穿透**：纯粹的应用层出站路由修改，与主机上运行的 Cloudflare Tunnel、阿里云反向代理等入站服务完美共存，互不干扰。

## 2. 准备工作
- **一台海外 VPS**：强烈建议购买带有 **CN2 GIA** 或 **AS9929** 优化线路的 VPS（如香港、东京、洛杉矶节点），这是单线程 TCP 跨国传输跑满 20MB/s 的物理基础。
- **Telegram API 凭证**：
  - 前往 [my.telegram.org](https://my.telegram.org) 申请。
  - 已获取的凭证：
    - **API_ID**: `33184502`
    - **API_HASH**: `10976e069756b3e09ef126f561df1e6f`

---

## 3. VPS 服务端部署步骤 (Server-side)

通过 SSH 登录到你的海外 VPS（使用 `root` 用户），依次执行以下步骤：

### 3.1 开启 TCP BBR 拥塞控制（关键网络优化）
用于在跨国高延迟网络下激进抢占带宽，榨干 20MB/s 的极限速度。
```bash
echo "net.core.default_qdisc=fq" >> /etc/sysctl.conf
echo "net.ipv4.tcp_congestion_control=bbr" >> /etc/sysctl.conf
sysctl -p
```
*检查：执行后无报错即表示 BBR 已启用。*

### 3.2 安装 Docker 环境
```bash
curl -fsSL https://get.docker.com | bash
```

### 3.3 一键启动 Local API Server 容器
使用开源社区维护的 `aiogram/telegram-bot-api` 镜像。请确保 VPS 的防火墙/安全组已开放 **8081** 端口的 TCP 访问。
```bash
docker run -d --restart=always -p 8081:8081 \
  --name telegram-bot-api \
  -v /var/lib/telegram-bot-api:/var/lib/telegram-bot-api \
  -e TELEGRAM_API_ID="33184502" \
  -e TELEGRAM_API_HASH="10976e069756b3e09ef126f561df1e6f" \
  -e TELEGRAM_STAT=1 \
  aiogram/telegram-bot-api:latest
```

### 3.4 配置缓存定时清理任务（防止 SSD 爆满）
Local API Server 会将所有收发的文件物理缓存在硬盘上且默认不清理。必须设置 Cron 定时任务来定期清理。
执行命令编辑定时任务：
```bash
crontab -e
```
在文件末尾添加以下行（每天凌晨 3 点清理 1 天前的文件）：
```bash
0 3 * * * find /var/lib/telegram-bot-api -type f -mtime +1 -exec rm -f {} \;
```
保存并退出即可。

### 3.5 验证服务端状态
在任意浏览器或终端访问：
```text
http://<你的VPS_公网IP>:8081
```
若返回 `{"ok":false,"error_code":404,"description":"Not Found"}`，则说明服务端部署成功。

---

## 4. 本地代码切换步骤 (Client-side)

回到本地的 Bot 项目代码（如 `src/bot_test.py` 或 `src/bot_prod.py`），修改 `python-telegram-bot` 的初始化配置，使其指向你刚建好的 VPS。

### 4.1 移除商业 VPN 代理
因为现在是通过普通 HTTP 直连你的 VPS，所以必须去除原有的科学上网代理配置。
在 `config.py` 中注释掉 `PROXY_URL`，或在 `bot_test.py` 中移除 `HTTPXRequest(proxy=...)`。

### 4.2 修改 Base URL
在 `ApplicationBuilder` 链式调用中，增加 `base_url` 和 `base_file_url`，指向你的 VPS。

```python
# src/bot_test.py 示例修改

app = (
    ApplicationBuilder()
    .token(token)
    # 增加以下两行，将请求打向海外 VPS 的 8081 端口
    .base_url("http://<你的VPS_公网IP>:8081/bot")
    .base_file_url("http://<你的VPS_公网IP>:8081/file/bot")
    
    # 确保移除之前的 .request(request) 代理挂载
    # .request(request)
    # .get_updates_request(request)
    
    .post_init(post_init)
    .post_shutdown(post_shutdown)
    .concurrent_updates(True)
    .build()
)
```

### 4.3 重启容器与验证
保存代码后，重启本地的 Bot 容器（如 `docker restart tg-bot-test`）。
此时，尝试在 Telegram 中触发一个大体积视频生成的任务。如果观察到上传进度不再受限于之前的 300KB/s，而是飞速飙升，说明架构切换已完美生效！
