# 后端系统技术报告

## 1. API 接口文档

本系统基于 RESTful 风格设计，采用 OpenAPI 3.0 标准。所有接口均通过 HTTP/HTTPS 协议访问。

### 1.1 通用说明

- **基础路径**: `/`
- **认证方式**: Bearer Token (Header: `Authorization: Bearer <token>`)
- **数据格式**: 请求体支持 `multipart/form-data` (用于文件上传) 和 `application/json`。响应体默认为 `application/json`。

### 1.2 核心接口详解

#### 1.2.1 图生图任务 (Image to Image)

- **路径**: `/comfy_img2img`
- **方法**: `POST`
- **描述**: 上传一张参考图和提示词，生成新的图像。（注：如果上传的图片最长边超过 768 像素，系统会自动等比缩放到 768 像素，并调整长宽为 4 的倍数。）
- **请求参数 (multipart/form-data)**:
  - `image` (File, 必填): 参考图像文件。
  - `prompt` (String, 必填): 生成提示词。
  - `priority` (Integer, 选填): 任务优先级，默认 0。系统内部采用公式 `score = time.time() - (priority * 60)` 作为排序分数，即每提升 1 个优先级等级，相当于在队列中提前排队了 60 秒。数字越大优先级越高。
- **响应示例**:
  ```json
  {
    "task_id": "d633584f-10ac-4683-86e4-8a044f3cb2f8"
  }
  ```

#### 1.2.2 人脸替换任务 (Face Swap)

- **路径**: `/face_swap`
- **方法**: `POST`
- **描述**: 将源人脸替换到目标身体图像上。
- **请求参数 (multipart/form-data)**:
  - `face_image` (File, 必填): 提供人脸的源图像。
  - `body_image` (File, 必填): 提供身体的目标图像。
  - `priority` (Integer, 选填): 优先级。
- **响应示例**:
  ```json
  {
    "task_id": "9107570e-cf35-4d42-8ea2-9c4070e9811b"
  }
  ```

#### 1.2.3 视频植入任务 (Video Insert)

- **路径**: `/perfect_video_insert`
- **方法**: `POST`
- **描述**: 将图像植入到视频生成流程中。
- **请求参数 (multipart/form-data)**:
  - `image` (File, 必填): 输入图像。
  - `prompt` (String, 必填): 提示词。
  - `width` (Integer, 默认 512): 视频宽度。
  - `height` (Integer, 默认 512): 视频高度。
  - `length` (Integer, 默认 81): 视频帧数/长度。
  - `priority` (Integer, 选填): 优先级。
- **响应示例**: 同上。

#### 1.2.4 视频编辑任务 (Video Edit)

- **路径**: `/perfect_video_edit`
- **方法**: `POST`
- **描述**: 基于图像和提示词编辑生成视频。
- **请求参数**: 同 "视频植入任务"。
- **响应示例**: 同上。

#### 1.2.5 文生图 Turbo 任务 (T2I Pornmaster Turbo)

- **路径**: `/api/v1/workflows/t2i-pornmaster-turbo`
- **方法**: `POST`
- **描述**: 文生图工作流，集成 Double checkpoints 与现实增强器。
- **请求参数 (application/json)**:
  - `prompt` (String, 必填): 生成提示词，长度 1-512。
  - `priority` (Integer, 选填): 任务优先级，默认 0。
- **查询参数**:
  - `async` (Boolean, 默认 true): 是否异步执行。若为 `false`，则同步阻塞等待结果（超时 60s）。
  - `priority` (Integer, 选填): 优先级。若 JSON 中也存在，则以 JSON 为准。
- **响应示例**:
  ```json
  {
    "task_id": "893c8340-96f3-469a-9e22-861f60049f57",
    "image_url": "http://192.168.1.115:9000/comfyui-temp/comfyui_00001_.png"
  }
  ```
