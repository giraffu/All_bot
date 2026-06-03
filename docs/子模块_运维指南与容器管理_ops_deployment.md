# 子模块: 运维指南与容器管理 (Ops & Deployment)

## 1. 目标与范围
本模块记录当前仓库真实生效的部署顺序、迁移策略与常见故障恢复方式。最重要的事实更新有两点：
- 数据库迁移已经由 `safe_deploy.sh` 在宿主机上主动执行，不再依赖“容器下次启动自动迁移”。
- `web-api` 等服务若未挂载源码卷，代码变更后必须 `--build` 重建镜像才会生效。

## 2. 当前推荐部署路径
- 功能研发、联调、修复、配置调整：首选仓库根目录执行 `bash safe_deploy_test.sh`
- 正式发布、交付上线：仅在用户明确确认测试通过后，才执行 `bash safe_deploy.sh`
- 原因：脚本已经把以下步骤串成标准顺序：
  - 进入维护模式
  - 等待活跃任务清空
  - 清理僵尸任务与 Redis 锁
  - 检查 Alembic 多 head
  - 宿主机执行 `alembic upgrade head`
  - 重建 workers
  - 重建 central api
  - 重建主服务群
  - 重建 dashboard
  - 发布测试 Web 静态站到边缘 VPS
- `safe_deploy.sh` 到此结束，不会顺带重建测试环境。
- 若仅更新隔离测试栈，可执行 `bash safe_deploy_test.sh`；它会处理 `.env.test`、测试数据库迁移、测试 workers、测试 central api、测试入口服务，以及 `frontend/scripts/deploy-edge-test.sh` 对应的边缘 VPS 测试站静态资源发布；不会重建生产服务，也不会重建正式 Dashboard。

## 2.1 当前默认发布策略
- AI 在功能研发期间默认只能更新隔离测试环境，不得主动执行生产部署。
- “帮我改功能”“帮我修 Bug”“帮我联调”“帮我验证配置”这类请求，默认理解为测试环境操作。
- 只有在用户明确表达“上线”“发布”“部署正式环境”“交付生产”后，才允许切换到 `safe_deploy.sh` 或生产 compose。
- 在用户完成测试验收前，不得把测试环境变更直接同步到正式 Bot、正式 Web、正式 Payment、正式 Central API 或正式 Dashboard。

## 3. 当前真实迁移口径
- 迁移入口在 `safe_deploy.sh` 第 4 步。
- 脚本会先寻找可用的 Alembic 可执行文件，再检查 `heads` 数量。
- 一旦发现多个 head，脚本会直接中止，要求先合并 migration，而不是带病部署。
- 通过多 head 检查后，脚本会立即执行 `alembic upgrade head`。

这意味着知识库里以下旧说法都应删除：
- “等容器启动时自动迁移”
- “部署完新容器后再手动进容器跑 upgrade head 才是标准流程”

## 4. 服务重建注意事项
- `web-api`、`payment-api`、Dashboard、CS Bot 等通过镜像 `COPY` 代码的服务，修改代码后都要重建镜像，单纯 `restart` 不会拿到新代码。
- `workers` 更新环境变量时，应使用 `docker-compose up -d` 触发重新创建，而不是只做 `restart`。
- 当前仓库的测试环境与正式环境已经使用独立数据库；`safe_deploy_test.sh` 只会基于 `.env.test` 校验并迁移测试库，`safe_deploy.sh` 只会基于 `.env` 校验并迁移正式库，两套迁移应按各自环境分别执行，互不替代。
- 若启用隔离测试栈，应使用独立的 `.env.test`、`backend/docker-compose-test.yml` 与 `workers/docker-compose-test.yml`，并让测试入口服务指向独立的 Central API 端口与独立 Redis 队列。
- 隔离测试栈的最低要求是：测试 Bot/Web/Payment 使用测试库，Central API 使用独立 Redis DB 作为队列，测试 workers 连接测试 Central API；否则仍会与正式环境共用任务调度面。
- `workers/docker-compose-test.yml` 中的 `${...}` 插值不会读取 `env_file: ../.env.test` 的值；当前测试 compose 已让 `AGENT_SECRET_TOKEN` 从 `env_file` 注入，并将 `MINIO_INPUT_BUCKET` / `MINIO_RESULT_BUCKET` 默认到 `bot-data-test` / `comfyui-temp-test`。重建测试 worker 后仍要用 `docker exec <worker> env` 核对实际生效值，避免 401 或读写错误桶。
- `safe_deploy_test.sh` 里的测试 Web VPS 发布依赖宿主机可执行 `npm`，并通过 `frontend/scripts/deploy-edge-test.sh` 使用 SSH/SCP 把 `build:edge-test` 产物同步到边缘 VPS；若私钥缺失、`npm` 未安装或边缘域名不可达，脚本会中止而不是假装发布成功。

