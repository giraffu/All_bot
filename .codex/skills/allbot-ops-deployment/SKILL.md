---
name: "allbot-ops-deployment"
description: "处理 Docker Compose 编排、safe_deploy/safe_deploy_test、Alembic 迁移和故障恢复。研发默认先发测试环境，正式发布需用户明确确认。"
---

# AllBot 运维指南与容器管理 (Ops & Deployment)

本技能用于规范 AllBot 的部署、迁移与系统级排障，必须以当前 `safe_deploy.sh` 与 `safe_deploy_test.sh` 的真实流程为准。

## 1. 模块功能描述
- **测试优先部署**：功能研发、联调、修复与配置调整默认先更新隔离测试栈，优先使用根目录 `safe_deploy_test.sh`；只有在用户明确要求正式发布或交付验收通过后，才允许使用 `safe_deploy.sh` 更新生产环境。
- **标准部署入口**：测试环境优先使用 `safe_deploy_test.sh`，生产环境使用 `safe_deploy.sh`，避免手工拼接多个目录的容器命令。
- **迁移保护**：部署前检查 Alembic multiple heads；发现多 head 立即中止。
- **宿主机迁移执行**：通过后直接在宿主机执行 `alembic upgrade head`，不依赖容器启动时自动迁移。
- **分阶段重建**：按 workers -> central api -> 主服务群 -> dashboard -> 测试环境的顺序重建。
- **故障恢复**：处理 MinIO 503、Nginx 404/502、容器代码未更新、环境变量未生效等典型问题。
- **测试 worker 变量陷阱**：`workers/docker-compose-test.yml` 内的 `${...}` 插值不会读取 `env_file: ../.env.test`，重建测试 worker 时需要从宿主 shell 显式传入关键变量，避免 401 或读写错误桶。

## 2. 操作规范
- 修改数据库结构时：
  - 先更新模型
  - 生成 migration
  - 确保只有一个 Alembic head
  - 测试研发阶段先通过 `safe_deploy_test.sh` 或测试库宿主机 Alembic 验证升级
  - 只有在用户明确要求正式发布时，才通过 `safe_deploy.sh` 或生产库宿主机 Alembic 执行升级
- 修改未挂载源码卷的服务代码时：必须 `--build` 重建镜像，不能只 `restart`。
- 功能研发默认目标环境是隔离测试栈：`.env.test`、`backend/docker-compose-test.yml`、`workers/docker-compose-test.yml`、`deploy/docker-compose-test.yml`。
- 测试完成前，不得默认重建生产 Bot、生产 Web API、生产 Payment API、生产 Central API 或正式 Dashboard。
- 交付前必须把“测试环境已验证通过、准备正式发布”作为显式阶段切换条件，不得自行跳过用户验收。
- 若重建测试 worker，必须额外核对宿主 shell 是否已显式导出 `AGENT_SECRET_TOKEN`、`MINIO_BUCKET`、`MINIO_RESULT_BUCKET`；不要误以为 compose 插值会自动读取 `.env.test` 的 `env_file` 值。

## 3. 核心红线
- 不要在普通功能研发过程中默认执行 `safe_deploy.sh`、生产 compose 或任何正式环境重建动作。
- 不要把“帮我改功能/修 Bug/做联调”自动理解为“允许正式部署”；除非用户明确提出上线、交付、发布、同步生产。
- 不要再写“容器下次启动会自动应用 Alembic 变更”，这不是当前标准流程。
- 不要在存在 multiple heads 的情况下继续部署。
- 不要忽略卷挂载差异直接判断“代码已生效”。
- 不要把 `docker restart` 当作代码发布手段，特别是 `web-api`、Dashboard、CS Bot 等 COPY 型服务。
- 不要把 `env_file` 与 compose `${...}` 插值混为一谈；测试 worker 的变量未显式导出时，默认值可能悄悄生效。

## 4. 测试与验证
- 测试研发阶段先验证隔离测试栈健康检查、关键 API 可达、测试库/测试 Redis/测试中控链路正确。
- 只有在测试环境完成功能验证并得到用户确认后，才进入正式环境部署验证。
- 验证 migration 在空库可顺利 `upgrade head`。
- 验证重建后容器确实运行的是新镜像，而不是旧容器旧代码。
- 若测试 worker 涉及认证或对象存储，额外验证实际生效的 `AGENT_SECRET_TOKEN`、输入桶和结果桶与 `.env.test` 期望一致。