- **cURL 示例**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/workflows/t2i-pornmaster-turbo?async=false" \
       -H "Authorization: Bearer <token>" \
       -H "Content-Type: application/json" \
       -d '{"prompt": "一張來自日本90年代Tokyo-Hot色情片中的一位可愛18歲日本女性照片"}'
  ```
- **前端调用示例 (JavaScript)**:
  ```javascript
  const response = await fetch('/api/v1/workflows/t2i-pornmaster-turbo', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ prompt: 'your prompt here' })
  });
  const data = await response.json();
  console.log('Task ID:', data.task_id);
  ```

#### 1.2.6 查询任务状态 (V1)

- **路径**: `/api/v1/tasks/{task_id}`
- **方法**: `GET`
- **描述**: 获取任务详情，包括生成图片的 URL。
- **响应示例**:
  ```json
  {
    "status": "done",
    "queue_pos": null,
    "progress": 1.0,
    "result_path": "comfyui_00001_.png",
    "image_url": "http://192.168.1.115:9000/comfyui-temp/comfyui_00001_.png"
  }
  ```

#### 1.2.7 查询任务状态 (Legacy)

- **路径**: `/status/{task_id}`
- **方法**: `GET`
- **描述**: 获取任务的当前状态、队列位置及进度。
- **响应示例**:
  ```json
  {
    "status": "done",
    "queue_pos": null,
    "queue_remaining": 0,
    "progress": 1.0,
    "error": null,
    "result_path": "ComfyUI_00001_.png"
  }
  ```
- **状态码定义**:
  - `pending`: 排队中
  - `running`: 执行中
  - `done`: 已完成
  - `error`: 失败

#### 1.2.8 获取结果文件

- **路径**: `/image/{task_id}` 或 `/video/{task_id}`
- **方法**: `GET`
- **描述**: 下载任务生成的图片或视频文件。系统采用**云端优先/回退机制**：主控节点会直接从 MinIO 对象存储的 `comfyui-temp` 桶中下载文件并返回给用户。不再依赖本地磁盘共享。
- **错误处理**:
  - `404 Not Found`: 文件在 MinIO 中不存在或任务未完成。

#### 1.2.9 系统状态

- **路径**: `/system/status`
- **方法**: `GET`
- **描述**: 获取系统整体运行状态，包括队列积压情况和活跃 Agent 数量。
- **响应示例**:
  ```json
  {
    "queue_size": 5,
    "queue_by_type": {
      "img2img": 2,
      "t2i-pornmaster-turbo": 3
    },
    "active_workers": 1,
    "comfy_online": true
  }
  ```

#### 1.2.10 Agent 内部接口 (仅供 Agent 调用)

- **路径**: `/api/agent/task/pop` | `POST /api/agent/task/status` | `POST /api/agent/task/complete`
- **描述**: 支撑分布式架构的核心接口。其中 `/pop` 接口支持 `types` 查询参数（逗号分隔），允许 Agent 根据自身硬件配置或预装模型，定向接取特定类型的任务。

***

## 2. 系统架构设计文档

### 2.1 技术栈选型

- **编程语言**: Python 3.10
- **Web 框架**: FastAPI (高性能异步框架)
- **分布式 Agent**: `comfy_agent` (独立项目，负责任务执行与 ComfyUI 交互)
- **应用服务器**: Uvicorn (ASGI)
- **消息队列/缓存**: Redis 7.0 (用于任务调度、状态同步、Worker 注册)
- **对象存储**: MinIO (核心存储组件，实现主控与 Agent 之间的文件流转)
- **AI 引擎**: ComfyUI (基于 Stable Diffusion 的节点式工作流引擎)
- **容器化**: Docker & Docker Compose

### 2.2 架构设计 (分布式 Agent 模型)

```mermaid
graph TD
    User[用户/前端] -->|HTTP请求| API[API Gateway (FastAPI)]
    API -->|1. 任务写入| Redis[(Redis Queue)]
    API -->|2. 图片直传| MinIO[(MinIO Object Storage)]
    
    subgraph Execution Node (Agent Server)
        Agent[comfy_agent]
        ComfyUI[ComfyUI Server]
    end
    
    Agent -->|3. 轮询 Pop Task| API
    Agent -->|4. 下载 Input| MinIO
    Agent -->|5. 提交执行 (HTTP)| ComfyUI
    ComfyUI -->|6. 渲染结果| Agent
    Agent -->|7. 上传结果| MinIO
    Agent -->|8. 回传 Status/Complete| API
    
    User -->|轮询状态/下载| API
    API -->|9. 从云端获取结果| MinIO
