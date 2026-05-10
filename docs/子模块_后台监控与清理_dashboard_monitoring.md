# 子模块: 后台监控与清理 (Dashboard & Monitoring)

## 1. 目标与范围
本模块包含面向管理员的 Vue3/FastAPI 数据看板（Dashboard）和自动化运行的幽灵任务自愈协程（Zombie Cleaner）。其目标是提供全系统数据可视化（包含用户统计、服务器节点存活状态、Gallery 广场管理、历史任务回溯），并在出现 Worker 节点宕机或并发锁死锁时，主动释放用户锁定资源并退还灵石，保障整个生成集群的高可用性。

## 2. 架构图与调用链

```mermaid
sequenceDiagram
    autonumber
    participant Admin as 管理员
    participant DB as Dashboard FastAPI
    participant Redis as Redis (DB1 & DB2)
    participant ZC as 僵尸清理协程 (zombie_cleaner_service)
    participant PG as PostgreSQL

    Admin->>DB: 1. GET /api/stats (请求监控数据)
    DB->>Redis: 2. DB2 扫描 active workers & queue size
    DB->>PG: 3. 统计今日新用户与消耗 (通过SQL聚合)
    DB-->>Admin: 4. 返回可视化图表数据
    
    loop 余额监控与统计轮询 (balance_monitor.py)
        BM->>TG_API: 异步增量拉取 Stars 流水
        BM->>TON_API: 异步查询 TON/USDT 余额
        BM->>Redis: 缓存外部余额与 last_tx_id
    end

    loop 后台定时巡检 (每 1 分钟)
        ZC->>Redis: 5. DB1 提取所有 active_tasks (状态=running/pending)
        ZC->>Redis: 6. 检查 task_id 是否已超时 (>10分钟)
        alt 发现僵尸任务
            ZC->>PG: 7. 执行退还灵石 (refund_credits)
            ZC->>Redis: 8. 删除 DB1 user_lock 和 active_tasks 记录
            ZC->>DB: 9. (可选) 通知中控 API 双向删除任务防止幽灵算力
        end
    end
```

## 3. 核心代码片段

### 核心层隔离与 Dashboard API (dashboard/backend/routers/system.py)
[`system.py`](file:///home/hfy/APP/All_bot/dashboard/backend/routers/system.py)
```python
@router.post("/system/refund_bot_task")
async def refund_bot_task(req: RefundTaskRequest, db: AsyncSession = Depends(get_db)):
    """Force terminate a stuck task, refund credits and release concurrency lock."""
    # 遵循 Core Isolation，Dashboard 不再直连 Redis 或手动修改锁，而是调用 Core 层统一接口
    from src.core.task_core import get_system_task_stats, force_terminate_task
    from src.services.permission_service import permission_service
    
    tasks, _ = await get_system_task_stats()
    task = tasks[req.task_id]
    
    # 1. Refund
    await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund_admin_force")
        
    # 2. Release lock and remove task via Core API
    await force_terminate_task(req.task_id, user_id=user_id)
    
    return {"status": "success"}
```

### Dashboard 接口鉴权 (dashboard/backend/main.py)
[`main.py:L62-L80`](file:///home/hfy/APP/All_bot/dashboard/backend/main.py#L62)
```python
@app.middleware("http")
async def check_auth_header(request: Request, call_next):
    """
    后台 Dashboard 的基础认证中间件。
    检查 HTTP 请求头中的 ADMIN_SECRET 是否与环境变量匹配。
    """
    # 排除不需要鉴权的路由
    if request.url.path in ["/api/health", "/docs", "/openapi.json"]:
        return await call_next(request)
        
    admin_secret = request.headers.get("Authorization")
    if not admin_secret or admin_secret.replace("Bearer ", "") != os.getenv("ADMIN_SECRET"):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        
    return await call_next(request)
```

## 4. 接口定义 (OpenAPI 3.0)

```yaml
openapi: 3.0.3
info:
  title: Dashboard API
  version: 1.0.0
paths:
  /api/stats:
    get:
      summary: 获取系统大盘监控数据
      security:
        - bearerAuth: []
      responses:
        '200':
          description: 返回在线节点数、排队长度和用户统计
          content:
            application/json:
              schema:
                type: object
                properties:
                  active_workers:
                    type: integer
                  queue_size:
                    type: integer
                  today_new_users:
                    type: integer
```

## 5. 单元与集成测试要求
- **覆盖率基准**：自愈与清退逻辑要求 **≥90%** 覆盖率。
- **核心用例**：
  1. `test_zombie_cleaner_refunds_correctly`：在 Redis 中伪造一个耗时 601 秒且带有 cost=10 的任务，运行 `clean_zombies`，断言用户的灵石增加了 10，且 Redis 锁被删除。
  2. `test_zombie_cleaner_ignores_fresh_tasks`：伪造一个耗时 30 秒的任务，运行巡检，断言没有任何清理操作发生。
  3. `test_dashboard_auth_middleware`：发送未携带 `ADMIN_SECRET` 的请求到 `/api/stats`，断言被中间件 401 拦截。

## 6. 部署与回滚步骤
- **部署**：
  建议使用根目录下的 `safe_deploy.sh` 脚本进行安全平滑部署，它会自动重建 Dashboard 服务。
  如需手动部署，可运行：
  ```bash
  cd dashboard
  docker-compose up -d --build
  ```
  *注意*：后台依赖宿主机网络，通常配置为 `network_mode: "host"`，通过 FRP 将 8001 端口穿透至公网供管理员访问。
- **环境要求**：必须在 `.env` 中正确配置复杂的 `ADMIN_SECRET`，并确保前后端保持一致。
- **回滚**：
  无数据库结构变更，拉取上一版本直接重启容器。

## 7. 监控告警规则 (SLI/SLO)
- **SLI**：僵尸任务清理的触发频率与成功率，Dashboard 接口平均响应时间。
- **SLO**：每分钟不超过 5 个僵尸任务。
- **告警策略**：
  - **Critical**：当 1 小时内触发的 `clean_zombies` 次数超过总排队任务数的 5%，意味着底层的 ComfyUI Worker 出现系统性瘫痪（可能因 OOM 宕机），系统必须立刻发送最高级别 P0 告警给研发团队。
