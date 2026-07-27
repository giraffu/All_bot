# Compat / Seam 当前退出表

本表只跟踪仍在运行或仍需运行态确认的兼容层。已删除、已下沉和已完成条目
保存在 `docs/archive/knowledge-base-cleanup-20260727/`，不再进入默认上下文。

## 状态定义

- `active-compat`：仍有受支持调用方或历史数据，暂不能删除。
- `runtime-verification-required`：代码调用已收敛，但需环境/数据观测后删除。
- `test-seam`：有明确 fake/环境差异，作为可替换 seam 保留。

## 当前条目

| 对象 | 状态 | 当前用途 | 删除条件 |
| --- | --- | --- | --- |
| `image_to_video_fsm.start_custom_video` | active-compat | `/custom_video` 与旧 callback 命名 | 产品入口和已发消息不再使用旧名 |
| `MODE_IMAGE_TO_VIDEO = MODE_VIDEO_LORA` | active-compat | 历史任务值和旧 payload | 数据/调用方全部迁移到 canonical type |
| QQCC Wan22 单模型字段与旧模型名 | active-compat | 升级前场景、payload、continuation | 官方/私有配置迁移且观察窗口无旧字段 |
| QQCC `next_scene_id` 容错归一 | active-compat | 安全加载旧或损坏配置 | 所有受支持 checkpoint 重新保存且回滚点退出 |
| `video_insert` / `video_edit` | active-compat | 旧 Central endpoint/队列/worker alias | 队列与访问日志确认旧类型清零 |
| Order 历史内部用户列语义 | runtime-verification-required | 生产 schema 兼容 | 目标环境 migration/head 与 ORM 契约一致 |
| `ORDER:` / `ORDER_V2:` 双载荷 | active-compat | 旧支付 callback | 旧通道和展示调用方完全退出 |
| legacy user adopt 分支 | runtime-verification-required | 早期内部 ID/TG ID 混用记录 | 数据审计确认不存在可收养历史用户 |
| Gallery `free_edit_v2_group` 查询别名 | active-compat | 升级前客户端 | 受支持客户端只发送 v3 group 且日志清零 |
| QQCC `buttons_per_row=null` | active-compat | 旧 checkpoint 固定分行 | 官方/私有配置迁移为显式列数 |
| provider/dependencies fake | test-seam | 测试与环境 adapter 替换 | 属于有价值 seam，不按历史兼容删除 |

## 维护规则

- 新兼容层必须写清调用方、目标 canonical interface、退出信号和验证方式。
- 已删除代码不留在活跃表；删除证据进入归档或 Git 历史。
- 只有静态 `rg` 不足以删除数据/协议兼容；涉及历史 payload、队列、数据库或
  已发 Telegram callback 时必须补运行态/数据观测。
- 测试 seam 只有在 fake、环境差异或可替换 adapter 存在时保留；仅一行转发
  且无 interface 价值的浅壳应删除。
- 完成退出后同步专项文档、Skill 和审计矩阵，并运行 focused tests。
