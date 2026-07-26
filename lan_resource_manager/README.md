# LAN AIO 资源管理平台

仅供本地主服务器局域网使用的 LAN AIO 映射与单卡切换界面。页面把 Git
catalog、XDG ledger 和 live status 合并为物理 GPU 卡片；真正的切换仍只通过
`scripts/lan_aio_fleet_prod_ops.py` 完成。

## 安全边界

- Compose 只发布到 `192.168.1.115:8096`，应用层同时限制
  `192.168.1.0/24`、Host、Origin、JSON 和 CSRF。
- 平台没有登录，因此同一局域网中能打开页面的人都能在二次输入确认后请求切换。
- 只允许 `catalog_ready + enabled + retargetable` 候选。
- 切换前重新巡检目标卡；drift、未完成 operation、陈旧 current 或未收口空卡都会
  fail closed。
- 不挂 Docker Socket，不提供 reconcile、candidate-plan、镜像发布或自由命令接口。
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

停止平台不会停止任何 GPU runtime：

```bash
docker compose --env-file .env -f compose.yml down
```

## 开发验证

```bash
python -m pytest -q lan_resource_manager/tests
cd lan_resource_manager/frontend
npm ci
npm test
npm run build
cd ..
docker compose --env-file .env.example -f compose.yml config
```

后端通过 `OperatorPort` 注入 fake，测试不会执行真实 LAN mutation。前端采用
Vue 3 Composition API、`<script setup lang="ts">` 和 TypeScript。
