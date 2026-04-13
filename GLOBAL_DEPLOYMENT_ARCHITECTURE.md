# 🌍 全球化部署架构方案：武汉算力底座 + 海外 VPS 边缘节点

## 1. 架构背景与核心设计理念

针对当前系统“服务器在武汉（负责算力与存储），目标用户主要在海外或通过 VPN 访问”的现状，传统的纯国内穿透方案（如仅使用 Cloudflare Tunnel 暴露所有服务）会导致网页加载缓慢，且生成的动辄几十 MB 的视频文件在传输时会极度占用国内服务器宝贵的国际出口带宽。

本架构采用**“算力、存储与流量解耦”**的经典出海产品 CDN 架构：将高频的静态资源访问和媒体文件下载前置到海外 VPS（边缘缓存），而将重度的 GPU 渲染、数据库读写和文件源站保留在武汉本地。

---

## 2. 节点职责划分

### 📍 核心底座：武汉服务器 (源站 Origin)
*   **ComfyUI Workers (算力节点)**：负责消耗 GPU 算力，执行图像和视频的生成。
*   **MinIO (对象存储源站)**：负责持久化存储所有的输入源图、中间产物和生成的媒体文件。与算力节点在同一局域网，保证极低延迟。
*   **Web API (FastAPI)**：处理核心业务逻辑、并发锁、状态机和队列调度。
*   **PostgreSQL / Redis**：系统的唯一真实数据源与状态同步中心。

### 🌐 流量入口：海外 VPS (边缘节点 Edge)
*   **Vue 3 前端 (Web UI)**：直接在 VPS 上通过 Nginx 托管编译后的静态资源 (`dist`)，实现海外用户/VPN 用户的网页秒开。
*   **Nginx (反向代理 & 缓存中心)**：
    *   **API 转发**：将前端发起的 `/api` 请求安全加密地转发给武汉的 FastAPI。
    *   **文件缓存加速 (核心)**：拦截对 MinIO 的媒体文件请求，拉取一次后缓存在 VPS 本地硬盘/内存中，后续用户的下载和播放直接由 VPS 提供，实现**武汉服务器出口带宽“零”消耗**。
*   **Telegram Local API**：继续承担 Telegram Bot 的大文件传输中转（系统现有功能）。

---

## 3. 网络数据流向图

```text
[ 海外用户 / VPN 用户 ]
         │
         ▼ (公网高带宽连接)
┌────────────────────────────────────────────────────────┐
│                      海外 VPS 节点                     │
│                                                        │
│  1. Nginx 静态服务返回 Vue 页面 (秒开)                 │
│  2. Nginx 接收 /api 请求 ─────(代理转发)──────┐        │
│  3. Nginx 接收文件下载请求 ───(查找本地缓存)  │        │
│                                │ 未命中       │        │
└────────────────────────────────┼──────────────┼────────┘
                                 │              │
                    (加密安全隧道: Tailscale/WireGuard)
                                 │              │
┌────────────────────────────────┼──────────────┼────────┐
│                      武汉服务器底座            │        │
│                                │              │        │
│  ┌──────────────┐    ┌─────────▼────────┐     ▼        │
│  │ ComfyUI 算力 │◄───┤ MinIO (对象存储) ├──── FastAPI  │
│  └──────────────┘    └──────────────────┘     │        │
│                                            数据库/Redis │
└────────────────────────────────────────────────────────┘
```

---

## 4. 核心落地步骤与配置指南

### 步骤一：打通跨国安全内网 (虚拟局域网)
为了安全，武汉服务器的 FastAPI 和 MinIO 端口绝对**不要暴露在公网**。
*   **推荐方案**：在两台机器上安装 **Tailscale** 或 **WireGuard**。
*   **效果**：两台机器获得固定的虚拟内网 IP（例如 VPS 是 `10.0.0.1`，武汉是 `10.0.0.2`），所有的跨国传输均在底层自动加密。

### 步骤二：部署 Vue 3 前端到海外 VPS
在 VPS 上安装 Nginx，将前端打包后的 `dist` 目录放入 `/var/www/all_bot_frontend`。

### 步骤三：配置 VPS 上的 Nginx (核心缓存与路由代理)
这是整个架构的灵魂，在 VPS 的 Nginx 配置文件（如 `/etc/nginx/sites-available/all_bot`）中加入以下配置：

```nginx
# 1. 定义 MinIO 的缓存区 (分配 10GB 硬盘空间用于缓存视频和图片)
proxy_cache_path /var/cache/nginx/minio_cache levels=1:2 keys_zone=minio_cache:10m max_size=10g inactive=7d use_temp_path=off;

server {
    listen 80;
    listen 443 ssl;
    server_name web.yourdomain.com assets.yourdomain.com; # 你的前端与文件域名
    
    # SSL 配置略...

    # 1. 托管前端静态页面
    location / {
        root /var/www/all_bot_frontend;
        try_files $uri $uri/ /index.html; # Vue Router History 模式支持
    }

    # 2. 代理 API 请求到武汉 FastAPI
    location /api/ {
        # 假设 10.0.0.2 是武汉服务器的 Tailscale 内网 IP，8000 是 FastAPI 端口
        proxy_pass http://10.0.0.2:8000/; 
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # SSE (Server-Sent Events) 支持，防止进度条断开
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_buffering off;
        proxy_cache off;
    }

    # 3. 代理并缓存 MinIO 的媒体文件请求 (CDN 加速核心)
    location /bot-data/ {
        # 假设 10.0.0.2 是武汉服务器，9000 是 MinIO API 端口
        proxy_pass http://10.0.0.2:9000/bot-data/;
        
        # 启用缓存
        proxy_cache minio_cache;
        proxy_cache_valid 200 302 7d; # 成功响应缓存 7 天
        proxy_cache_valid 404 1m;     # 404 响应缓存 1 分钟
        
        # 增加缓存命中状态响应头，方便你 F12 调试是否命中缓存
        add_header X-Cache-Status $upstream_cache_status;
        
        # 优化大文件（视频）传输体验
        proxy_buffering on;
        proxy_ignore_headers Cache-Control Expires; # 强制忽略源站的防缓存头
    }
}
```

### 步骤四：修改前端环境变量
在前端的 `.env.production` 中，将 API 地址和文件加载地址统一指向你的 VPS 域名：
```env
VITE_API_BASE_URL=https://web.yourdomain.com/api
# MinIO 的 Presigned URL 生成时，需要让后端把域名替换为 VPS 的加速域名
VITE_STORAGE_URL=https://web.yourdomain.com
```

---

## 5. 方案优势总结

1.  **极致的用户体验**：用户访问网页和加载图片/视频的速度等同于直接访问海外 VPS，彻底告别国内服务器跨国访问的卡顿。
2.  **榨干武汉算力，保护国内带宽**：GPU 算力拉满的同时，生成的数十 MB 视频只需向海外传输**一次**，之后无数次的用户播放、下载都由 VPS 的 Nginx 缓存拦截，国内带宽压力骤降 99%。
3.  **安全性拉满**：武汉的核心服务器无需暴露任何公网端口，所有通信通过虚拟局域网（Tailscale/WireGuard）加密，彻底杜绝被恶意扫描和 DDoS 的风险。
4.  **架构扩展性强**：未来如果海外流量暴增，只需在 VPS 前面再套一层 Cloudflare CDN，或者增加多台海外 VPS 做负载均衡，而武汉的“算力+存储底座”完全不需要改动代码。
