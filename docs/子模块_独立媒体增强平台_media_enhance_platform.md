# 真境智影（Clarity AI）独立媒体增强平台

## 1. 定位与边界

`media_enhance_platform/` 是 AllBot 仓库内独立演进的“真境智影
（Clarity AI）”媒体增强产品。前端首次访问默认使用中文，并保留
用户手动切换后的语言偏好。V1
提供图片高清、视频高清与视频插帧，拥有独立前端、FastAPI API、
PostgreSQL 数据、MinIO 对象存储和 Worker HTTP 契约。它不复用 AllBot
主用户、灵石、任务队列、Telegram 对象或数据库表。

本地唯一局域网入口是 `http://<LAN-IP>:8095`。Nginx 代理 `/api`，
PostgreSQL、MinIO 和后端不发布 LAN 端口。V1 不部署云测试、云正式、
Cloudflare、RunPod 或 LAN GPU，也不修改现有 Worker 支持列表。

## 2. 目录与服务

- `frontend/`：Vue 3、TypeScript、Pinia、Router、vue-i18n 的响应式 SPA。
- `backend/`：认证、RBAC、报价、账本、任务、媒体、工单、投诉与管理 API。
- `worker_contract/`：Worker 租约协议及 workflow 构建/校验代码。
- `workflows/`：三类自有 API workflow 与 catalog，不依赖运行机模板包。
- `docker-compose.yml`：PostgreSQL、MinIO、API、Nginx/SPA 的本地持久化栈。

未来可把四层分别迁移服务器；GPU Worker 仅持 agent token，通过
`heartbeat → claim → progress → complete/fail` 工作，不接触用户数据库。

## 3. 身份、计费与媒体

认证采用 Argon2 密码哈希、短期 JWT access token 和 HttpOnly refresh
cookie；管理员通过本地环境变量首次初始化，密码不得进入 Git。V1
不发送验证或找回邮件。

注册赠送 100 个测试点。提交时创建 `reserve` 流水，成功时 `capture`，
失败或取消时 `release`。后台退款不能超过已扣点数，并以幂等键拒绝
重复执行。业务任务和执行尝试分离：失败重试只新增 attempt，不重复扣点。

上传只信任服务端媒体探测结果，不信任扩展名。默认支持
JPG/PNG/WebP 与 MP4/MOV/WebM；图片上限 100 MB，视频上限 2 GB/30 分钟。
源文件和结果不自动过期；运行中不可删除，排队任务须先取消，删除后仅留
不含媒体内容的审计记录。

## 4. 任务与 Worker 契约

任务状态固定为 `queued / claimed / preprocessing / running / uploading /
succeeded / failed / canceled`。无健康 Worker 时，业务任务保持 `queued`
并呈现 `no_worker_online`，预占点数不会被扣除。

claim 创建带 `attempt_id` 和到期时间的租约。进度、完成和失败必须同时
匹配任务、attempt 与租约所有者；租约过期后任务可安全回队。失败分为可重试
和不可重试，只有 failed 业务任务可由后台创建新 attempt。

三个 workflow：

- `image_upscale`：SeedVR2 图片增强，2×/4×。
- `video_upscale`：SeedVR2 视频增强，2×，输出映射保留音频。
- `frame_interpolation`：已验证的 `FL_RIFE`/RIFE 模式，2×/4×，保留音频。

V1 只校验 JSON、关键节点和参数注入，不宣称真实 GPU 画质验收。

## 5. 页面与法律状态

前台包含首页、注册/登录、上传三步工作台、任务进度/下载、定价、账户客服、
用户协议、隐私政策和版权投诉。后台包含任务时间线、失败重试、文件删除、
点数调整/退款、客服与投诉处理。中英文共用同一信息架构。

定价由后端 catalog 下发；套餐购买在 V1 标记“暂未开放”，按钮转客服工单。
站点页脚展示已核准的 `鄂ICP备2026044153号-1`，并链接工信部备案系统。
协议与隐私页只是上线前结构草案，不是正式法律意见；公网发布前必须补齐
运营主体、地址、客服/版权邮箱和审阅后的条款。

## 6. 本地启动与验证

按 `media_enhance_platform/README.md` 准备忽略提交的 `.env`，执行
`docker compose up --build -d`。健康检查：

```bash
curl -fsS http://127.0.0.1:8095/health
curl -fsS http://127.0.0.1:8095/api/health
```

后端测试覆盖认证/RBAC、报价、媒体所有权与校验、账本、退款、Worker
租约、重试、删除审计及无 Worker 行为。前端需通过 Vitest、类型检查、
生产构建，并在 1440×900 与 390×844 视口做 Playwright 验收。
