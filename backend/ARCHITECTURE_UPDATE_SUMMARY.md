# 后端架构更新总结文档

本文档总结了近期将单体紧耦合架构升级为**分布式 Agent 架构**的全部核心更新内容。该升级实现了主控节点与任务执行节点的彻底解耦，并为未来的多机集群部署打下了基础。

## 一、 架构核心变更

1. **去中心化解耦**
   - **旧架构**：FastAPI 主控服务与后台 Worker 运行在同一个进程/机器中，直接通过本地文件系统共享输入图片和输出结果。
   - **新架构**：主控服务降级为纯粹的“API 网关”与“任务调度中心”。任务的实际执行被剥离到一个完全独立的 Python 项目 `comfy_agent` 中。Agent 通过 HTTP 主动轮询网关获取任务。

2. **存储流转云端化 (MinIO)**
   - 彻底废弃了通过 `comfy_input_dir` 和 `comfy_output_dir` 进行的本地磁盘文件共享。
   - **上传链路**：用户上传的图片由主控节点直接推送到 MinIO 的 `comfyui-input` 桶。
   - **执行链路**：Agent 领到任务后，从 `comfyui-input` 桶下载图片并提供给同机的 ComfyUI 处理。
   - **结果链路**：Agent 监听到 ComfyUI 渲染完成后，通过 ComfyUI 的 `/view` API 获取结果字节流，并直接上传到 MinIO 的 `comfyui-temp` 桶，最后通知主控。

---

## 二、 具体的代码与文件变更

### 1. 主控节点 (`backend-api`) 变更
- **新增接口**：创建了 `app/routers/agent.py`，暴露了三个供 Agent 调用的接口：
  - `GET /api/agent/task/pop`：主动拉取任务。
  - `POST /api/agent/task/status`：上报任务执行进度（支持 0-100% 进度和运行状态）。
  - `POST /api/agent/task/complete`：上报任务完成，并传递 MinIO 上的结果路径。
- **文件上传重构**：修改了 `app/main.py` 中的 `save_upload_file` 函数，实现文件纯内存流转并直接上传至 MinIO，抛弃了本地落盘逻辑。
- **文件下载重构**：修改了 `/image/{task_id}` 和 `/video/{task_id}` 接口，当用户查询结果时，主控直接从 MinIO 下载临时文件并返回。
- **清理旧代码**：完全删除了主控端的老旧代码 `worker.py`、`websocket_listener.py` 和 `comfy_client.py`。
- **配置清理**：在 `app/config.py` 和 `docker-compose.yml` 中移除了 ComfyUI 的直连配置以及不必要的本地 Volume 挂载。

### 2. 独立执行节点 (`comfy_agent`) 新增
- **新建独立项目**：在项目根目录创建了独立的 `comfy_agent` 目录。
- **核心模块**：
  - `agent_main.py`：核心守护进程，负责轮询主控、拉取图片、分发给 ComfyUI、监听 WebSocket 进度，以及上传结果至 MinIO。
  - `workflow_patcher.py`：负责将动态参数注入到 ComfyUI 的 API JSON 模板中。
  - `comfy_client.py`：封装了对本地 ComfyUI 的 HTTP 调用（修复了图片上传的 Multipart MIME 格式要求）。
- **Docker 化**：编写了专属的 `Dockerfile` 和 `docker-compose.yml`，支持一键拉起，且使用 `network_mode: "host"` 方便连接本机的 ComfyUI 服务。

---

## 三、 已解决的重点 Bug 与优化

1. **循环依赖问题**
   - **现象**：`app/main.py` 与 `app/routers/agent.py` 互相引入导致 Uvicorn 无法启动。
   - **解决**：在路由层重新定义了 Redis 的依赖注入，打断了交叉引用。
2. **ComfyUI 500 上传报错**
   - **现象**：Agent 尝试将下载的图片推给 ComfyUI 时报 500 错误。
   - **解决**：由于新架构采用了严格的文件流传输，修复了 HTTP 客户端的表单格式，显式声明了 `type="input"` 字段和 `"image/png"` MIME 类型。
3. **僵尸任务导致活跃 Worker 显示异常**
   - **现象**：前端显示有 5 个活跃节点，但实际只有一个。
   - **解决**：这是由于容器频繁重启导致任务卡在 Redis 的 `running` 集合中。手动清理了 Redis 的僵尸数据，并优化了 `main.py` 中 `/system/status` 接口的显示逻辑，避免给用户造成误导。
4. **Agent 读取结果失败**
   - **现象**：ComfyUI 渲染成功，但 Agent 报错找不到文件。
   - **解决**：重构了获取结果的逻辑，Agent 不再依赖读取本地 `/output` 文件夹，而是通过 ComfyUI 的 `/view` API 跨网络直接拉取字节流。

---

## 四、 遗留说明与未来扩展

- **前端透明**：本次升级严格遵守了网关模式，所有的用户端/Bot 端 API（如下单、查进度、取图片）均保持原样，**外部调用方无需做任何代码修改**。
- **横向扩展 (Scale Out)**：现在的架构已经完美支持多机部署。如果要增加算力，只需要在新的带有显卡的服务器上安装 ComfyUI，把 `comfy_agent` 目录拷过去，修改 `.env` 指向主控的公网 IP 即可，无需拷贝整个后端代码。
- **任务优先级**：Redis 的 `ZSET` 优先级队列机制（Priority Acceleration）在更换架构后依然完全保留且正常生效。