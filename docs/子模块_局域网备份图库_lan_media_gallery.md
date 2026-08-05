# 局域网备份图库

## 1. 定位

`lan_media_gallery/` 使用独立 PiGallery2 容器浏览已经校验的个人图片和视频。
服务只在 FEVM 局域网地址发布，不进入 Cloudflare、Tailscale 公网入口或 AllBot
业务控制面。AllBot 社区 Gallery 继续管理投稿与 R2 媒体，两者没有数据或身份耦合。

## 2. 数据边界

媒体事实源是 `/home/hfy/Backups/NAS_WD500G_2026-08-04` 下经人工选择的目录。
Compose 逐项挂载个人媒体、Windows Pictures、微信媒体、QQ 图片/收藏与共享表情；
每项都是 `read_only: true`。备份根目录、校验清单、聊天数据库、账号配置和
`AppWebCache` 不对容器可见。

容器以 `1000:1000` 运行。可写数据只位于
`/home/hfy/.local/share/allbot/lan-media-gallery/`：

- `config/`：PiGallery2 配置；
- `db/`：账户和 SQLite 索引；
- `tmp/`：图片缩略图、视频缩略图与必要的 MP4 转码副本。

3GP 等浏览器不能原生播放的输入由 PiGallery2 在 `tmp/` 生成派生 MP4；原文件
保持只读。删除或重建缩略图不会改变源备份，删除 `db/` 则会丢失账户与索引，必须
单独确认。

## 3. 容器与访问

镜像在 `compose.yml` 中固定为精确 OCI digest。Web 声明绑定
`192.168.1.115:8099`，上传通过启动参数关闭，认证保持开启。容器还使用只读
rootfs、`cap_drop: ALL` 和 `no-new-privileges`。

首次启动先在私有运行态生成管理员密码，再用只绑定回环地址的初始化阶段修改上游
默认账户；确认旧默认密码失效后才允许发布到 LAN。密码文件权限必须为 `0600`，
不得进入 Git、日志或 Compose。

## 4. 验证与运维

静态验证：

```bash
python -m pytest -q lan_media_gallery/tests
docker compose -f lan_media_gallery/compose.yml config
```

运行时验证：

```bash
docker compose -f lan_media_gallery/compose.yml ps
curl -I http://192.168.1.115:8099/
docker inspect allbot-lan-media-gallery \
  --format '{{range .Mounts}}{{println .Source .Destination .RW}}{{end}}'
```

验收要求：容器健康、HTTP 200、未登录 Gallery API 被拒绝、管理员可登录、配置读取
到 `Upload.enabled=false`，所有备份源挂载的 `RW` 均为 `false`。普通更新只重建
目标服务并保留 XDG 运行态目录；失败时停止新容器并用上一精确 digest 恢复，不删除
索引或缩略图。
