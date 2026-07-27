# AllBot 发布入口

代码发布只支持受保护 main 的完整 Git SHA、不可变 release bundle 和
digest-pinned artifact。日常入口：

```bash
# 无 mutation 预览
python scripts/release.py promote [--modules <modules>] [--sha <full-sha>]

# 用户明确确认正式发布后，在同一候选增加
python scripts/release.py promote [--modules <modules>] [--sha <full-sha>] \
  --confirm-prod
```

测试部署、严格 migration、配置收敛、回滚与恢复的完整命令和门禁只以
`docs/子模块_Git不可变发布_git_immutable_release.md` 及 `release.py --help`
为准。

禁止旧同步脚本、rsync、现场 build、源码 bind mount、mutable tag 和自由
Compose。代码发布不修改 `/etc/allbot/test.env` 或 `/etc/allbot/prod.env`；
配置变化走独立 `config-plan/config-apply` 授权。

本地 `safe_deploy.sh` 仅用于云正式整体故障时的受控灾备，必须按
`docs/子模块_本地正式灾备切换_local_prod_fallback.md` 单独授权。
