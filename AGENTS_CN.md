# AI Agent 架构与开发指南 (AGENTS.md)

## 1. 项目概览与架构

本项目实现了一个具有“修仙”主题的 **Telegram Bot**，提供基于 AI 的图像和视频生成服务。架构采用分层设计，分离了接口处理、业务逻辑和基础设施集成。

### 1.1 架构图

```mermaid
graph TD
    User((User/Daoist)) <-->|Telegram API| TG[Telegram Bot Interface]
    
    subgraph "Application Layer (src)"
        TG -->|Updates| H[Handler Layer]
        H -->|Commands/Messages| R[Router/Dispatcher]
        
        subgraph "Service Layer"
            R -->|Auth & Quota| PS[Permission Service]
            R -->|Task Orchestration| TS[Task Service]
            TS -->|Queue/Status| IS[Image Service]
        end
        
        subgraph "Infrastructure Layer"
            IS -->|HTTP/REST| API[Backend API Client]
            PS -->|SQLAlchemy| DB[Database (PostgreSQL)]
            TS -->|File I/O| S[Storage/MinIO]
        end
    end
    
    subgraph "External Systems"
        API <-->|Generation Tasks| AI_Backend[AI Inference Server]
        S <-->|Assets| MinIO[MinIO Object Storage]
        DB <-->|Persistance| PG[PostgreSQL DB]
    end
```

### 1.2 核心组件

系统模块化为几个关键的“Agent”（逻辑组件）：

1.  **Interface Agent (Gateway)**：处理 Telegram 更新、会话管理和用户交互。
2.  **Permission Agent (Sect Elder)**：管理用户认证、“灵石”（积分）经济和“修炼境界”（等级）。
3.  **Generation Agent (Alchemist)**：编排 AI 任务（图生图、换脸、视频生成）。
4.  **Backend Connector Agent (Transmission)**：管理与 AI 后端的可靠通信。
5.  **Data Steward Agent**：处理数据持久化和日志记录。

---

## 2. Agent 职责与契约

### 2.1 Interface Agent (Gateway)
-   **代码库**: `bot_test.py`, `src/handlers/*`
-   **角色**: 所有用户交互的入口点。
-   **职责**:
    -   初始化 Telegram Application 并注册 Handler。
    -   解析传入的 `Update` 对象（文本、图片、视频、文件）。
    -   管理用户会话状态 (`context.user_data['mode']`)。
    -   根据当前模式（如 `MODE_FACESWAP`, `MODE_UNDRESS`）将请求路由到相应的服务。
    -   渲染 UI（回复键盘、内联按钮）。
-   **输入**: Telegram `Update` 对象。
-   **输出**: 用户反馈（消息、菜单）或对 Service Layer 的调用。

### 2.2 Permission Agent (Sect Elder)
-   **代码库**: `src/services/permission_service.py`, `src/quota.py`
-   **角色**: 看门人和经济管理者。
-   **职责**:
    -   **认证**: 验证用户是否为指定 Telegram 频道的成员 (`REQUIRED_CHANNEL_ID`)。
    -   **经济**: 管理“灵石”（积分）。扣除任务成本，发放签到/邀请奖励。
    -   **等级管理**: 根据活跃度计算用户境界（凡人 -> 练气期 -> 筑基期 -> 金丹期）。
    -   **邀请系统**: 追踪邀请并分发奖励。
-   **关键算法**:
    -   `calculate_user_priority`: 基于用户等级和每日使用量的动态优先级。
    -   `refresh_user_group`: 基于阈值（邀请数、签到数、生成数）自动晋升等级。

### 2.3 Generation Agent (Alchemist)
-   **代码库**: `src/services/task_service.py`
-   **角色**: 任务编排者。
-   **职责**:
    -   **预处理**: 将上传的文件保存到 `TMP_DIR`，验证输入。
    -   **任务提交**: 构建不同任务的 payload（Img2Img, FaceSwap, Video）。
    -   **监控**: 通过 `ImageService` 轮询任务状态。
    -   **后处理**: 下载结果，保存到本地/云端，发送给用户。
    -   **清理**: 删除临时文件。
-   **模式**:
    -   **快速任务**: 脱衣、自慰（单张图片 + 预设 Prompt）。
    -   **换脸**: 2步（人脸 + 身体）或随机模板。
    -   **视频**: 自定义文生视频或基于模板（如 "Doggy Style", "Blowjob"）。

### 2.4 Backend Connector Agent (Transmission)
-   **代码库**: `src/services/image_service.py`, `src/api_client.py`
-   **角色**: 可靠传输层。
-   **职责**:
    -   **协议**: HTTP/1.1 REST。
    -   **弹性**: 实现 **熔断器 (Circuit Breaker)**（后端宕机时快速失败）和 **异步重试 (Async Retries)**。
    -   **存储集成**: 在发送给后端之前从 MinIO 获取资源。
    -   **端点**: `img2img`, `face_swap`, `perfect_video_edit`, `perfect_video_insert`。

