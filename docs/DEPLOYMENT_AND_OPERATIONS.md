# 服务部署与运维操作指南 (Deployment & Operations Guide)

本文档旨在梳理当前 Bot 系统及 Dashboard 后台管理系统的服务开关、部署、重启以及日常运维的注意事项。本项目高度依赖 Docker Compose 进行容器化编排，所有服务的启停和更新均应通过标准的 Docker 指令完成。

---

## 一、 系统架构与部署环境

系统目前分为两个主要部署堆栈：
1. **Telegram Bot 堆栈**：分为生产环境 (`PROD`) 和测试环境 (`TEST`)，负责与用户交互并处理生成任务。
2. **Dashboard 堆栈**：包含 FastAPI 后端和 Vue 3 前端，用于管理员监控与干预。

它们共享底层的 PostgreSQL 数据库、Redis 缓存以及 MinIO 对象存储。

---

## 二、 服务启停与重建指令 (Docker Commands)

所有部署指令必须在 **项目根目录 (`/home/hfy/APP/All_bot`)** 下执行。

### 1. 正式服 Bot (Production)
当修改了 `src/` 下的核心逻辑，需要更新正式服时：
```bash
# 重启并强制重建镜像 (推荐)
docker-compose -f deploy/docker-compose.yml up -d --build bot

# 仅查看实时日志
docker logs -f tg-bot
```

### 2. 测试服 Bot (Test)
测试服主要用于新功能验证，与正式服数据隔离（通过 Redis 的 `test:` 前缀和不同的 Bot Token）：
```bash
# 重启并强制重建镜像
docker-compose -f deploy/docker-compose-test.yml up -d --build bot-test

# 查看测试服日志
docker logs -f tg-bot-test
```

### 3. 管理后台 (Dashboard)
Dashboard 的前后端通过独立的 Docker Compose 文件编排。

**一键重启并重建 (包含前后端)**:
```bash
docker-compose -f dashboard/docker-compose.yml up -d --build --force-recreate
```
*(注意：如果出现 `ContainerConfig` 相关的 Docker 网络或挂载报错，请先执行 `docker rm -f <容器名>` 删除旧容器后再重新启动。)*

**如果只修改了后端 (FastAPI)**:
```bash
docker-compose -f dashboard/docker-compose.yml up -d --build dashboard-backend
```

**如果只修改了前端 (Vue 3)**:
```bash
docker-compose -f dashboard/docker-compose.yml up -d --build dashboard-frontend
```

---

## 三、 服务开关与功能干预

### 1. 维护模式开关 (Maintenance Mode)
为了在不停机的情况下暂停接收新的生成任务（例如后端显卡服务器需要重启或更新模型时），我们在 Bot 中内置了维护模式。
*   **如何开启/关闭**: 管理员直接在 Telegram 中向 Bot 发送 `/maintenance` 指令。
*   **生效范围**: 开启后，普通用户尝试生成图片或视频时会被拦截并提示“⚠️ 服务器即将运维，暂停生成服务中”。但用户依然可以进行签到、查看个人中心等非生成操作。

### 2. 活动任务强制干预 (Active Tasks Refund)
如果遇到某些任务卡死在队列中，或者用户上传了违规素材但逃过了初步筛查，管理员可以通过 Dashboard 介入。
*   **操作路径**: 登录 Dashboard -> 首页监控 (Monitor) -> `Bot 活动任务池 (ActiveTasksTable)`。
*   **执行退款**: 点击对应任务的红色 `退款` 按钮。
*   **后台逻辑**: 该操作会调用后端的 `/api/system/refund_bot_task` 接口。它会自动从 Redis 中清除该任务，**释放该用户的并发锁**，并将扣除的灵石全额退还给该用户。

---

## 四、 重启与运维注意事项 (Precautions)

在进行系统升级或重启时，请务必注意以下几点：

### 1. 任务的平滑重启与退款机制
*   **自动退款**: Bot 在接收到正常的停机信号（`SIGTERM` / `docker stop`）时，会触发 `post_shutdown` 钩子。它会自动读取 Redis 中所有状态为 `pending` 或 `generating` 的任务，执行全额退款。
*   **强制杀进程的风险**: 如果使用 `docker kill` 或服务器直接断电，`post_shutdown` 将无法执行，可能导致用户灵石被扣但没拿到图，且并发锁未释放（导致用户无法发起新任务）。
*   **启动恢复补偿**: 为防止上述强制断电导致的数据不一致，Bot 在每次启动（`post_init`）时，会调用 `recovery_service.py` 扫描 Redis 中的滞留任务，进行状态清理或补偿退款。

### 2. 临时灵石清理 (Cron Jobs)
*   系统在 `bot_test.py` 中注册了 `clear_temp_credits_job`。它会在**每 48 小时的北京时间零点**自动执行。
*   如果重启服务，调度器的计时器可能会被重置，但它依然会寻找下一个最近的“明天零点”作为基准点，无需人工干预。

### 3. 数据一致性与对账
*   任何涉及“灵石”增减的代码修改（包括手动在数据库修改数据），**都必须**同步在 `user_logs` 表中插入对应的流水记录！
*   如果不插入 `user_logs`，将导致用户的 `users.credits` 余额与流水对不上账，严重影响后续的财务审计。
