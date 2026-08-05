---
name: "allbot-lan-media-gallery"
description: "部署和维护 AllBot 局域网只读备份图库，覆盖媒体白名单、PiGallery2 容器、账户初始化、索引缓存与 LAN 暴露。"
---

# AllBot 局域网备份图库

## 必读入口

1. `lan_media_gallery/README.md`
2. `docs/子模块_局域网备份图库_lan_media_gallery.md`
3. 涉及容器部署时叠加 `allbot-ops-deployment`

## 固定边界

- 图库是独立 LAN 服务，不复用 AllBot 社区 Gallery、R2 或业务数据库。
- 备份源只能按 `compose.yml` 白名单逐目录只读挂载；禁止挂载备份根目录、
  `SHA256SUMS`、QQ/微信数据库或 AppWebCache。
- 配置、账户、SQLite 索引、缩略图和转码结果只写独立 XDG 运行态目录。
- 容器使用宿主非 root UID/GID、只读 rootfs、drop all capabilities 和
  `no-new-privileges`；上传保持关闭。
- 镜像必须固定精确 OCI digest。LAN 地址、账户密码和 live 状态不写入 Skill；
  密码只保存到操作者私有凭据文件。
- 启停、升级、修改可读目录或账户均属于 LAN mutation，需要用户明确要求。
- 普通停止不得删除运行态目录；清空账户/索引必须另行确认。

## 最小验证

```bash
python -m pytest -q lan_media_gallery/tests
docker compose -f lan_media_gallery/compose.yml config
python scripts/doc_quality_checker.py
```

部署后还要验证健康状态、LAN HTTP、认证、`Upload.enabled=false`，并通过
`docker inspect` 确认每个备份挂载的 `RW=false`。
