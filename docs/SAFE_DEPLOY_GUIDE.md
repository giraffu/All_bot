# All_Bot 本地旧部署脚本说明 (`safe_deploy.sh` / `safe_deploy_test.sh`)

本文档只说明根目录旧本地脚本的使用边界。当前正式生产已经切到云控制面，日常生产热修不再使用 `safe_deploy.sh`；当前研发验证首选云测试控制面。

当前主入口：
- 云正式生产：`scripts/safe_deploy_cloud_prod.sh`、`deploy/docker-compose-cloud-prod.yml`、`workers/docker-compose-cloud-prod-worker.yml`
- 云测试环境：`scripts/safe_deploy_cloud_test.sh`、`deploy/docker-compose-cloud-test.yml`、`workers/docker-compose-cloud-worker-test.yml`
- 本地正式灾备：`docs/子模块_本地正式灾备切换_local_prod_fallback.md`

## 1. `safe_deploy.sh` 的当前边界

`safe_deploy.sh` 是旧本地正式整栈脚本，只在以下场景使用：
- 云正式整体故障，需要本地主服务器临时接管正式服务。
- 明确维护本地旧正式栈，且已经确认不会影响当前云正式生产。

它会重建本地 worker、Central API、Bot/Web/Payment、Dashboard，并发布旧边缘静态站。它不是当前云正式生产发布入口，不能用于更新 `cloud-*` 容器。

执行前必须确认：
- 本地 `.env` 是生产口径，未混入测试库、测试 Redis 或测试桶。
- 生产 Telegram Bot token 全网只有一个 polling 实例。
- 需要本地接管时已按本地灾备文档处理 Cloudflare/API/RMB 入口。

## 2. `safe_deploy_test.sh` 的当前边界

`safe_deploy_test.sh` 是旧本地隔离测试栈脚本。当前默认测试环境已经迁到独立 DigitalOcean 测试机 `allbot-do-sgp1-test-control`，因此新研发、联调和配置验证优先走：

```bash
ssh allbot-do-sgp1-test-control
cd /home/deploy/APP/All_bot
./scripts/safe_deploy_cloud_test.sh
```

仅当明确要恢复或维护本地主服务器旧测试栈时，才使用：

```bash
bash safe_deploy_test.sh
```

## 3. 旧脚本共同规则

- 有 Alembic 变更时，先检查 multiple heads，再在宿主机执行 `alembic upgrade head`；不要写“容器启动自动迁移”。
- COPY 型服务改代码后必须 `--build` 重建镜像，不能只 `docker restart`。
- 本地 `docker-compose 1.29.2` 可能遇到 `KeyError: 'ContainerConfig'`；恢复时只清理目标 service 容器，不要批量清理 unrelated 容器。
- 不要在普通功能研发时执行 `safe_deploy.sh`。
- 不要把旧本地测试栈、云测试栈、云正式栈混用同一数据库、Redis DB、Bot token 或对象桶。

## 4. 参考文档

- 云正式长期 SOP：`docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`
- 云测试长期 SOP：`docs/子模块_云测试控制面部署_cloud_test_control_plane.md`
- 本地正式灾备：`docs/子模块_本地正式灾备切换_local_prod_fallback.md`
- 运维总览：`docs/子模块_运维指南与容器管理_ops_deployment.md`