## 4.1 workflow 资产事实源
- 当前仓库同时存在 `backend/workflows` 与 `workers/comfy_agent/workflows`。Central API 的校验/镜像构建路径与 Worker 的实际执行路径可能不是同一个目录。
- 修改 workflow JSON、`mappings.json` 或 workflow patcher 时，必须先确认本次变更影响的是 Central 校验副本、Worker 执行副本，还是两者都影响。
- 新增/更新 workflow 的默认口径是以 Worker 实际执行目录 `workers/comfy_agent/workflows` 为运行时事实源；若 backend 仍需要本地校验副本，必须同步更新并在部署说明中写明同步依据。
- 若只重建 Central API 而未重建 Worker，或只重建 Worker 而未同步 backend 校验副本，可能出现“启动校验通过但执行失败”或“执行目录已更新但 Central 校验仍拒绝”的漂移。
- 后续建议把 workflow 资产收口为共享目录或建立哈希校验门禁；在完成前，workflow 变更应手动对照 `find backend/workflows workers/comfy_agent/workflows -maxdepth 1 -type f` 与关键文件 hash。

## 5. 常见问题与恢复约束
- MinIO 503 / 上传假死
  - 现象：Web 请求超时，甚至非上传接口也被拖慢。
  - 根因：Region 探测阻塞事件循环。
  - 处理：重启 MinIO，并保持 `_region_map` 离线映射策略。
- Nginx 404 / 502
  - `404` 常见于 `proxy_pass` 带错误路径
  - `502` 常见于后端服务或 Tailscale 链路不可达
- CS Bot 改代码不生效
  - 根因通常是只做了 `docker restart`
  - 处理必须是 `docker-compose up -d --build`
- 测试 worker 重建后出现 401 / 读错桶
  - 常见根因：把 `env_file` 当成 compose `${...}` 插值来源，或测试 worker 容器内实际 `AGENT_SECRET_TOKEN`、`MINIO_INPUT_BUCKET`、`MINIO_RESULT_BUCKET` 与 `.env.test` 口径不一致
  - 处理：核对 `workers/docker-compose-test.yml` 默认值是否仍为测试桶，重建后用 `docker exec <worker> env` 验证 `MINIO_INPUT_BUCKET=bot-data-test`、`MINIO_RESULT_BUCKET=comfyui-temp-test`，并确认 token 与测试 Central API 一致

## 6. 文档维护口径
- 部署文档与运维技能必须和 `safe_deploy.sh` 的真实顺序保持一致。
- 若测试栈流程、`.env.test` 口径、`safe_deploy_test.sh` 或“测试优先发布”策略发生变化，必须同步更新运维技能、`AGENTS.md` 与本子模块文档。
- 任何涉及 Alembic 的说明，都应明确“先检查多 head，再在宿主机执行 upgrade head”。
- 任何涉及容器代码更新的说明，都应先核对卷挂载，再决定是 `restart` 还是 `--build`。
- 任何涉及 workflow 资产的说明，都应明确 Central 校验目录与 Worker 执行目录是否一致。
