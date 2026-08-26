---
name: "allbot-lan-media-gallery"
description: "维护局域网只读图库、iCloud 原片单向 NAS 备份与 LAN 浏览。"
---

# AllBot 局域网备份图库

## 必读入口

1. `lan_media_gallery/README.md`
2. `docs/子模块_局域网备份图库_lan_media_gallery.md`
3. iCloud 原片备份读取 `ops/icloud_photos_nas/README.md`
4. 涉及容器部署时叠加 `allbot-ops-deployment`

## 固定边界

- 服务独立于社区 Gallery、R2 和业务库；图库只读挂载 `compose.yml` 白名单，禁止
  备份根、校验清单、聊天数据库及 AppWebCache。
- 账户、索引、缩略图和转码只写 XDG 运行态；容器非 root、只读 rootfs、无
  capabilities、`no-new-privileges`，上传关闭。
- iCloud 只单向下载原片、视频、Live Photo 和 XMP，禁止云端/本地删除；原片与
  keyring/session 分离，快照不得含凭据。
- 镜像固定精确 digest；LAN 地址、密码和 live 状态不写 Skill，凭据只进私有文件。
- 启停、升级、修改可读目录或账户均属于 LAN mutation，需要用户明确要求。
- 普通停止不得删除运行态目录；清空账户/索引必须另行确认。

## 最小验证

```bash
.venv/bin/python -m pytest -q lan_media_gallery/tests \
  tests/ops/test_icloud_photos_nas_contract.py
docker compose -f lan_media_gallery/compose.yml config
python3 scripts/doc_quality_checker.py
```

部署后还要验证健康状态、LAN HTTP、认证、`Upload.enabled=false`，并通过
`docker inspect` 确认每个备份挂载的 `RW=false`。
