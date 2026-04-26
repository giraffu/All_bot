# 子模块: 社区广场与分级存储 (Gallery & Storage)

## 1. 目标与范围
本模块包含两大核心：一是系统级的冷热分级存储与大文件传输加速；二是依托历史生成记录衍生出的社区广场。它通过 MinIO 对象存储引用传递机制、CDN 边缘加速（R2）、以及 `GalleryPost` / `UserInteraction` 的防并发覆盖和原创保护机制，大幅降低内网带宽与主库压力。

## 2. 架构图与调用链

```mermaid
classDiagram
    class History {
        +UUID id
        +int user_id
        +str type
        +dict params
        +bool allow_contribute
        +bool is_template
        +datetime created_at
    }
    class GalleryPost {
        +UUID id
        +UUID task_id (History.id)
        +int author_id
        +str lora_model
        +int likes_count
        +int applied_count
        +datetime submitted_at
    }
    class UserInteraction {
        +UUID id
        +int user_id
        +UUID post_id
        +str action_type (like/dislike/apply)
        +UniqueConstraint(user_id, post_id, action_type)
    }
    History "1" -- "0..1" GalleryPost : 投稿关联
    GalleryPost "1" -- "0..*" UserInteraction : 互动记录
```

```mermaid
sequenceDiagram
    autonumber
    actor U as 用户 (前端)
    participant API as BFF API (routers/gallery.py)
    participant PG as PostgreSQL
    participant R2 as Cloudflare R2
    participant MinIO as 归档桶 (Cold)

    U->>API: 1. POST /api/gallery/posts/submit/{task_id}
    API->>PG: 2. 验证 History.allow_contribute == True
    PG-->>API: 3. 允许投稿
    API->>PG: 4. 创建 GalleryPost 实体
    API->>R2: 5. 异步守护线程：将 MinIO 热数据转存 R2
    R2-->>API: 6. 同步完成，返回加速域名
    API-->>U: 7. 投稿成功
    U->>API: 8. POST /api/gallery/posts/{post_id}/interact
    API->>PG: 9. 写入 UserInteraction (带 Unique 约束)
    PG-->>API: 10. 拦截重复点赞/更新 likes_count
    API-->>U: 11. 更新互动状态
```

## 3. 核心代码片段

### 社区原创保护投稿 (src/web_api/routers/gallery.py)
[`gallery.py:L538-L560`](file:///home/hfy/APP/All_bot/src/web_api/routers/gallery.py#L538-L560)
```python
@router.post("/posts/submit/{task_id}")
async def submit_to_gallery(task_id: str, db: AsyncSession = Depends(get_db)):
    """防抄袭保护的社区投稿接口，只允许原始创作者投稿"""
    history = await db.get(History, task_id)
    
    if not history or history.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作他人记录")
        
    if not history.allow_contribute or history.is_template:
        raise HTTPException(
            status_code=400, 
            detail="该作品由套用他人模板生成，为保护原创，禁止再次发布至广场！"
        )
    
    # 执行投稿...
    post = GalleryPost(task_id=history.id, author_id=current_user.id)
    db.add(post)
    await db.commit()
    return {"message": "发布成功"}
```

### 并发互动保护 (src/web_api/routers/gallery.py)
[`gallery.py:L436-L450`](file:///home/hfy/APP/All_bot/src/web_api/routers/gallery.py#L436-L450)
```python
@router.post("/posts/{post_id}/interact")
async def interact_with_post(post_id: str, action: str):
    """利用 UniqueConstraint 捕获 IntegrityError，防并发连点"""
    try:
        interaction = UserInteraction(user_id=uid, post_id=post_id, action_type=action)
        db.add(interaction)
        await db.flush()
        
        # 使用数据库层面的原子更新，防覆盖
        stmt = update(GalleryPost).where(GalleryPost.id == post_id)\
                                  .values(likes_count=GalleryPost.likes_count + 1)
        await db.execute(stmt)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="您已经操作过了")
```

## 4. 接口定义 (OpenAPI 3.0)

```yaml
openapi: 3.0.3
info:
  title: Gallery & Storage API
  version: 1.0.0
paths:
  /api/gallery/posts/submit/{task_id}:
    post:
      summary: 将个人历史记录推送到社区广场
      parameters:
        - in: path
          name: task_id
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: 发布成功
        '400':
          description: 非原创作品（allow_contribute=False），拒绝发布
        '403':
          description: 无权操作他人记录
```

## 5. 单元与集成测试要求
- **覆盖率基准**：此模块覆盖率要求 **≥85%**。
- **核心用例**：
  1. `test_duplicate_submission`：对同一个 `task_id` 连续调用两次投稿接口，断言数据库只存在一条 `GalleryPost`，第二次抛出 400 错误。
  2. `test_prevent_template_resubmission`：构建一个 `allow_contribute=False` 的 History，调用投稿，断言被严格拦截。
  3. `test_concurrent_likes`：使用多线程/协程对同一帖子进行 50 次并发点赞，断言最终 `likes_count` 精确为 50。

## 6. 部署与回滚步骤
- **部署**：
  广场与存储服务与 BFF 网关集成。部署执行：
  `docker-compose -f deploy/docker-compose.yml up -d --build web-api`
- **回滚**：
  如果异步转存逻辑导致 MinIO 崩溃，可回滚旧镜像或手动重启存储容器：`docker restart minio-server`。

## 7. 监控告警规则 (SLI/SLO)
- **SLI**：排行榜查询 `/api/gallery/posts` 的响应时间；MinIO `_region_map` 离线签名命中率。
- **SLO**：广场首页 API 平均响应延迟 < 200ms；直传文件预签名失败率 < 0.1%。
- **告警策略**：
  - **Critical**：前端频发 503 超时错误，表示 MinIO 已进入假死离线状态（taking drive offline），触发最高级别警报，人工介入重启存储节点。
  - **Warning**：热门数据转存 R2 失败次数 > 5 次/分钟，通过群组通报 CDN 同步异常。
