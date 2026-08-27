# iCloud Photos → NAS 原片备份

本目录把 Apple iCloud Photos 单向下载到 NAS。下载器不上传文件，也不启用任何
iCloud 删除或本地镜像删除参数。NAS 原片位于独立 Btrfs 子卷，运行凭据位于另一
私有目录；每日只读快照只覆盖原片，不覆盖 Apple 账号状态。

这不是 Apple Photos 图库数据库的替代品。它保存原照片、原视频、Live Photo 的视频
部分和 XMP sidecar，但不承诺完整还原 Apple Photos 的人物识别、编辑历史、回忆和
相册数据库。iCloud 继续作为日常同步主库，NAS 是防误删的独立本地副本。

## 固定安全边界

- 镜像固定为 `icloudpd` 1.32.3 的精确多架构 OCI digest；NAS 无法访问 registry
  时，只接受从可信机离线导入后核验一致的精确 `sha256:<image-id>`。
- 容器以 NAS `1000:100` 运行，无监听端口、只读 rootfs、无 Linux capability。
- `icloudpd` 单文件程序只在 256 MB 内存临时盘解包运行；该临时盘允许执行但保留
  `nosuid,nodev`，容器退出即清空，不授予任何 NAS 数据目录执行权限。
- 原片写入 `/volume1/ApplePhotos/originals`；凭据与 session 写入
  `/volume1/ApplePhotosRuntime`，两者不共享快照。
- 下载命名包含 iCloud asset ID，避免多个设备产生同名 `IMG_0001` 时互相覆盖。
- 达到卷使用率 80% 后，新下载周期 fail closed。
- Apple 密码不进入 Compose、Git 或命令参数。交互认证把它保存到仅 NAS 用户可读的
  keyring 状态中，以便无人值守续传；该私有运行态必须按 Apple 账号凭据保护。
- 不启用 Advanced Data Protection 的账号才能使用当前 `icloudpd` Web API 登录方式；
  iPhone 的“允许在网页上访问 iCloud 数据”也必须开启。

## 1. 只读计划与安装

先在 NAS 上从精确 Git SHA 的部署包目录运行只读计划：

```bash
./bootstrap.sh
```

确认路径后，以 NAS 管理员执行一次安装：

```bash
sudo ./bootstrap.sh --execute --confirm CREATE_ICLOUD_PHOTOS_ARCHIVE
```

安装会创建原片子卷与私有运行目录、拉取精确镜像并启用每日快照 timer，但不会启动
iCloud 下载器。重复执行是幂等更新，不会删除原片或凭据。

若 NAS 到 Docker Hub 超时，由可信主机对上述精确 digest 执行 `docker save`，使用
`gzip -n` 生成冻结归档并把归档 SHA-256 与文件一起传到 NAS。先 dry-run，再显式导入：

```bash
sudo ./load-offline-image.sh \
  --archive /受限路径/icloudpd-image.tar.gz \
  --archive-sha256 <64位归档摘要>

sudo ./load-offline-image.sh \
  --archive /受限路径/icloudpd-image.tar.gz \
  --archive-sha256 <同一摘要> \
  --execute --confirm LOAD_ICLOUDPD_OFFLINE_IMAGE

sudo env \
  ICLOUDPD_IMAGE=sha256:6fe2cb61721e21f16a1a6506e623b0ae584495ff81d2e1faad72b55043443122 \
  ./bootstrap.sh --execute --confirm CREATE_ICLOUD_PHOTOS_ARCHIVE
```

导入器先验证冻结归档摘要，再验证实际 image ID；bootstrap 只允许官方 registry digest
或这一精确离线 image ID，并把选择写入 root-only `.env`。普通 tag、不同 image ID 或
摘要漂移全部 fail closed。

## 2. 私密认证

Apple ID 只在 NAS 终端输入，不要写入聊天、Git 或 shell history：

```bash
sudo /volume1/ApplePhotosRuntime/deploy/set-apple-id.sh
sudo /volume1/ApplePhotosRuntime/deploy/operator.sh authenticate
```

按提示输入 Apple 密码与双重认证验证码。中国大陆 iCloud 默认使用 `cn` domain；若
账号实际在全球区，可在受限 `.env` 中设置 `ICLOUD_DOMAIN=com` 后重新认证。认证过期
时，容器会写入 `/volume1/ApplePhotosRuntime/state/reauth-required` 并变为 unhealthy；
重新运行上述认证命令即可，通常不需要重建容器。

## 3. Canary 与全量下载

认证后先只下载最近 10 项：

```bash
sudo /volume1/ApplePhotosRuntime/deploy/operator.sh canary
```

确认照片、视频、Live Photo 和 XMP 可读取后，再启动全量循环：

```bash
sudo /volume1/ApplePhotosRuntime/deploy/operator.sh start
sudo /volume1/ApplePhotosRuntime/deploy/operator.sh status
sudo /volume1/ApplePhotosRuntime/deploy/operator.sh logs
```

首次几 TB 下载可能持续数天。下载器每轮完整遍历后等待 6 小时；失败会保留已完成
文件并在下一轮续传。不要把“容器正在运行”等同于“全量备份已完成”，验收时需要对照
iCloud 项目数、NAS 文件数与总字节，并随机回读照片、普通视频和 Live Photo。

## 4. 停止、恢复与清理边界

普通停止不会删除数据：

```bash
sudo /volume1/ApplePhotosRuntime/deploy/operator.sh stop
```

每日快照位于 `/volume1/.apple-photos-snapshots`，默认保留 30 份。恢复应先停止下载器，
从只读快照复制精确文件回原片子卷，再重新启动。不要把快照直接改为可写，也不要把
运行凭据复制进图库。

删除原片、快照、keyring/session 或整个部署均不属于普通停用，必须另行取得精确确认。
NAS Btrfs 快照仍与原盘共故障域；如果未来停止使用 iCloud，应再增加一份离线硬盘或
异地备份。