### 2.5 Data Steward Agent
-   **代码库**: `src/database/*`
-   **角色**: 持久化管理者。
-   **职责**:
    -   管理 SQLAlchemy 会话 (`AsyncSessionLocal`)。
    -   定义 Schema (`User`, `History`, `Referral`, `UserLog`)。
    -   记录每次积分变更的详细交易日志。

---

## 3. Agent 间通信

-   **模式**: 直接异步函数调用 (`await service.method()`)。
-   **状态共享**:
    -   **瞬态**: `context.user_data` (Telegram Bot Context) 用于多步流程（例如 FaceSwap 步骤 1 -> 步骤 2）。
    -   **持久态**: PostgreSQL 用于用户画像、积分和历史记录。
-   **外部**:
    -   **Bot <-> Backend**: HTTP 轮询（状态检查）。
    -   **Bot <-> MinIO**: S3 兼容 API。

---

## 4. 配置与环境

系统通过 `config.py` 使用 `.env` 变量进行配置。

### 4.1 关键环境变量

| 变量名 | 描述 | 默认值 / 示例 |
| :--- | :--- | :--- |
| `BOT_TOKEN_TEST` | Telegram Bot Token | `123456:ABC...` |
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql+asyncpg://...` |
| `API_BASE` | AI Backend 基础 URL | `http://192.168.1.226:8003` |
| `API_TOKEN` | Backend 认证 Token | `your_secure_token` |
| `MINIO_ENDPOINT` | MinIO 地址 | `192.168.1.115:9000` |
| `REQUIRED_CHANNEL_ID` | 强制加入的频道 ID | `-1001234567890` |
| `PROXY_URL` | 网络代理（可选） | `socks5://127.0.0.1:7890` |

---

## 5. 测试策略

### 5.1 单元测试模板
使用 `pytest` 和 `unittest.mock`。

```python
import pytest
from unittest.mock import AsyncMock, patch
from src.services.permission_service import PermissionService

@pytest.mark.asyncio
async def test_check_quota_sufficient():
    # Setup
    service = PermissionService()
    service.quota_manager.check_credits = AsyncMock(return_value=True)
    
    # Execute
    update = AsyncMock()
    context = AsyncMock()
    result = await service.check_quota(update, context, cost=2)
    
    # Assert
    assert result is True
```

### 5.2 集成测试
-   **数据库**: 使用单独的测试数据库或事务回滚。
-   **API**: Mock `httpx.AsyncClient` 以模拟 Backend 响应。

---

## 6. 部署与可观测性

### 6.1 部署步骤
#### 本地部署
1.  **前提条件**: Python 3.10+, PostgreSQL, MinIO, AI Backend。
2.  **安装依赖**: `pip install -r requirements.txt`。
3.  **设置 DB**: 运行迁移脚本（例如 `alembic` 或 `post_init` 中的 `init_db`）。
4.  **运行**: `python src/bot_test.py`。

#### Docker 部署与重启
如果使用 Docker 部署，为了让 Bot 服务应用最新代码并正常重启，必须先移除旧容器，然后重新构建镜像。

```bash
cd deploy

# 1. 停止并移除旧容器
docker-compose down
# (或者仅针对 bot 服务：docker-compose rm -fs bot)

# 2. 重新构建镜像并在后台启动新容器
docker-compose up -d --build
```

### 6.2 可观测性
-   **日志**:
    -   `UserLogger` (`src/logger.py`) 将以用户为中心的行为记录到文件。
    -   标准 `logging` 用于系统错误。
-   **指标**:
    -   队列大小（通过 `/queue` 命令）。
    -   用户统计（通过 `/profile` 或 `个人中心`）。

---

## 7. 安全与合规

### 7.1 访问控制
-   **基于角色**: 普通用户 vs 管理员（由配置/代码访问权限暗示）。
-   **看门人**: `check_access` 强制执行频道成员资格检查。

### 7.2 数据安全
-   **输入验证**: `_handle_template_contribution` 验证文件类型。
-   **隐私**: 提供私密生成模式（内联按钮 "私密"）。
-   **可追溯性**: 所有生成操作都记录在 `History` 表和 `UserLog` 中。

### 7.3 运维安全
-   **机密信息**: 所有敏感密钥都在 `.env` 中（不提交代码库）。
-   **熔断器**: 防止 Backend 过载时的级联故障。

---

## 8. 维护

**维护者**: 开发团队
**最后更新**: 2025-03-05

### 变更日志
-   **初稿**: 从源代码反向工程梳理出的架构。
