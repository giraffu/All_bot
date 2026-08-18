# AllBot 发布入口

代码发布只支持受保护 main 的完整 Git SHA 和 digest-pinned artifact，不再
生成或消费 release bundle。先构建明确模块：

```bash
python3 scripts/release.py build \
  --module <module> --sha <40位main-sha>
```

部署只接受构建结果中的精确 `repository@sha256:digest`，一次一个模块：

```bash
python3 scripts/release.py deploy \
  --env test --module <module> --artifact <repository@sha256:digest>

# 只有用户明确授权正式发布后才可执行
python3 scripts/release.py deploy \
  --env prod --module <module> --artifact <repository@sha256:digest> \
  --confirm-prod
```

状态、回滚、migration、Pages 与 GPU operator 的完整参数只以
`docs/子模块_Git不可变发布_git_immutable_release.md` 及 `release.py --help`
为准。

禁止旧同步脚本、rsync、现场 build、源码 bind mount、mutable tag 和自由
Compose。代码发布不修改 `/etc/allbot/test.env` 或 `/etc/allbot/prod.env`。
GitHub 手动入口为 `module-build.yml` 和 `module-deploy.yml`；该 workflow 仍拒绝
GPU/ComfyUI。GPU artifact 由 operator 直接调用 `release.py build`，可显式选择
云端 `allbot-sgp1` Buildx builder；构建不触发任何 RunPod/LAN runtime rollout。

本地 `safe_deploy.sh` 仅用于云正式整体故障时的受控灾备，必须按
`docs/子模块_本地正式灾备切换_local_prod_fallback.md` 单独授权。
