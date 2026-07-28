# AllBot 本地资源管理平台

> 模块发布 UI 的旧 build/plan/deploy 路径已退役；当前只读展示 main 与独立模块
> 目录，实际操作使用 `scripts/release.py build/deploy/rollback/status`。

仅供本地主服务器局域网使用的资源控制面。`LAN AIO 资源管理` Tab 合并 Git
catalog、XDG ledger 和 live status；`模块构建部署` Tab 管理 A–H handoff
集成/安全对齐、可信 main bundle 与模块化测试部署，通过隔离 runner 调用既有
协调器和不可变发布器。

## 安全边界

- Compose 只发布到 `192.168.1.115:8096`，应用层同时限制
  `192.168.1.0/24`、Host、Origin、JSON 和 CSRF。
- 平台没有登录，因此同一局域网中能打开页面的人都能在二次输入确认后请求切换。
- 只允许 `catalog_ready + enabled + retargetable` 候选。
- 切换前重新巡检目标卡；drift、未完成 operation、陈旧 current 或未收口空卡都会
  fail closed。
- 不挂 Docker Socket，不提供 reconcile、candidate-plan、镜像发布或自由命令接口。
- Web 容器不挂云 SSH、GitHub/GHCR 或 Pages 凭据；这些只进入无对外端口的 Unix
  socket runner，且 runner 只接受固定动作和参数。
- 构建仅允许当前远端 main；缺可信 CI 时触发完整上游链，已有成功 CI 时仅以固定
  `main/full` 参数补齐 modular bundle，不生成 build-only 包。轻量 main 会明确跳过
  bundle，并沿 main 历史使用最近的不可变部署候选。
- 每次只部署 `release-policy.yml` 的一个完整模块组，先生成短效计划，再输入
  `TEST|PROD <module> <40位SHA>`；构建成功不会自动部署。
- 全部集成固定使用测试专用 coordinator；全部对齐只刷新 clean 且已被 main 包含的
  槽；测试全模块部署把 policy 中 test 模块精确全集组成一次原子
  `plan -> deploy`。三者均无正式批量发布能力。
- 失败批次必须按界面给出的 `RETRY <batch>` 精确确认后原批重试；runner 的临时
  worktree 与短效 plan 使用持久 release cache volume，并配置固定审计提交身份，避免受容器小容量
  `/tmp` 或宿主 Git 全局配置限制。
- `GPU BUILD <main-sha>` 可恢复因 GPU attestation 缺失而失败的 bundle：只构建缺失
  的 8 个实际镜像，形成 9-profile 完整 manifest 并重放 bundle；不会创建 Pod、
  部署正式环境或进入维护。
- `TEST CONFIG <main-sha>` 固定以当前 main 执行 test `config-plan -> config-apply`，
  原子收敛阻断部署的配置投影漂移；没有 prod 参数，也不调用手动维护入口。
- 手动维护只阻止新生成请求，未知 owner、活动事务或 recovery 状态只能由宿主 CLI
  收口。
- 启动和刷新只读，不会自动切换、recover 或 reconcile。
- 运行镜像从 AllBot 已发布的 Dashboard Backend 精确 digest 继承 Python/OpenSSH
  闭包；平台不导入或启动 Dashboard 服务。
- `.env.lan-aio-prod` 是宿主 CLI 的可选 overlay，平台默认使用 `/dev/null`，避免
  Docker 为缺失的可选 bind source 创建目录；正式 cloud/model env 仍只读挂载。

## 启动

从已经包含本项目的 AllBot 主目录执行：

```bash
cd lan_resource_manager
cp .env.example .env
docker compose --env-file .env -f compose.yml config
docker compose --env-file .env -f compose.yml up -d --build
```

浏览器打开 `http://192.168.1.115:8096`。第一次进入先点击“刷新实时状态”；全量
巡检通常需要约 30–60 秒。若显示只读保护，使用宿主 operator CLI 检查 drift，
不要修改平台代码或账本绕过。

页面右上角问号打开 `/help.html`，给出从 handoff、全部集成、槽位对齐、测试
全模块部署到不可变正式候选就绪的操作顺序和 blocker 处理方式。

若要启用构建/部署与集成功能，另外配置 `.env` 中 runner 专用的 test/prod env、
云 SSH key、GitHub Actions token、Git push SSH key、GHCR read config 与 Pages
token 路径。runner 只对 Git common dir、A–H 与 XDG queue 使用精确写挂载；Web
容器仍不接触这些凭据和写挂载。保持默认 `/dev/null` 时对应能力 fail closed。
runner 的 `WORKSPACE_REPO_ROOT` 固定指向已显式写挂载的主仓库；`/workspace`
继续只读，用于加载当前可信脚本和策略。

停止平台不会停止任何 GPU runtime：

```bash
docker compose --env-file .env -f compose.yml down
```

## 开发验证

```bash
python -m pytest -q lan_resource_manager/tests
python -m pytest -q tests/scripts/test_release_maintenance.py
cd lan_resource_manager/frontend
npm ci
npm test
npm run build
cd ..
docker compose --env-file .env.example -f compose.yml config
```

后端通过 `OperatorPort` 注入 fake，测试不会执行真实 LAN mutation。前端采用
Vue 3 Composition API、`<script setup lang="ts">` 和 TypeScript。
