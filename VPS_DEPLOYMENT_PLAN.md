# 🌍 VPS 边缘节点部署实操指南

## 📍 节点信息核对
- **武汉服务器 (源站 Origin)** Tailscale IP: `100.99.254.53`
- **海外 VPS (边缘节点 Edge)** Tailscale IP: `100.88.57.122`

以下所有操作均在 **海外 VPS** 上通过 root 或 sudo 权限执行。

---

## 步骤一：安装 Nginx 与环境准备

1. **更新软件源并安装 Nginx**
   ```bash
   apt update && apt install nginx -y
   ```

2. **创建缓存与静态页面目录并赋权**
   ```bash
   # 创建 MinIO 媒体缓存目录
   mkdir -p /var/cache/nginx/minio_cache
   chown -R www-data:www-data /var/cache/nginx/minio_cache

   # 创建前端 Web 静态文件目录
   mkdir -p /var/www/all_bot_frontend
   chown -R www-data:www-data /var/www/all_bot_frontend
   ```

---

## 步骤二：配置 Nginx 核心代理与缓存

1. **创建并编辑站点配置文件**
   ```bash
   nano /etc/nginx/sites-available/all_bot
   ```

2. **填入以下配置 (请将 `yourdomain.com` 替换为你的真实域名)**：
   ```nginx
   # 1. 定义 MinIO 的缓存区 (分配 10GB 硬盘空间用于缓存视频和图片)
   proxy_cache_path /var/cache/nginx/minio_cache levels=1:2 keys_zone=minio_cache:10m max_size=10g inactive=7d use_temp_path=off;

   server {
       listen 80;
       server_name web.yourdomain.com assets.yourdomain.com; # 你的前端与文件域名
       
       # 1. 托管前端静态页面
       location / {
           root /var/www/all_bot_frontend;
           try_files $uri $uri/ /index.html; # Vue Router History 模式支持
       }

       # 2. 代理 API 请求到武汉 FastAPI
       location /api/ {
           # 转发到武汉服务器的 Tailscale IP
           proxy_pass http://100.99.254.53:8000/; 
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
           # 转发到武汉服务器的 Tailscale IP，9000 是 MinIO API 端口
           proxy_pass http://100.99.254.53:9000/bot-data/;
           
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

3. **启用配置并重启 Nginx**
   ```bash
   # 移除默认配置（可选，防止冲突）
   rm /etc/nginx/sites-enabled/default
   
   # 建立软链接启用新配置
   ln -s /etc/nginx/sites-available/all_bot /etc/nginx/sites-enabled/
   
   # 测试配置并重启
   nginx -t
   systemctl reload nginx
   ```

---

## 步骤三：前端打包与部署

1. **修改前端项目 `.env.production` (在你的开发机上操作)**：
   将接口和存储地址指向你的 VPS 域名（配置 SSL 后请使用 `https`）：
   ```env
   VITE_API_BASE_URL=http://web.yourdomain.com/api
   VITE_STORAGE_URL=http://web.yourdomain.com
   ```

2. **打包并上传到 VPS**：
   ```bash
   # 在前端项目目录下打包
   npm run build
   
   # 将 dist 目录内容上传到 VPS
   scp -r dist/* root@100.88.57.122:/var/www/all_bot_frontend/
   ```

---

## 步骤四：配置 SSL 证书 (推荐)

为域名开启 HTTPS，确保数据传输安全并解锁浏览器的部分高级特性。

```bash
# 安装 certbot
apt install certbot python3-certbot-nginx -y

# 自动配置 Nginx 的 SSL 证书 (按提示操作)
certbot --nginx -d web.yourdomain.com
```

---

## 步骤五：验证与测试

1. 浏览器访问 `http://web.yourdomain.com` (或 https)，确认 Vue 3 页面能秒开。
2. 尝试生成一张图片或视频。
3. 按 `F12` 打开浏览器开发者工具，切换到 `Network` (网络) 面板。
4. 找到请求媒体文件（如 `.mp4` 或 `.png`）的记录，查看 `Response Headers`。
5. 如果看到 `X-Cache-Status: HIT`，恭喜你，CDN 边缘缓存已生效，武汉服务器出口带宽已被完美保护！