```

### 2.3 核心机制

1. **分布式 Agent 架构**: 实现主控 (`backend-api`) 与执行端 (`comfy_agent`) 的彻底解耦。主控仅负责 API 路由、任务调度和结果分发；Agent 运行在 GPU 机器上，负责具体的渲染工作。
2. **异步任务调度**: 采用 Redis `Sorted Set` 实现优先级队列 (`comfy:queue:pending`)。Agent 通过 `GET /api/agent/task/pop` 接口主动拉取任务。该接口支持按任务类型过滤（通过 `types` 参数），实现了任务的定向路由。
3. **状态同步机制**: Agent 内部集成 WebSocket 监听 ComfyUI 执行进度，并通过 `POST /api/agent/task/status` 定时回传给主控，主控将状态映射回 Redis (`comfy:task:{id}`) 供用户查询。
4. **云端文件流转 (MinIO)**: 
   - **上传**: 主控接收用户文件后，直接通过 `boto3` 流式上传至 MinIO，不经过本地磁盘。
   - **下载**: Agent 领到任务后，按需从 MinIO 下载输入图片。
   - **结果**: Agent 渲染完成后，通过 ComfyUI `/view` API 获取字节流并上传至 MinIO `comfyui-temp` 桶，随后通知主控完成任务。
5. **工作流补丁 (Patching)**: Agent 维护 JSON 格式的工作流模板，根据任务参数动态注入 Seed、Prompt 等字段，并处理图片上传至 ComfyUI 的 Multipart 逻辑。

### 2.4 安全防护

- **认证**: 基于 HTTP Bearer Token 的简单认证机制。
- **隔离**: 后端服务与 ComfyUI 通过 Docker 网络隔离，对外仅暴露 API 端口。
- **输入校验**: Pydantic 模型严格校验请求参数类型。

***

## 3. 潜在风险与故障排查指南

### 3.1 常见错误场景

| 错误现象             | 可能原因                                     | 排查/解决策略                                                                     |
| ---------------- | ---------------------------------------- | --------------------------------------------------------------------------- |
| **任务一直 Pending** | 1. Agent 未启动 2. Redis 任务堆积 3. 网络隔离 | 1. 检查 Agent 日志 `docker logs comfy-agent` 2. 检查 Redis 状态 3. 确保 Agent 能访问主控 IP |
| **任务 Error**     | 1. ComfyUI 离线 2. MinIO 上传/下载失败 3. 显存不足 | 1. 检查 ComfyUI 容器 2. 验证 MinIO 凭据 3. 查看 ComfyUI 控制台 |
| **结果下载 404**     | 1. Agent 未成功上传结果 2. 任务状态不同步 | 1. 检查 Agent 端的 `POST /task/complete` 调用是否成功 2. 确认 MinIO 桶权限 |
| **循环依赖报错** | 主控路由与 main.py 交叉引用 | 检查 `app/routers/agent.py` 是否正确使用依赖注入，避免直接 import main 实例 |

### 3.2 监控告警规则 (建议)

- **队列堆积**: 当 `queue_size > 20` 持续 5 分钟 -> 告警 (需扩容 ComfyUI 节点)。
- **Worker 存活**: 监听 `/system/status`，若 `active_workers == 0` 且队列不为空 -> 告警。
- **错误率**: 单位时间内 `status=error` 的任务比例超过 10% -> 告警。

***

## 4. 功能扩展规范

### 4.1 添加新功能模块流程

1. **准备工作流**: 在 ComfyUI 前端搭建并调试好工作流，导出为 **API Format (JSON)** (注意不是 Workflow 格式)。
2. **保存模板**: 将 JSON 文件命名为 `xxx.json` 放入 `backend/workflows/` 目录。
3. **配置映射 (可选)**: 在 `app/worker.py` 的 `load_workflow` 方法中添加类型映射，或更新 `mappings.json` 以精确控制参数替换逻辑。
4. **定义模型**: 在 `app/models.py` 的 `TaskType` 枚举中添加新类型。
5. **添加接口**: 在 `app/main.py` 添加对应的 `POST` 路由 endpoint。

### 4.2 数据库/缓存迁移

- 当前使用 Redis 作为临时状态存储，数据由 TTL (24小时) 自动过期，无持久化强需求。
- 若需升级为持久化存储 (MySQL/PG)，需引入 SQLAlchemy/Tortoise-ORM，并编写 Alembic 迁移脚本。

### 4.3 灰度发布

- 利用 Docker 部署多套 Backend + ComfyUI 环境 (如 `prod` 和 `stage`)。
- 通过 Nginx 反向代理基于 Header 或流量权重分发请求。

***

## 5. 运维操作手册

### 5.1 服务启停

```bash
# 1. 启动主控服务 (backend-api)
cd /home/ubantu/backend
docker compose up -d

