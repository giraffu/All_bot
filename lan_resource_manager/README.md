# AllBot 本地资源管理平台

仅供本地主服务器局域网使用的 FastAPI + Vue 3 控制面，包含：

- `LAN AIO 资源管理`：继续通过固定单槽 operator 管理本地 GPU。
- `模块构建部署`：扫描 A–H、选择 pending handoff 合入 main、选择安全槽位
  对齐，以及选择独立模块构建并部署到 test/prod。

平台不实现第二套协调器或发布器。隔离 runner 只调用：

```text
manage_ai_workspaces.py status / align-merged --slot ...
auto_integrate_handoffs.py integrate-all --head ... --execute
release.py build / deploy / status
```

旧 PR/CI/bundle、plan-token、全量 test、GPU manifest preparation、配置同步、
回滚材料修复和 maintenance UI 已删除。

## 操作规则

- 槽位合入只接受所选槽位当前的 `pending` handoff；冲突进入
  `needs-rebase`，不影响其它所选任务。
- 对齐只触及所选槽位；dirty、未合入或未初始化槽位由 workspace manager 拒绝，
  不覆盖本地内容。
- test 每次只能部署 1–2 个模块；prod 可多选，runner 仍逐模块调用发布器并记录
  每个结果。
- 构建只接受当前远端 main 的完整 SHA；模块产物必须是精确
  `repository@sha256:digest`。
- prod 由后台显式选择且确认；runner 自动向 `release.py deploy` 附加
  `--confirm-prod`。
- GPU 模块必须单独选择，并提供 `runpod|lan + exact slot`。
- Web 容器不读取 Git、Docker、GHCR、Cloudflare 或云 SSH 凭据。runner 不挂
  Docker Socket；本机构建通过配置的 SSH Docker endpoint 执行。

## 启动

```bash
cd lan_resource_manager
cp .env.example .env
docker compose --env-file .env -f compose.yml config
docker compose --env-file .env -f compose.yml up -d --build
```

浏览器访问 `http://192.168.1.115:8096`。启用构建前需要配置专用本机 SSH key、
GHCR push 配置；启用云部署前配置固定云 SSH key，Pages 另配专用 token。保持
`/dev/null` 会让相应动作安全失败。

## 验证

```bash
python -m pytest -q lan_resource_manager/tests
python -m pytest -q tests/ops/test_manage_ai_workspaces.py \
  tests/ops/test_auto_integrate_handoffs.py tests/ops/test_release_cli.py
cd lan_resource_manager/frontend
npm ci
npm test
npm run build
cd ..
docker compose --env-file .env.example -f compose.yml config
```
