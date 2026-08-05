# NAS 资源证据（2026-08-05）

- 目标：`192.168.1.150`，UGREEN NAS。
- UGOS 管理页：本次使用管理员账号登录成功；明文密码不写入知识库或仓库。
- 主存储池：live SSH 显示 `/volume1` 为 Btrfs，device size `16.02 TiB`，
  statfs 可用约 `16.01 TiB`，当前几乎为空。用户提供的 `16.4 TB` 属于十进制/
  展示口径，与系统约 16 TiB 的容量级别一致。另有 `/volume2` Btrfs，约
  `450 GiB`，不纳入 AllBot Archive 规划。
- 规划上限：永久数据先按 80% 计算，约 `13.1 TB`；其余留给 MinIO 元数据、
  索引、快照和增长。到达门限时停止迁移，不静默跳过。
- 固件与 Docker：用户明确确认重启后，依次从 `1.0.0.0556` 升级到
  `1.0.0.1977`、`1.7.0.3125`、`1.12.1.0002`，最终 live
  `OS_VERSION=1.17.0.0095`。Docker 官方应用已安装到 Volume 1，Engine
  `29.4.3`、Compose `v5.1.3`，Docker root 为 `/volume1/@docker`。
- 镜像证据：2026-08-05 通过 registry manifest 只读查询固定
  `minio/minio@sha256:14cea493…8936e` 与
  `minio/mc@sha256:a7fe349e…11727`；部署时消费完整 digest，不使用 latest tag。
- 已完成部署：`/volume1/AllBotArchive` 使用独占的 `minio-data`、
  `minio-certs`、`ca`、`config` 和 `deploy`；固件权限迁移一度把预置目录放宽
  为 0777，启动前已恢复 root 管理，`.env` 和私钥为 0600。服务端证书 SAN 包含
  `IP:192.168.1.150` 与 `DNS:minio`。CA 私钥只保存在本地主机权限 600 的
  `~/.local/share/allbot/media-archive-pki`，未复制到 NAS。
- NAS 直连 Docker Hub 超时；使用本地主服务器已按 manifest digest 验证的
  amd64 镜像，通过一次性 LAN 流导入 NAS，运行时固定 image ID。MinIO 已健康
  监听 TLS 9000/9001；三个桶、archive versioning、不可删除 Worker 与分析只读
  policy 已完成。真实写读回校验通过，Worker DeleteObject 返回 AccessDenied，
  验证对象随后由管理员清理；容器重启后重新健康。
- UGOS 防火墙配置 `AllBot Archive MinIO` 已启用：仅 `192.168.1.115` 可访问
  9000，`192.168.1.0/24` 可访问 9001，其它来源拒绝；SSH、S3 和控制台从允许
  来源复测成功。
- Btrfs 快照：UGOS Snapshot 只能看到已登记 shared folder，不能直接纳入普通
  `AllBotArchive` 目录。因此已将该目录无损转换为独立 Btrfs subvolume（ID 257），
  安装并启用 `allbot-media-archive-snapshot.timer`，每天约 03:20 执行、随机延迟
  最多 15 分钟并保留 7 份。首个只读快照
  `/volume1/.allbot-archive-snapshots/AllBotArchive-20260805T113839Z` 已验证
  `ro=true`；MinIO 在新 subvolume 上恢复 healthy，bootstrap 幂等退出 0。转换期
  旧目录副本在新服务和首个快照验收后已删除，当前可从只读快照恢复。
- SSH：固件升级移除了 `/home/nas`，公钥授权随之失效；账号 home 已迁到持久化
  `/volume1/@home/nas` 并恢复原公钥。本机专用密钥
  `~/.ssh/allbot_nas_dxp8800_rsa` 已重新验证可用，指纹为
  `SHA256:tTmOiTSqJtoxBfXt+8sv4LqgLppLboTFPqIEVj1qXJg`，账号 `nas` 属于 admin
  组；sudo 需要交互密码。已在本机 `~/.ssh/config` 登记 alias
  `allbot-nas-archive`，不保存密码。
- 本地主服务器 Worker 凭据保存于权限 0600 的运行态配置，不进入仓库；本证据
  不记录密码、access key、secret key 或私钥内容。

本证据不包含密码、token、私钥或对象 URL。一次性远端 staging 已在校验后删除。
