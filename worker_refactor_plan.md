# ComfyUI Worker 节点去重与容器化编排重构方案

## 1. 现状问题分析
根据代码静态分析报告，当前项目中存在严重的架构级代码重复问题。在 `workers/` 目录下，存在 5 个子目录（`comfy_agent1/` 至 `comfy_agent5/`），这 5 个目录的内容（包括 `agent_main.py`、`comfy_client.py`、`workflow_patcher.py` 及 JSON 工作流）是 **100% 物理拷贝**。

**当前带来的负面影响：**
- **维护成本极高**：每次更新工作流或修复 Agent 调度 Bug 时，都需要手动在 5 个目录中重复修改。
- **配置分散**：由于没有统一容器化编排，每个节点可能是独立在宿主机上使用 `nohup` 或 `screen` 启动，环境变量管理混乱。
- **扩展性差**：新增第 6 个节点时需要再次 Copy 整个目录。

## 2. 重构目标
**“代码抽象一份，实例通过 Docker 环境变量区分”**
遵循 DRY (Don't Repeat Yourself) 原则和微服务架构规范，将 5 个独立的硬编码目录整合为一个单一的 `comfy_agent` 模块，并通过 Docker Compose 和环境变量动态下发节点的差异化配置。同时实现 **存储无状态化** 与 **构建体积极简**。

---

## 3. 具体实施方案

### 步骤一：合并与清理冗余代码 (Code Consolidation)
1. 在 `workers/` 目录下创建一个新的通用目录 `workers/comfy_agent/`。
2. 将核心 Python 代码（`agent_main.py`、`comfy_client.py`、`workflow_patcher.py`）移动至新的 `comfy_agent/` 中。
3. **工作流全集并入**：提取 `comfy_agent1/` 至 `comfy_agent5/` 目录下 `workflows/` 的所有 JSON 文件，取其并集放入 `workers/comfy_agent/workflows/` 中，并手动剔除调试残留文件（如 `actual_prompt.json`）。
4. 删除 `workers/comfy_agent1/` 到 `workers/comfy_agent5/` 这 5 个重复目录。

### 步骤二：环境变量动态化 (Environment Variable Injection)
经过检查，`agent_main.py` 中已经预留了 `os.getenv()` 读取配置的接口，我们需要确保它们在 Docker 启动时由外部严格控制：
```python
# 核心区分节点身份与职责的参数
AGENT_ID = os.getenv("AGENT_ID", "worker_local_01")
SUPPORTED_TASK_TYPES = os.getenv("SUPPORTED_TASK_TYPES", "img2img,face_swap")
COMFY_API_URL = os.getenv("COMFY_API_URL", "http://127.0.0.1:8188")
COMFY_WS_URL = os.getenv("COMFY_WS_URL", "ws://127.0.0.1:8188/ws")
# 无状态存储目录
COMFY_INPUT_DIR = os.getenv("COMFY_INPUT_DIR", "/tmp/input")
COMFY_OUTPUT_DIR = os.getenv("COMFY_OUTPUT_DIR", "/tmp/output")
```

### 步骤三：编写 Docker Compose 编排文件 (Docker Compose Orchestration)
在 `workers/` 目录下创建一个专门用于 Worker 集群的编排文件 `workers/docker-compose.yml`。

**注意**：必须确保外层的 `../.env` 文件中已正确配置了全局依赖变量（如 `MASTER_API_URL`, `MINIO_ENDPOINT`, `AGENT_SECRET_TOKEN` 等），通过 `env_file` 统一注入。

使用 Docker Compose 的 YAML 锚点（Anchors `&`）和扩展（Extension `<<: *`）特性，避免重复定义：

```yaml
version: '3.8'

# 定义基础模板 (不会作为独立容器启动)
x-worker-base: &worker-base
  build: 
    context: ../
    dockerfile: workers/Dockerfile
  restart: always
  env_file:
    - ../.env
  network_mode: "host"
  volumes:
    - ../logs/workers:/app/logs
    # 不再挂载宿主机 input/output 目录，实现真正的无状态化

services:
  # Agent 1 (如专门负责跑 LTX 视频模型)
  comfy-agent-1:
    <<: *worker-base
    container_name: comfy-agent-1
    environment:
      - TZ=Asia/Shanghai
      - AGENT_ID=worker_01
      - SUPPORTED_TASK_TYPES=ltx_video,face_video
      - COMFY_API_URL=http://127.0.0.1:8188
      - COMFY_WS_URL=ws://127.0.0.1:8188/ws
      - COMFY_INPUT_DIR=/tmp/input
      - COMFY_OUTPUT_DIR=/tmp/output

  # Agent 2 (如专门负责跑 图片生成 模型)
  comfy-agent-2:
    <<: *worker-base
    container_name: comfy-agent-2
    environment:
      - TZ=Asia/Shanghai
      - AGENT_ID=worker_02
      - SUPPORTED_TASK_TYPES=img2img,face_swap,i2i_pro
      - COMFY_API_URL=http://127.0.0.1:8189
      - COMFY_WS_URL=ws://127.0.0.1:8189/ws
      - COMFY_INPUT_DIR=/tmp/input
      - COMFY_OUTPUT_DIR=/tmp/output

  # Agent 3 ... (依此类推)
```

### 步骤四：精简构建与专属 Dockerfile
1. 在 `workers/` 目录下新建 `worker_requirements.txt`，仅保留极轻量的 Worker 专属依赖：
   ```text
   httpx
   websockets
   minio
   python-dotenv
   asgi-correlation-id
   ```
2. 在 `workers/` 目录下新增 `Dockerfile`，确保环境隔离且体积精简：
```dockerfile
FROM python:3.10-slim

WORKDIR /app

# 仅拷贝轻量级依赖文件，极大提升构建速度
COPY workers/worker_requirements.txt .
RUN pip install --no-cache-dir -r worker_requirements.txt

COPY workers/comfy_agent /app/worker

# 设置 Python 寻址路径
ENV PYTHONPATH=/app

CMD ["python", "/app/worker/agent_main.py"]
```

## 4. 部署与验收流程
1. **平滑下线旧节点**：如果生产环境正在运行旧的 5 个 Agent，等待其任务队列清空后关闭进程。
2. **构建新镜像并启动集群**：
   ```bash
   cd workers
   docker-compose up -d --build
   ```
3. **验证中控注册**：通过 Dashboard 或 API 日志检查 `Central API` 是否成功接收到了 `worker_01` 到 `worker_05` 发来的心跳与能力注册信息（`SUPPORTED_TASK_TYPES`）。

## 5. 预期收益与核心优化点
- **代码行数 (LOC) 降低**：直接消除了约 `4000+` 行毫无意义的重复代码。
- **极速扩容**：如果在未来引入了新显卡（如 `:8193`），只需在 `docker-compose.yml` 复制 10 行配置即可启动新的 Worker 节点。
- **稳定性提升**：由 Docker 守护进程托管 Agent 的崩溃重启，替代传统 nohup。
- **存储彻底无状态化**：Agent 不再依赖并挂载宿主机磁盘来交换 ComfyUI 的输入输出图片，直接使用容器 `/tmp` 目录并在内存及 MinIO 间流转，告别磁盘堆积和权限报错。
- **构建体积极致优化**：取消了主项目 `src/` 和庞大 `requirements.txt` 的打包依赖，镜像体积缩减，构建速度实现秒级。