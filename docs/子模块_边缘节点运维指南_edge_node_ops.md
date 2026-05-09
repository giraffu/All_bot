# 子模块: 边缘节点运维与网络代理 (Edge Node Ops)

## 1. 目标与范围
本模块专项记录海外边缘节点（Edge Node, `100.88.57.122`）的运维规范，重点涵盖 Nginx 反向代理配置、对象存储（MinIO/S3）直传的预签名 URL 路由、大文件流式传输优化、跨域（CORS）控制及常见网络超时问题的排查与修复策略。

## 2. 核心架构与请求流向
由于核心后端服务与 MinIO 存储部署在国内无公网 IP 的物理机上，边缘节点承担着全球网络入口的重任，通过 Tailscale VLAN 将外部请求安全透传至国内：
- **静态资源托管**：托管前端 Vue 项目（`web.aivison.it.com`）。
- **动态 API 穿透**：将 `/api/` 路由透传至国内 Web API（`100.99.254.53:8000`）。
- **对象存储代理**：将 `assets.aivison.it.com` 的直传与下载请求透传至国内 MinIO（`100.99.254.53:9000`）。

## 3. Nginx 核心配置红线 (极度重要)

边缘节点 Nginx 配置 (`/etc/nginx/sites-available/all_bot`) 必须严格遵守以下规范，以防止预签名失效、跨域报错和传输超时。

### 3.1 对象存储 (MinIO/S3) 预签名代理规范
**绝对禁止在 `proxy_pass` 中包含 URI（包括尾部斜杠 `/`）**。
- **错误示例**：`proxy_pass http://100.99.254.53:9000/bot-data/;` 
  - *原因*：Nginx 会对包含 URI 的 `proxy_pass` 自动进行 URL Decode（如将 `%20` 还原为空格），这将破坏预签名 URL 严格的签名计算规则，导致上传中文或含特殊字符文件时必定报 `403 Signature Does Not Match`。
- **正确示例**：`proxy_pass http://100.99.254.53:9000;` 
  - *原理*：Nginx 将原封不动地透传 Raw URI。

### 3.2 大文件直传 (流式转发) 与弱网超时优化
处理大文件（如视频生成任务素材）的上传时，默认的缓冲机制会导致磁盘 IO 飙高和 Tailscale 连接超时（110/111 报错）。
- **必须关闭请求缓冲**：`proxy_request_buffering off;`
- **必须启用 HTTP/1.1**：关闭缓冲时必须搭配 `proxy_http_version 1.1;` 和 `proxy_set_header Connection "";`，以支持分块传输 (Chunked Transfer) 和长连接。
- **下载与缓存隔离**：对于下载和浏览请求，原有的响应缓冲 (`proxy_buffering on;`) 与静态缓存 (`proxy_cache`) 必须保留。

### 3.3 跨域 (CORS) 与实体限制控制
- **拒绝 Nginx 层兜底 CORS**：**坚决不要**在 Nginx 侧使用 `if ($request_method = 'OPTIONS')` 强行添加跨域头。这会导致同层级的 `proxy_set_header` 丢失。MinIO 默认已开启全局 CORS 支持，Nginx 仅需做纯粹的网络透传。
- **请求体大小限制**：在 `server` 块必须显式放开文件大小限制，解决 `413 Request Entity Too Large` 问题：`client_max_body_size 50m;`

## 4. 故障排查与恢复契约 (SOP)

| 故障现象 | 根本原因分析 (RCA) | 应急恢复指令/方案 |
| :--- | :--- | :--- |
| **上传特定文件（中文/空格）时 403** | 预签名 URL 在 Nginx 代理层被解码（URL Decode），导致与 MinIO 计算签名不一致。 | 去除 Nginx 对应 location 的 `proxy_pass` 尾部斜杠 `/`，然后 `nginx -s reload`。 |
| **Ajax 上传时控制台报 CORS 错误** | 实质是请求 403 导致，浏览器将非 200/预检失败一律作为 CORS 抛出，并非真的缺跨域头。 | 同上，解决 403 签名失效问题，CORS 报错将自动消失。 |
| **大文件上传卡死、110/111 超时** | Nginx `proxy_request_buffering` 开启导致边缘节点临时磁盘堆积，且引发 Tailscale 隧道拥堵断连。 | 针对直传路由补充 `proxy_request_buffering off; proxy_http_version 1.1;`。 |
| **上传小文件成功，大一点直接 413** | Nginx 默认 `client_max_body_size` 限制（通常为 1MB）。 | 在对应 server 块中配置 `client_max_body_size 50m;`。 |

## 5. 配置更新与发布流程
修改边缘节点 Nginx 配置时，属于零停机平滑更新：
1. **修改配置**：通过 SSH 或 SCP 修改 `/etc/nginx/sites-available/all_bot`。
2. **语法检查**：必须执行 `nginx -t`。
3. **平滑重载**：若检查通过，执行 `nginx -s reload`。现有的传输连接将继续被老 Worker 处理直至完成，新请求由新 Worker 接收。

## 6. 与其他子模块的关系
- 前端项目自动部署见 [运维指南与容器管理](./子模块_运维指南与容器管理_ops_deployment.md) 中的 `npm run deploy` 章节。
- 更多网络穿透原理与前端架构见 [网络暴露与代理穿透](./子模块_网络暴露与代理穿透_network_proxy.md)。