# 2. 启动执行节点 (comfy_agent)
cd /home/ubantu/backend/comfy_agent
docker compose up -d

# 停止所有服务
docker compose -f /home/ubantu/backend/docker-compose.yml -f /home/ubantu/backend/comfy_agent/docker-compose.yml down
```

### 5.2 日志查看

```bash
# 查看主控日志
docker logs -f backend-api-1

# 查看 Agent 日志
docker logs -f comfy-agent
```

### 5.3 配置文件更新

1. 修改 `/home/ubantu/backend/.env` (主控) 或 `/home/ubantu/backend/comfy_agent/.env` (Agent)。
2. 对于 Agent，可以通过 `SUPPORTED_TASK_TYPES` 环境变量（如 `img2img,face_swap`）指定其支持的任务类型。若留空则接取所有任务。
3. 重启对应容器。

***

## 6. 数据存储全景图

### 6.1 Redis 数据结构 (Schema)

| Key 模式                     | 类型     | TTL | 说明                                                          |
| -------------------------- | ------ | --- | ----------------------------------------------------------- |
| `comfy:task:{uuid}`        | Hash   | 24h | 存储任务详情 (status, params, result\_path, progress, error\_msg) |
| `comfy:queue:pending`      | ZSet   | -   | 等待队列。Member: task\_id, Score: 优先级权重 |
| `comfy:queue:running`      | Set    | -   | 运行中任务集合。用于故障恢复。 |
| `comfy:agent:workers`      | Set    | 1m  | 活跃 Agent 注册表 (Heartbeat)。 |

### 6.2 文件存储路径规划

| 存储类型 | 桶/目录名 | 说明 |
| --- | --- | --- |
| **MinIO (Input)** | `comfyui-input` | 存储用户上传的原始图片/视频。 |
| **MinIO (Temp)** | `comfyui-temp` | 存储 Agent 生成的最终结果和中间文件。 |
| **Local (Agent)** | `/input`, `/output` | Agent 容器内的临时缓存目录，与宿主机隔离。 |
| **Local (Workflows)** | `~/backend/workflows` | 业务逻辑模板文件 (主控与 Agent 同步)。 |

### 6.3 数据归档策略

- **定期清理**: 已部署自动化脚本 `/home/ubantu/backend/scripts/cleanup_files.sh`，用于清理 `Input`、`Output` 和 `Temp` 目录下超过 3 天的文件。
  - **Crontab 配置**: `0 3 * * * /bin/bash /home/ubantu/backend/scripts/cleanup_files.sh` (每天凌晨 3 点执行)
  - **日志记录**: 清理日志保存在 `/home/ubantu/backend/cleanup.log`。
- **结果保留**: 长期归档建议同步至对象存储 (S3/OSS)，或在清理脚本中排除特定重要文件。

