# NAS 资源证据（2026-08-05）

- 目标：`192.168.1.150`，UGREEN NAS。
- UGOS 管理页：本次使用管理员账号登录成功；明文密码不写入知识库或仓库。
- 主存储池：live SSH 显示 `/volume1` 为 Btrfs，device size `16.02 TiB`，
  statfs 可用约 `16.01 TiB`，当前几乎为空。用户提供的 `16.4 TB` 属于十进制/
  展示口径，与系统约 16 TiB 的容量级别一致。另有 `/volume2` Btrfs，约
  `450 GiB`，不纳入 AllBot Archive 规划。
- 规划上限：永久数据先按 80% 计算，约 `13.1 TB`；其余留给 MinIO 元数据、
  索引、快照和增长。到达门限时停止迁移，不静默跳过。
- MinIO：本次探测 9000/9001 未部署；Docker/containerd 也未安装。UGOS 应用中心
  登录成功，但在线列表只有内置系统应用，搜索 Docker 返回 `No Content`。
- 固件门槛：live `/etc/os-release` 为 `OS_VERSION=1.0.0.0556`；UGREEN 官方下载
  中心当前 Docker `1.17.0.0028` 要求固件至少 `1.17.0.0001`。升级固件会重启
  NAS，未获得本轮单独确认，因此未执行。
- 镜像证据：2026-08-05 通过 registry manifest 只读查询固定
  `minio/minio@sha256:14cea493…8936e` 与
  `minio/mc@sha256:a7fe349e…11727`；部署时消费完整 digest，不使用 latest tag。
- 已完成准备：`/volume1/AllBotArchive` 已创建独占的 `minio-data`、
  `minio-certs`、`ca`、`config` 和 `deploy`；私有 MinIO 配置为 root-only，
  `preflight.sh` 通过。服务端证书已从 NAS 回读，SAN 包含
  `IP:192.168.1.150` 与 `DNS:minio`。CA 私钥只保存在本地主机权限 600 的
  `~/.local/share/allbot/media-archive-pki`，未复制到 NAS。
- 未完成：由于官方 Docker 应用和固件门槛未满足，MinIO 容器、三个桶、用户
  policy、versioning、防火墙和 Btrfs 快照尚未启用；9000/9001 仍未监听。
- SSH：本机专用密钥 `~/.ssh/allbot_nas_dxp8800_rsa` 已验证可用，指纹为
  `SHA256:tTmOiTSqJtoxBfXt+8sv4LqgLppLboTFPqIEVj1qXJg`，账号 `nas` 属于 admin
  组；sudo 需要交互密码。已在本机 `~/.ssh/config` 登记 alias
  `allbot-nas-archive`，不保存密码。
- 后续补证：固件和官方 Docker 应用安装后，记录目录真实 bind path、快照能力、
  MinIO digest/健康/TLS/权限/versioning 和防火墙验证。

本证据不包含密码、token、私钥或对象 URL。一次性远端 staging 已在校验后删除。
