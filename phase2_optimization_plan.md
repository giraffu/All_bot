# 🛠️ 第二阶段实施方案：数据库 N+1 性能优化

## 🎯 目标
消除系统列表查询中的潜在 N+1 性能隐患，提升接口响应速度，降低数据库连接池压力。主要聚焦于计费套餐渲染和 Web 画廊列表获取逻辑。

## 📍 优化点 1：`billing_callbacks.py` 代码去重与防御性预加载
**文件路径**: `src/handlers/callbacks/billing_callbacks.py`

### 🔍 现状分析
当前的回调函数（如 `recharge_stars_menu_callback`, `recharge_rmb_menu_callback` 等）从数据库加载了 `MembershipPlan` 列表后，通过 `for plan in plans:` 进行遍历。
虽然这里的 `plan` 本身是一张单表，**没有直接触发 N+1 延迟加载**的属性读取，但是每次生成键盘都要执行多条重复或相似的查询逻辑。此外，不同接口针对“月卡(duration_days > 0)”和“直充(duration_days == 0)”的过滤以及价格排序字段均有所不同。

### 🛠️ 重构方案
由于 `plans` 数据在系统中属于低频更新的高频读取数据，且这里的查询并无关系表（N+1）的直接问题，为了极致性能与代码整洁，我们将：
1. **统一查询入口**：不再在 4 个回调里写重复的 `select(MembershipPlan)` 代码，抽离一个公共方法 `_get_active_plans(session, is_rmb: bool, is_subscription: bool)`。在内部动态构建 `.where(MembershipPlan.duration_days > 0)` 或 `== 0` 的查询条件，并根据 `is_rmb` 决定按 RMB 还是 Star 的价格升序排列。
2. **内存缓存或批量加载**：如果未来在 Plan 上加外键（例如关联多语言翻译表），公共方法可以直接改为 `joinedload` 预加载，从而防御 N+1。

---

## 📍 优化点 2：`gallery.py` 画廊接口的 N+1 根除
**文件路径**: `src/web_api/routers/gallery.py`

### 🔍 现状分析
在画廊相关的 **3 个列表查询接口**（`get_gallery_posts`, `get_my_gallery_posts`, `get_my_favorite_posts`）中，存在严重的 N+1 隐患及大量重复代码：
```python
# 循环内部（每个接口重复约 40 行）：
for post in posts:
    # ❌ 每次循环都要单独发起一次对 History 表的数据库查询！
    hist_res = await session.execute(select(History).where(History.task_id == post.task_id))
    history = hist_res.scalars().first()
```
如果一页加载 20 条帖子，就会额外发起 20 次 `History` 的单条查询，这是经典的 N+1 性能杀手！

### 🛠️ 重构方案：批量查询 (in_) 映射与代码复用
为了避免 N+1 并提升代码可维护性，我们将采取**“先批量获取，再内存组装”**的策略，并提取公共函数：
1. **抽离公共响应组装函数**：创建一个私有函数 `_build_post_responses(session, posts, user_likes, user_dislikes)`，统一处理这 3 个接口的返回数据组装。
2. **收集外键**：在循环外，提取当前页所有帖子的 `task_id`：
   ```python
   task_ids = [post.task_id for post in posts if post.task_id]
   ```
3. **批量查询 (in_)**：一次性查出所有关联的历史记录：
   ```python
   histories = []
   if task_ids:
       histories = (await session.execute(
           select(History).where(History.task_id.in_(task_ids))
       )).scalars().all()
   ```
4. **建立内存映射 (Dict Map)**：将批量查出的结果转为字典，以便在循环中直接以 `O(1)` 时间复杂度获取：
   ```python
   history_map = {h.task_id: h for h in histories}
   ```
5. **替换循环内的查询**：在 `for post in posts:` 内部，直接使用 `history_map.get(post.task_id)` 代替 `await session.execute(...)`。

---

## 🚀 预期收益
- **画廊加载性能提升**：Web 端的画廊翻页和刷新速度将获得显著提升，数据库查询次数从 `1 + 1 + N` 降为固定的 `3` 次（主表 + Interaction + History）。
- **代码可维护性增强**：通过提取 `_build_post_responses` 函数，`gallery.py` 能够精简上百行冗余代码。
- **降低数据库压力**：减少了大量无谓的 TCP 连接和事务开销，极大提升了 API 的并发承载能力。
