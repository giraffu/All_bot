---
name: "allbot-avatar-miniapp"
description: "开发和维护独立 3D 角色 Mini App、局域网容器、fixture 建模、Three.js/VRM 预览、Blender CPU 渲染与未来 GPU provider seam。"
---

# AllBot 3D 角色 Mini App

## 按需阅读

- 架构、API、表、状态和 LAN SOP：
  `docs/子模块_3D角色MiniApp_avatar_miniapp.md`
- 2D 人物参考图语义：
  `docs/子模块_LTX文生视频与人物一致性_ltx_t2v_characters.md`
- 正式 GPU/workflow 接入：`allbot-comfy-models`
- JWT、密码与权限：`allbot-billing-auth`
- Vue UI：`vue-best-practices`；视觉验收再加 `frontend-browser-preview`

## 稳定边界

- `src.avatar_miniapp.api:app` 只挂载 Mini App 所需登录、用户、上传、人物草稿
  和 3D 接口，不挂 Telegram、支付或通用任务入口。
- `ModelBuildProvider` 是建模 adapter seam；`local_fixture` 只用于明确开启的
  LAN 开发模式，不计费、不进 History、不声称根据照片重建真人。
- `character_model_input_views` 的四张标准建模视图与现有六种
  `CharacterReferenceView` 分表，禁止混淆人脸近景和几何重建输入。
- Worker 只使用服务端固定 Blender/FFmpeg 脚本和 catalog recipe；不得接受任意
  路径、URL、shell 参数或 Python。
- 所有模型、视图和渲染均使用 `internal_user_id` 校验 owner，并通过签名 URL
  交付。
- 主服务是迁移唯一所有者。Mini App 容器不得在启动时运行 Alembic。

## 开发与验证

- 后端行为先跑 `pytest -q tests/avatar_miniapp`。
- 前端使用 Vue 3 Composition API、`<script setup lang="ts">`、Pinia 和
  vue-i18n；后端只返回枚举/原始值，不拼 UI 文案。
- 响应式验收跑 Mini App 自身 Playwright desktop/mobile 项目并查看截图。
- Compose 先用 `.env.lan.example` 执行 `docker compose ... config`；真实
  `.env.lan`、CA 和输出资产不入 Git。
- 只有 Worker 镜像内实际生成 GLB、四视图和 MP4 后，才能声明 Blender 闭环
  通过；静态测试不能替代运行时证据。

## 高压红线

- 不因本地 fixture 接入 task registry、扣费或生产开关。
- 不提交第三方人物二进制、模型权重、真实照片、密钥或 LAN IP。
- 不自动部署、不修改 Cloudflare/Bot/RunPod/LAN GPU，不把 Compose 测试写成
  已上线。
- 正式多视角建模必须重新进入 task core、billing、GPU artifact、license 和
  canary 评审，不能复用 fixture endpoint 直接升级。
