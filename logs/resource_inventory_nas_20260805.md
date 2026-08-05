# NAS 资源证据（2026-08-05）

- 目标：`192.168.1.150`，UGREEN NAS。
- UGOS 管理页：本次只读网络探测可访问。
- 可用容量：`16.4 TB`，来源为用户在 2026-08-05 明确提供；尚未取得 NAS 管理
  权限，未通过存储池实时 API/页面复核，不记录为 live 探测值。
- 规划上限：永久数据先按 80% 计算，约 `13.1 TB`；其余留给 MinIO 元数据、
  索引、快照和增长。到达门限时停止迁移，不静默跳过。
- MinIO：本次探测 9000/9001 未部署；仓库已准备 `ops/media_archive_nas/`，尚未
  在 NAS 执行。
- 镜像证据：2026-08-05 通过 registry manifest 只读查询固定
  `minio/minio@sha256:14cea493…8936e` 与
  `minio/mc@sha256:a7fe349e…11727`；部署时消费完整 digest，不使用 latest tag。
- SSH：端口可达但当前密钥未获授权，因此未读取文件系统、存储池、Docker、
  Btrfs 或防火墙 live 状态，也未进行任何 NAS mutation。
- 后续补证：获得管理权限后记录实际可用/总容量、文件系统、存储池、目录真实
  bind path、快照能力、MinIO digest/健康/TLS/权限/versioning 和防火墙验证。

本证据不包含密码、token、私钥或对象 URL。
