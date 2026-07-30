# 子模块：3D 角色 Mini App

## 1. 定位与边界

`avatar_miniapp/` 是独立的局域网 3D 角色验证应用。它复用 AllBot 测试环境的
账号、PostgreSQL、Redis、MinIO 和 `CharacterReference`，但不绑定 Telegram
Bot、公网域名、GPU、ComfyUI 或生产发布。

容器沿用共享运行环境身份：测试环境使用 `ALLBOT_ENV=test` 与
`BOT_TYPE=TEST`。Mini App 只挂密码登录，因此允许 `BOT_TOKEN` 为空；空值只
禁用 Telegram 登录安全通知，不放宽 JWT、密码、限流或资源归属校验。

本地 `local_fixture` 是不计费的开发 provider：它生成项目自有的写实比例、
非真人肖像成年女性 mannequin，用于验证 3D 预览、骨骼动作和 CPU 视频导出。
它不会根据用户上传图片重建真人，也不写入正式任务 History。正式多视角建模
必须另接 task core、扣费补偿和 GPU Worker，不能扩大 fixture 接口权限。

稳定入口：

- API：`src.avatar_miniapp.api:app`
- 领域行为：`src/avatar_miniapp/service.py`
- Provider seam：`ModelBuildProvider`
- Worker：`python -m src.avatar_miniapp.worker`
- Vue：`avatar_miniapp/frontend/`
- LAN Compose：`avatar_miniapp/docker-compose.lan.yml`

独立 API lifespan 负责调用
`ensure_billing_core_providers_registered()`，使密码登录和动态权限检查复用
主 Web 的 provider seam；不得在 Mini App 路由中绕过或私自实现权限判断。

## 2. 数据与状态

主服务 Alembic 管理三张表：

- `character_model_assets`：角色模型版本、provider、GLB/Blend/缩略图 key、
  rig、动作和 Worker 租约；
- `character_model_input_views`：独立保存
  `model_front/model_back/model_left/model_right`，不改变现有六种 2D 人物参考图；
- `character_render_jobs`：受控 scene recipe、CPU 渲染状态、输出 key 和租约。

建模状态：
`queued → preparing_views → reconstructing → rigging → ready|failed`。
渲染状态：`queued → rendering → ready|failed|cancelled`。

每个角色只能有一个非终态建模版本。Worker 通过 PostgreSQL
`FOR UPDATE SKIP LOCKED` 和 30 分钟租约串行领取任务；过期租约可由重启后的
Worker 回收。对象使用 owner-scoped 前缀：

```text
character_models/{internal_user_id}/{character_id}/{asset_id}/...
character_renders/{internal_user_id}/{render_id}/...
```

API 只返回短时签名 URL。查询、构建、取消和下载前均校验
`internal_user_id`，客户端不能提交对象 key、本地路径、外部 URL、Blender
脚本或 FFmpeg 参数。

## 3. API 与前端

独立 API 只暴露密码登录、本人资料、预签名上传、角色列表/草稿和 Mini App
接口：

```text
POST /api/auth/login
GET  /api/users/me
GET  /api/storage/presigned-url
GET  /api/characters
POST /api/characters/drafts
GET  /api/miniapp/characters
POST /api/miniapp/characters/{character_id}/fixture-build
GET  /api/miniapp/model-assets/{asset_id}
POST /api/miniapp/renders
GET  /api/miniapp/renders/{render_id}
POST /api/miniapp/renders/{render_id}/cancel
```

`fixture-build` 在 `MINIAPP_FIXTURE_MODE` 关闭时返回 404。视频仅接受 catalog
动作、镜头、背景，`720x1280|1280x720|1024x1024`，24/30 FPS 和 3–10 秒。

Vue 使用 Composition API、TypeScript、Pinia、Vue Router、vue-i18n 与
Three.js。GLTF loader 注册 VRM plugin；当前 GLB 动作由 `AnimationMixer`
播放。桌面为角色/画布/控制三栏，手机为全屏画布、顶部角色条和底部设置抽屉。
`shared/web/theme-tokens.css` 是主 Web 与 Mini App 的公共主题 token seam；
Mini App 文案位于自身 `miniapp.*` namespace，并合并共享中英文 locale。

## 4. LAN 启动

从当前测试环境复制真实连接值，不把 `.env.lan` 提交 Git：

```bash
cp avatar_miniapp/.env.lan.example avatar_miniapp/.env.lan
```

`MINIO_ENDPOINT` 必须是容器可访问地址；`MINIO_PUBLIC_URL` 必须是手机和电脑可
访问的局域网地址，否则浏览器无法使用预签名上传/下载 URL。

主服务操作者先对测试数据库执行迁移：

```bash
alembic upgrade head
```

再启动三个容器：

```bash
docker compose \
  --env-file avatar_miniapp/.env.lan \
  -f avatar_miniapp/docker-compose.lan.yml \
  up --build -d
```

访问 `https://<MINIAPP_LAN_HOST>:8443`。Caddy 使用内部 CA；从容器复制根证书
并仅在测试设备上信任：

```bash
docker compose \
  --env-file avatar_miniapp/.env.lan \
  -f avatar_miniapp/docker-compose.lan.yml \
  cp avatar-miniapp-web:/data/caddy/pki/authorities/local/root.crt \
  /tmp/avatar-miniapp-root.crt
```

结束测试：

```bash
docker compose \
  --env-file avatar_miniapp/.env.lan \
  -f avatar_miniapp/docker-compose.lan.yml \
  down
```

不要追加 `-v`，除非明确希望删除本地 Caddy CA。Compose 不执行数据库迁移，
也不修改 Bot、Cloudflare、RunPod、LAN GPU 或生产环境。

## 5. 验证与未来 Provider

最小验证：

```bash
pytest -q tests/avatar_miniapp
cd avatar_miniapp/frontend
npm test
npm run build
npm run test:e2e
cd ../..
docker compose --env-file avatar_miniapp/.env.lan.example \
  -f avatar_miniapp/docker-compose.lan.yml config
python scripts/doc_quality_checker.py
```

真实 Blender 验收还需在 Worker 镜像内完成一次 fixture build，并确认 GLB、
四张 PNG、四个 action、3 秒 H.264 MP4 和 MinIO 回写。未执行真实共享服务与
Worker 流程时，只能声明代码、容器和静态测试就绪。

后续 GPU adapter 应消费一致尺度、A-Pose、同背景的四张 model input views，
输出 GLB/VRM 和 rig metadata。Hunyuan3D 等外部模型的权重、许可、workflow、
artifact 与 canary 继续遵守 `allbot-comfy-models` 和任务/计费边界。
