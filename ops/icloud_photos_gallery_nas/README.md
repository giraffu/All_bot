# iCloud Photos NAS 预览图库

该目录在 NAS 上运行独立 PiGallery2，把 `/volume1/ApplePhotos/originals` 作为唯一
`read_only` 媒体源。上传与分享关闭；配置、账户、索引、缩略图和视频转码只写入
`/volume1/ApplePhotosGalleryRuntime`，不会改名、移动或删除 iCloud 原片。

用户明确要求在 iCloud 首轮全量仍下载时提前查看，因此本服务属于预览。页面会随
下载进度增加内容，下载中的内容并不代表完整备份；首轮完成仍需单独核对 iCloud 项目
数、NAS 文件数、总字节以及图片、视频和 Live Photo 的随机回读。

## 部署

默认 dry-run：

```bash
./bootstrap.sh
```

NAS 无法访问 Docker Hub 时，先把固定 digest 镜像从可信主机用 `docker save` 和
`gzip -n` 生成冻结归档，再核验归档 SHA-256 与精确 image ID：

```bash
sudo ./load-offline-image.sh \
  --archive /受限路径/pigallery2-image.tar.gz \
  --archive-sha256 <64位归档摘要> \
  --execute --confirm LOAD_PIGALLERY_OFFLINE_IMAGE

sudo env \
  PIGALLERY_IMAGE=sha256:074da989a73e4e26d666c89989272b3b76c1d63a92a4e99e82fd98e8f7d36189 \
  ./bootstrap.sh --execute --confirm CREATE_ICLOUD_PHOTOS_PREVIEW_GALLERY
```

bootstrap 先只绑定 `127.0.0.1:8099`，生成随机管理员并删除上游默认账户；只有初始化
成功才重建到 `192.168.1.150:8099`。管理员用户名和密码分别保存在 root-only
`/volume1/ApplePhotosGalleryRuntime/secrets/admin-username` 与
`/volume1/ApplePhotosGalleryRuntime/secrets/admin-password`；首次初始化时用户名默认为
`nas-gallery`，之后重部署会保留运行时账号信息。

## 运维

```bash
sudo /volume1/ApplePhotosGalleryRuntime/deploy/operator.sh status
sudo /volume1/ApplePhotosGalleryRuntime/deploy/operator.sh logs
sudo /volume1/ApplePhotosGalleryRuntime/deploy/operator.sh stop
sudo /volume1/ApplePhotosGalleryRuntime/deploy/operator.sh start
```

浏览器访问 `http://192.168.1.150:8099`。日期目录按 `年/月/日` 展示；图片使用缩略图，
浏览器不能直接播放的 MOV 等视频在独立 `tmp/` 中生成派生 MP4。原始图片、视频、XMP
和 iCloud 下载状态都不会被图库修改。
