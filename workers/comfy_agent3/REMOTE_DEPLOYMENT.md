# ComfyUI Agent 远程部署指南 (Worker Node)

本指南旨在指导如何将执行节点 (Agent/Worker) 部署到与主控服务器 (Master Node) 不同的网络环境或服务器上。

## 1. 前置要求

在部署 Agent 之前，请确保远程服务器满足以下条件：

- **操作系统**: 推荐 Linux (Ubuntu 22.04+)。
- **GPU 环境**: 
  - 已安装 NVIDIA 驱动。
  - 已安装 NVIDIA Container Toolkit (用于 Docker 支持 GPU)。
- **软件环境**:
  - 已安装 **Docker** 和 **Docker Compose**。
  - 已安装并运行 **ComfyUI Server** (通常监听 `8188` 端口)。
- **网络访问**:
  - 能够通过公网访问主控服务器的 API (端口 `8003` 或通过 Nginx 转发的 `443`)。
  - 能够通过公网访问主控服务器的 MinIO (端口 `9000` 或通过 Nginx 转发的 `443`)。

---

## 2. 部署步骤

### 2.1 获取代码
将主控服务器上的 `comfy_agent` 目录及其所有内容复制到远程服务器的任意目录（例如 `/opt/comfy_agent`）。

```bash
# 示例：从主控服务器同步代码 (根据实际情况修改路径)
# scp -r /home/ubantu/backend/comfy_agent user@remote_ip:/opt/comfy_agent
```

### 2.2 配置环境变量
进入 `comfy_agent` 目录，编辑 `.env` 文件。

```bash
cd /opt/comfy_agent
nano .env
```

**关键配置项说明：**

```bash
# --- 身份与 Master 关联 ---
AGENT_ID=remote_worker_01           # 必须唯一，建议包含地理位置或服务器名
SUPPORTED_TASK_TYPES=               # 留空表示接取所有类型任务，或指定如 "img2img,face_swap"

# 修改为主控服务器的公网 API 地址
MASTER_API_URL=https://api.yourdomain.com
AGENT_SECRET_TOKEN=super_secret_agent_token_2026

# --- 本地 ComfyUI 关联 ---
# Agent 与本地 ComfyUI 通信，保持默认即可
COMFY_API_URL=http://127.0.0.1:8188
COMFY_WS_URL=ws://127.0.0.1:8188/ws
COMFY_INPUT_DIR=/path/to/comfyui/input    # ComfyUI 的输入目录绝对路径
COMFY_OUTPUT_DIR=/path/to/comfyui/output  # ComfyUI 的输出目录绝对路径

# --- MinIO 配置 (Agent 通过公网读写 Master 的 MinIO) ---
# 修改为主控服务器的公网 MinIO 地址
MINIO_ENDPOINT=minio.yourdomain.com
MINIO_ACCESS_KEY=chuzeyu
MINIO_SECRET_KEY=@Cv1347968277
MINIO_SECURE=true                   # 如果主控使用 HTTPS (443)，必须设为 true
```

### 2.3 配置 Docker Compose
编辑 `docker-compose.yml`，确保数据卷映射正确。

```yaml
version: '3.8'
services:
  comfy-agent:
    build: .
    container_name: comfy-agent
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./workflows:/app/workflows
      # ！！！务必将宿主机的 ComfyUI 目录映射到容器内，且路径需与 .env 中配置一致 ！！！
      - /path/to/comfyui/input:/path/to/comfyui/input
      - /path/to/comfyui/output:/path/to/comfyui/output
    network_mode: "host" # 使用 host 模式以直接访问本地 127.0.0.1:8188
```

### 2.4 启动服务
```bash
docker compose up -d --build
```

---

## 3. 验证部署

### 3.1 查看日志
启动后，查看日志确认 Agent 是否成功连接到主控和 MinIO：

```bash
docker logs -f comfy-agent
```
**正常日志标志：**
- `MinIO client initialized` (MinIO 连接成功)
- `Connected to ComfyUI WebSocket` (本地 ComfyUI 连接成功)
- `Agent remote_worker_01 started polling...` (开始从主控拉取任务)

### 3.2 在主控端验证
在主控服务器或通过浏览器访问：
`https://api.yourdomain.com/system/status`

确认 `active_workers` 数量增加，且能够看到该远程 Agent 的注册信息（如果有相关接口）。

---

## 4. 故障排除

| 现象 | 可能原因 | 解决方法 |
| --- | --- | --- |
| Connection failed to master | 1. URL 错误 <br> 2. 主控防火墙未开放端口 | 1. 检查 `MASTER_API_URL` <br> 2. 在远程服务器尝试 `curl -I <URL>` |
| MinIO Connection Error | 1. 凭据错误 <br> 2. `MINIO_SECURE` 设置不匹配 | 1. 检查 `MINIO_ACCESS_KEY/SECRET_KEY` <br> 2. 如果是 HTTP，设为 `false`；HTTPS 设为 `true` |
| Task stuck at "running" | 1. ComfyUI 挂起 <br> 2. 显存溢出 | 1. 检查 ComfyUI 控制台日志 <br> 2. 检查宿主机显存占用 `nvidia-smi` |
| File Not Found (Input) | 1. 路径映射错误 <br> 2. 权限问题 | 1. 检查 `docker-compose.yml` 的 `volumes` <br> 2. 确保 ComfyUI 运行用户对 input 目录有读写权限 |
