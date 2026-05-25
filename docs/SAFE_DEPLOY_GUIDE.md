# All_Bot 安全更新与部署脚本 (`safe_deploy.sh` / `safe_deploy_test.sh`) 使用说明

`safe_deploy.sh` 与 `safe_deploy_test.sh` 是一键式自动化部署脚本，分别用于正式环境与隔离测试环境。它们的目标是：在发布期间尽量避免打断正在收口的任务，并通过现行 runtime/registry/queue 视图判断是否可以安全重建服务。

---

## 1. 执行前置条件
1. 代码已同步到目标版本。
2. 正式环境 `.env` 与测试环境 `.env.test` 已正确配置。
3. 功能研发、联调、修复与配置验证默认只允许发布到测试环境；只有在明确确认后才允许执行正式发布。

---

## 2. 如何执行脚本
在项目根目录执行：

```bash
# 测试环境（默认研发路径）
bash safe_deploy_test.sh

# 正式环境（仅在明确要求上线时执行）
bash safe_deploy.sh
```

---

## 3. 默认发布策略
- 研发、联调、缺陷修复、配置调整：默认执行 `safe_deploy_test.sh`
- 用户验收通过、明确要求上线：才执行 `safe_deploy.sh`
- 未经明确确认，不得把研发改动直接部署到正式环境

## 4. 当前部署主口径
### 4.1 维护模式
- 脚本会先阻止新任务继续进入主链，避免发布过程中持续增加增量任务。

### 4.2 等待运行态收口
- 当前推荐口径是不再把“Redis `active_tasks` 哈希长度”当成唯一依据。
- 发布前应依据现行 runtime/registry/queue 视图判断是否仍有未收口任务。
- 若存在长任务，优先等待其正常完成；若明确已卡死，再走统一的 runtime cleanup / force terminate 路径。

### 4.3 异常任务处理
- 不再把 `zombie_cleaner_service.py` 视为部署脚本标准前置步骤。
- 当前异常任务清理应优先通过：
  - Dashboard 管理动作
  - core 暴露的 force terminate / runtime cleanup
  - 必要时结合 queue / worker 视图判断 backend 是否仍活跃

### 4.4 数据库迁移
- 数据库结构变更必须通过 Alembic。
- 当前标准流程是脚本在宿主机主动执行 Alembic，不再依赖“部署完成后手动进容器跑 upgrade head”。

### 4.5 服务重建
- workers、central API、主服务群与 Dashboard 按脚本编排顺序重建。
- 测试脚本只作用于测试栈；生产脚本只作用于生产栈。

---

## 5. 测试环境脚本说明
`safe_deploy_test.sh` 用于隔离测试栈，主要处理：
- 测试入口服务维护模式与运行态收口检查
- 测试数据库迁移
- 测试 workers / central API / 入口服务重建

它不会重建正式环境服务；`safe_deploy.sh` 也不会顺带更新测试环境。

---

## 6. 常见问题与排障
### Q1: 脚本卡在“等待运行态收口”怎么办？
- 可能存在一个超长视频任务仍在执行。
- 也可能某个 backend/worker 已异常，任务无法自然终态。
- 处理顺序建议：
  1. 查看 worker / central API 日志确认任务是否仍在推进。
  2. 通过 Dashboard 查看系统任务与 worker 视图。
  3. 若确认任务已卡死，优先走 Dashboard 管理动作或 core 统一终止入口。
  4. Redis 手工删键只作为极端故障兜底，不作为常规操作。

### Q2: 执行时提示 `docker-compose: command not found`？
- 可能系统使用的是新版 Docker 插件 `docker compose`。
- 需要按运行环境实际命令口径调整脚本。

### Q3: 为什么某些独立侧车服务没有被更新？
- 某些服务边界相对独立，默认不会被所有部署脚本全量重建。
- 若本次改动涉及这些侧车服务，应按其独立 compose 或部署入口补充更新。

---

## 7. 维护原则
- 部署文档不再把旧的 `active_tasks` 哈希、`DB1/DB2`、`zombie_cleaner_service` 写成主知识口径。
- 当前标准认知应是：依据 runtime/registry/queue 视图判断运行态，异常任务通过 core/runtime 统一收口。
