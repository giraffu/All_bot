---
name: allbot-cloud-ssh
description: "诊断和恢复 AllBot 云主机 SSH 访问，覆盖 DigitalOcean 等 Linux 云主机的 DNS、超时、拒绝连接、主机密钥变化、公钥认证、ProxyJump 与控制台救援。用户报告 SSH 失败、卡住、频繁断连、Permission denied、REMOTE HOST IDENTIFICATION HAS CHANGED、端口不可达，或准备新增/轮换云主机 SSH 配置时必须使用。"
---

# AllBot 云主机 SSH

先建立只读证据链，再选择最小修复。不要把“能读取凭据或远端状态”理解为允许
修改云防火墙、主机防火墙、`sshd`、账号、密钥、实例或生产服务。

## 资料路由

- 云控制面别名、密钥边界、初始化和轮换：
  `docs/子模块_云控制面SSH密钥管理_cloud_ssh_access.md`
- 私网/Tailscale/公网代理边界：
  `docs/子模块_网络暴露与代理穿透_network_proxy.md`
- DigitalOcean DNS、Firewall 或公网入口：
  叠加 `allbot-cloudflare-ops`
- 线上事故、日志和服务异常：
  叠加 `allbot-diagnosing-bugs`；需要采集环境日志时再叠加 `ops-log-monitor`
- 发布、重启、迁移或重建：
  叠加 `allbot-ops-deployment`，并遵守生产 mutation 授权

## 诊断闭环

### 1. 固定连接事实

记录目标环境、SSH Host 别名、预期用户名、端口、入口类型（公网、Tailscale、
堡垒机或云控制台）和完整错误文本。只读取密钥文件名、权限与公钥指纹，不输出
私钥、token、密码、完整 `authorized_keys` 或未经脱敏的 `ssh -vvv`。

先确认 OpenSSH 最终配置，避免被 `~/.ssh/config` 的通配项覆盖：

```bash
ssh -G <host-alias> | sed -n \
  '/^hostname /p;/^user /p;/^port /p;/^identityfile /p;/^identitiesonly /p;/^proxyjump /p'
```

### 2. 按连接阶段定位

按顺序停止在第一个失败阶段，不要同时改多个层：

1. **名称解析**：`getent ahosts <hostname>`；失败时核对别名和实时云控制台 IP。
2. **TCP 可达**：`nc -vz -w 5 <hostname> <port>`；超时优先检查路由、来源
   公网 IP、云防火墙和主机防火墙，拒绝连接优先检查端口与 `sshd` 监听。
3. **SSH 握手**：`ssh -vv -o BatchMode=yes -o ConnectTimeout=10 <host-alias>`；
   保存并脱敏从 `Connecting to` 到最终错误的最小片段。
4. **认证**：核对用户名、`IdentityFile`、`IdentitiesOnly yes`、本地私钥权限
   和公钥指纹；`Permission denied (publickey)` 不等于网络故障。
5. **会话稳定性**：连接成功后才区分 idle 断线、路径丢包、资源耗尽或远端
   shell/profile 卡住。保活只能缓解空闲连接回收，不能修复网络或服务故障。

### 3. 按错误分流

- `Could not resolve hostname`：检查 Host 别名、DNS 和目标 IP。
- `Connection timed out`：检查目标是否运行、端口、路由、云/主机防火墙与本地
  网络是否拦截该端口。
- `Connection refused`：网络已到主机；通过云控制台检查 `ssh`/`sshd` 状态、
  实际监听端口和 `ListenAddress`。
- `Permission denied (publickey)`：检查用户、公钥是否安装到该用户、
  `~/.ssh`/`authorized_keys` 所有权权限，以及服务端认证日志。
- `REMOTE HOST IDENTIFICATION HAS CHANGED`：先从云控制台或可信带外渠道核对
  新主机指纹和实例是否重建；确认后才按精确 hostname/IP 删除旧记录。不得用
  `StrictHostKeyChecking no` 绕过。
- 私网主机：先单独验证堡垒机，再验证第二跳；使用 `ProxyJump`/`ssh -J`。
  NAT 网关只提供出站连接，不是 SSH 入站入口。

### 4. 带外只读检查

常规 SSH 不可用时，优先用供应商 Web/Recovery Console 获取只读证据：

```bash
systemctl status ssh --no-pager || systemctl status sshd --no-pager
ss -lntp
sshd -t
journalctl -u ssh -u sshd --since "-30 min" --no-pager
ufw status verbose
```

同时核对云防火墙、主机防火墙、磁盘/内存是否耗尽。DigitalOcean Web Console
仍依赖网络、`sshd`、防火墙与 Droplet Agent；网络或 `sshd` 已损坏时改用
Recovery Console。

## 修复红线

- 修改 `sshd_config` 前先保留现有会话并运行 `sshd -t`；验证新会话成功后
  才关闭旧会话。
- 新密钥验证成功前不得删除旧公钥；不得把私钥粘贴到控制台或 Git。
- 删除 `known_hosts` 记录前必须核对可信指纹，只删除精确目标。
- 不因 SSH 失败直接 reboot、reset password、放宽 `0.0.0.0/0` 防火墙、
  启用密码/root 登录、重建实例或修改生产状态。
- 任何修复先说明目标、预期影响、回滚方式和所需授权；没有明确授权时只报告
  诊断结论与建议命令。

## 交付格式

输出“现象 → 首个失败阶段 → 证据 → 最可能原因 → 下一项最小验证/修复”。
若仍未定位，列出尚缺的精确信息，不把假设写成结论。

## 最小验证

```bash
python3 /home/hfy/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  .codex/skills/allbot-cloud-ssh
python3 scripts/doc_quality_checker.py
```
