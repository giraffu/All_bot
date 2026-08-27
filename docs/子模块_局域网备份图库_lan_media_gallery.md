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
.venv/bin/python -m pytest -q lan_media_gallery/tests
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

## 5. iCloud 原片单向 NAS 入口

`ops/icloud_photos_nas/` 使用固定 OCI digest 的 `icloudpd`，把个人 iCloud Photos
单向下载到 NAS `/volume1/ApplePhotos/originals`。它与现有 Windows/聊天媒体备份、
AllBot History 归档、R2 和社区 Gallery 都是独立事实源，不复用账号、目录、数据库或
生命周期。

下载范围包括原照片、原视频、Live Photo 视频部分和 XMP sidecar；文件名加入 iCloud
asset ID 防止跨设备同名覆盖。实现不携带 `delete-after-download`、iCloud recent
保留删除或本地 auto-delete 能力，iCloud 误删不会传播为 NAS 删除。原片是独立 Btrfs
子卷，每日只读快照默认保留 30 份；Apple keyring/session/cookie 与部署运行态位于
`/volume1/ApplePhotosRuntime`，禁止进入原片快照或图库只读挂载。

容器无入站端口，以 NAS `1000:100` 运行并使用只读 rootfs、空 capability 和
`no-new-privileges`。卷使用率达到 80% 后新下载周期 fail closed。首次安装只准备目录、
精确镜像和 snapshot timer，不启动下载；操作者必须在 NAS 私密终端输入 Apple ID、
密码与双重认证码，完成最近 10 项 canary 并回读照片、视频、Live Photo 后才能启动
全量循环。Advanced Data Protection 账号不支持该 Web API 登录路径；账号还必须允许
网页访问 iCloud 数据。

NAS 无法直连镜像 registry 时，从可信主机导出官方 digest 对应镜像，冻结并核对传输
归档 SHA-256；NAS 导入后还必须核对精确 `sha256:<image-id>`。Compose 只接受代码登记
的官方 digest 或离线 image ID，并把实际选择投影到 root-only `.env`；不得改用 tag。

首轮全量验收前，iCloud 原片不接入 PiGallery2。后续浏览接线只能把
`/volume1/ApplePhotos/originals` 作为新的精确只读白名单源；不得把
`/volume1/ApplePhotos`、运行态、快照根或 Apple 凭据目录整体暴露给图库容器。部署、
认证续期、启动、停止、快照恢复和目录接线详见 `ops/icloud_photos_nas/README.md`。
