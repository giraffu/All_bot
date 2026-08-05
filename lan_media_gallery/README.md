# AllBot 局域网备份图库

该目录以独立 PiGallery2 容器只读浏览已校验备份中的个人图片和视频。它不属于
AllBot Gallery，不读取业务数据库，也不修改备份目录。

## 安全边界

- Web 只发布到 `192.168.1.115:8099`。
- 镜像固定为精确 OCI digest，不跟随 mutable tag。
- 只挂载 `compose.yml` 中列出的媒体目录，所有备份 bind mount 都是只读。
- 容器以宿主 `hfy` 的 `1000:1000` 身份运行，不依赖 root 越权读取。
- 配置、索引和缩略图写入 `~/.local/share/allbot/lan-media-gallery/`，不写回备份。
- 上传功能关闭；首次启动后必须立即修改默认管理员密码。
- QQ `AppWebCache`、账号数据库、微信数据库和 `SHA256SUMS` 不在容器可读范围内。

## 操作

```bash
cd lan_media_gallery
mkdir -p /home/hfy/.local/share/allbot/lan-media-gallery/{config,db,tmp}
docker compose config
docker compose up -d
docker compose ps
```

浏览器访问 `http://192.168.1.115:8099`。首次登录使用上游初始化账户，然后立即在
设置中修改密码。运行后用以下命令复核只读范围：

```bash
docker inspect allbot-lan-media-gallery \
  --format '{{range .Mounts}}{{println .Source .Destination .RW}}{{end}}'
```

备份目录对应行的 `RW` 必须全部为 `false`。停止服务不会删除索引或配置：

```bash
docker compose down
```

只有明确需要清空图库账户、索引和缩略图时，才可另行确认后清理
`~/.local/share/allbot/lan-media-gallery/`；普通停止或升级不得删除该目录。
