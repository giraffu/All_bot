# 项目概述与AI开发指南 (AGENTS.md)

这份文档旨在帮助AI助手快速理解本项目架构、技术栈及部署流程，以便进行代码维护和功能开发。

## 1. 项目简介
本项目是一个全栈管理后台系统（Dashboard），用于管理TeleBot应用的用户、统计数据、模版贡献及系统监控。项目采用前后端分离架构，并进行容器化部署。

## 2. 技术栈架构

### 2.1 前端 (Frontend)
- **路径**: `frontend/`
- **框架**: Vue 3 + Vite
- **UI组件库**: Ant Design Vue 4.x
- **样式**: Tailwind CSS
- **图表库**: Apache ECharts (通过 `vue-echarts` 集成)
- **网络请求**: Axios
- **部署**: Nginx (监听端口 `8085`)
- **关键文件**:
  - `vite.config.js`: 构建配置
  - `src/api/api.js`: API 接口定义
  - `src/components/`: 业务组件

### 2.2 后端 (Backend)
- **路径**: `backend/` (及项目根目录 `src/` 模块)
- **框架**: FastAPI (Python)
- **数据库**: PostgreSQL (SQLAlchemy ORM + asyncpg)
- **对象存储**: MinIO (用于图片/视频存储)
- **认证**: OAuth2 with Password Flow (JWT)
- **运行**: Gunicorn + Uvicorn Worker (监听端口 `8043`)
- **关键文件**:
  - `backend/main.py`: 应用入口及路由定义
  - `backend/auth.py`: 认证逻辑
  - `backend/requirements.txt`: 依赖列表
- **依赖关系**: 后端代码依赖于父级目录中的 `src` 模块 (Bot核心逻辑)，构建时需要上级目录上下文。

## 3. 部署与更新流程 (重要)

本项目使用 **Docker Compose** 进行容器化部署，且使用 `network_mode: "host"` 模式，服务直接共享宿主机网络栈。

### 3.1 容器服务
- **dashboard-frontend**: Nginx服务，承载Vue前端构建产物，反向代理API请求到后端。
- **dashboard-backend**: Python后端服务，提供API接口。

### 3.2 代码更新与部署指南
**注意：代码修改后，必须移除旧容器并重新构建容器才能生效。仅重启容器 (`docker restart`) 是无效的，这会导致修改不生效！**

请遵循以下步骤进行更新：

1.  **修改代码**: 完成前端或后端代码的修改。
2.  **重建并更新容器**:
    在 `dashboard/` 目录下执行以下命令：

    ```bash
    # 方法一：完全重建所有服务 (推荐)
    docker-compose down
    docker-compose up -d --build

    # 方法二：仅更新特定服务 (例如仅更新后端)
    docker-compose stop dashboard-backend
    docker-compose rm -f dashboard-backend
    docker-compose up -d --build dashboard-backend
    ```

### 3.3 环境配置
- 环境变量通过 `docker-compose.yml` 及 `.env` 文件注入。
- 数据库连接字符串及 MinIO 配置在 `docker-compose.yml` 中定义。

## 4. 开发注意事项
- **API 代理**: 前端开发环境 (`vite.config.js`) 和生产环境 (`nginx.conf`) 均配置了 `/api` 前缀的代理，指向后端服务。
- **跨域 (CORS)**: 后端 `main.py` 配置了 CORS 中间件，允许跨域请求（生产环境建议限制来源）。
- **静态资源**: 图片和视频资源通过 MinIO 的预签名 URL (Presigned URL) 提供访问，不直接通过本地文件系统服务。
