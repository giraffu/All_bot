# 人民币支付 Cloudflare Tunnel 内网穿透架构梳理

目前系统中人民币支付（如易支付网关）的回调是通过 **Cloudflare Tunnel (Zero Trust)** 实现内网穿透的。这种方案不需要我们在服务器上开放任何入站端口（Inbound），也不需要购买公网 IP，即可安全地将本地的支付回调 API 暴露给公网。

## 1. 整体架构与数据流向

当用户支付成功后，第三方支付平台会向我们的公网回调地址发起请求，数据流向如下：

1. **支付平台/用户** ➡️ 发起 HTTPS 回调请求至公网域名 `rmb.aivison.it.com`。
2. **Cloudflare 边缘节点** ➡️ 接收公网请求（在此层提供 SSL 证书和 DDoS 防护）。
3. **Cloudflare Tunnel** ➡️ 通过本地主动发起的加密长连接，将请求下发至服务器本地的 `cloudflared` 守护进程。
4. **本地后端服务** ➡️ `cloudflared` 进程将 HTTP 请求转发至本地服务器的 `127.0.0.1:8021`（即 `payment-api` 服务）。

## 2. 核心组件与配置

- **本地回调服务 (`payment-api`)**：
  在 `deploy/docker-compose.yml` 中，`payment-api` 容器采用 `network_mode: "host"` 模式运行，这意味着 FastAPI 服务直接监听了宿主机的 `8021` 端口。
- **Cloudflare 客户端 (`cloudflared`)**：
  运行在服务器上的客户端程序，路径位于 `~/APP/All_bot/bin/cloudflared`。它负责主动向 Cloudflare 维持一条出站隧道。
- **隧道配置 (`config.yml`)**：
  配置文件位于 `~/.cloudflared/config.yml`。它的核心作用是路由匹配：
  ```yaml
  ingress:
    # 当请求域名为 rmb.aivison.it.com 时，转发给本地的 8021 端口
    - hostname: rmb.aivison.it.com
      service: http://127.0.0.1:8021
    # 兜底规则，其余请求返回 404
    - service: http_status:404
  ```

## 3. 针对国内网络的稳定性优化

因为国内服务器连接 Cloudflare 节点经常会遇到网络波动断联，系统特别做了一层代理优化：
`cloudflared` 启动时，被强制注入了本地代理环境变量（指向 `127.0.0.1:7890`）。这意味着隧道流量会先经过本地代理翻墙，再连接到 Cloudflare，从而保证了支付回调长连接的绝对稳定，避免漏单。

## 4. 服务管理与运维

为了保证隧道的高可用，这套穿透方案被封装成了 Linux 的 Systemd 后台服务：

- **服务名称**：`cloudflared-rmb-pay.service`
- **查看运行状态**：`systemctl status cloudflared-rmb-pay`
- **重启隧道**：`sudo systemctl restart cloudflared-rmb-pay`
- **查看隧道日志**：`journalctl -u cloudflared-rmb-pay -f`

**常见排障思路**：

- 如果公网访问报 **`502 Bad Gateway`**：说明隧道是通的，但是本地的 `payment-api` (8021端口) 服务挂了或没启动。
- 如果公网访问报 **`503 Service Unavailable`**：说明隧道断了，需要检查代理 (`7890`) 是否正常，或者 `cloudflared` 进程是否存活。

> 💡 **提示**：如果你需要修改公网域名或者本地转发的端口，只需修改 `~/.cloudflared/config.yml` 文件，然后执行重启服务命令即可生效。更详细的原始配置和报错说明可参考项目根目录的 `CLOUDFLARE_TUNNEL_GUIDE.md`。
