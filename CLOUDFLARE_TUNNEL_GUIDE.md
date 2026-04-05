# Cloudflare Tunnel 支付网关网络配置与运维指南

本文档记录了 `All_bot` 项目为了接入第三方人民币支付网关（`huanyuy`），而引入的 **Cloudflare Tunnel (Zero Trust)** 网络配置方案。

通过该方案，我们可以安全地将内网服务器的 `8021` 端口暴露给公网（即支付平台的回调服务器），而无需购买公网 IP 或配置复杂的路由器端口映射。

---

## 1. 架构与原理

### 1.1 数据流向
```mermaid
graph LR
    User[支付平台/用户] -->|HTTPS 请求| CF[Cloudflare 边缘节点]
    CF -->|加密长连接 Tunnel| CF_Daemon[本地 cloudflared 进程]
    CF_Daemon -->|HTTP 转发| Backend[本地 FastAPI 8021 端口]
```

### 1.2 核心组件
1. **Cloudflare 边缘节点**：负责接收公网的 HTTP/HTTPS 请求，提供 SSL 证书和 DDoS 防护。
2. **`cloudflared` 守护进程**：运行在我们服务器上的客户端（位于 `~/APP/All_bot/bin/cloudflared`）。它主动向 Cloudflare 发起出站连接（Outbound），因此不需要内网开放任何入站端口（Inbound）。
3. **本地后端服务**：运行在 `127.0.0.1:8021` 的后端 API（负责处理支付回调验签与发货）。
4. **代理网络 (VPN)**：由于中国大陆到 Cloudflare 节点可能存在网络波动，`cloudflared` 启动时配置了本地代理（`127.0.0.1:7890`）以确保长连接的稳定性。

---

## 2. 部署与配置详情

### 2.1 隧道信息
- **隧道名称**：`rmb-pay`
- **隧道 ID**：`9c0231eb-0d3f-4702-a5f2-338d71722141`
- **绑定的公网域名**：`rmb.aivison.it.com`
- **本地转发目标**：`http://127.0.0.1:8021`

### 2.2 核心配置文件
配置文件的默认位置为：`~/.cloudflared/config.yml`。
如果需要修改转发规则（例如后端端口从 `8021` 变了），请修改此文件：

```yaml
tunnel: 9c0231eb-0d3f-4702-a5f2-338d71722141
credentials-file: /home/hfy/.cloudflared/9c0231eb-0d3f-4702-a5f2-338d71722141.json

ingress:
  # 匹配指定的公网域名，转发到本地 8021 端口
  - hostname: rmb.aivison.it.com
    service: http://127.0.0.1:8021
  # 兜底规则，未匹配的请求返回 404
  - service: http_status:404
```

*修改后需要重启 `cloudflared` 进程才能生效。*

---

## 3. 日常运维指南

### 3.1 验证隧道连通性
你可以通过公网请求测试连通性：
```bash
curl -I https://rmb.aivison.it.com/
```
如果返回 `HTTP/2 404` 或你后端 `8021` 服务的响应，说明公网到本地的链路已经打通。

### 3.2 常见报错说明
| 报错日志 | 原因与处理 |
| :--- | :--- |
| `WRN The user running cloudflared process has a GID...` | 权限警告，提示当前用户无权发送 ICMP(ping) 包。**完全可以忽略**，我们只用 HTTP 代理，不用 ICMP 代理。 |
| `failed to sufficiently increase receive buffer size` | UDP 缓冲区偏小警告。Linux 默认限制，**对低并发支付回调无影响，可以忽略**。 |
| `Connection reset by peer` / `Timeout` | 隧道与 CF 节点断开连接。检查代理 (`127.0.0.1:7890`) 是否正常工作。 |
| 公网访问报 `502 Bad Gateway` | 隧道通了，但 `cloudflared` 连不上 `127.0.0.1:8021`。请检查本地 FastAPI 服务是否挂了。 |
| 公网访问报 `503 Service Unavailable` | 隧道本身断了。请检查 `cloudflared` 进程是否还在运行。 |

---

## 4. 生产环境守护进程 (已部署)

目前隧道已经注册为 **Systemd 系统服务**，实现了开机自启和崩溃自动重启，并注入了全局代理环境变量以保证网络稳定性。

### 4.1 服务信息
- **服务名称**：`cloudflared-rmb-pay.service`
- **服务文件路径**：`/etc/systemd/system/cloudflared-rmb-pay.service`

### 4.2 常用运维命令
- **查看运行状态**：`systemctl status cloudflared-rmb-pay`
- **重启隧道服务**：`sudo systemctl restart cloudflared-rmb-pay`
- **停止隧道服务**：`sudo systemctl stop cloudflared-rmb-pay`
- **查看实时日志**：`journalctl -u cloudflared-rmb-pay -f`

### 4.3 Systemd 配置备份
`/etc/systemd/system/cloudflared-rmb-pay.service` 的配置内容如下，供后续维护参考：
```ini
[Unit]
Description=Cloudflare Tunnel for RMB Pay
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=hfy
Group=hfy
Environment="http_proxy=http://127.0.0.1:7890"
Environment="https_proxy=http://127.0.0.1:7890"
Environment="all_proxy=http://127.0.0.1:7890"
ExecStart=/home/hfy/APP/All_bot/bin/cloudflared tunnel run rmb-pay
Restart=always
RestartSec=5
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
```
