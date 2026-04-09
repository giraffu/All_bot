# 废弃字段平滑移除计划 (Deprecated Columns Migration Plan)

## 背景 (Background)
系统曾存在 `temp_credits`（临时灵石）和 `temporary_ingot` 字段。目前系统已全面采用单轨制代币（`credits`）体系，这些字段已被完全废弃，相关逻辑已在核心系统中移除。
为保持代码整洁并防止后续开发者误用，需要从 ORM 模型和数据库表中彻底移除这两个字段。

## 目标 (Objective)
在**不影响当前正在运行的线上服务（Bot, Dashboard 等）**的前提下，安全、平滑地从代码库和数据库中删除 `temp_credits` 和 `temporary_ingot` 字段。

## 为什么不能直接删除数据库字段？ (Why not drop columns directly?)
如果直接在数据库中执行 `ALTER TABLE users DROP COLUMN temp_credits`，而此时旧版本的容器（包含旧版 `models.py`）仍在运行：
1. 旧容器在执行 `SELECT * FROM users` 或读取用户对象时，会向数据库请求这两个已不存在的列。
2. 数据库会抛出 `ProgrammingError: column "temp_credits" does not exist` 错误。
3. 这将导致旧服务大面积崩溃，影响用户正常使用。

因此，必须采用**两步走（Two-Phase Drop）**的策略来实现平滑过渡。

---

## 实施步骤 (Execution Steps)

### 阶段一：代码层面解耦 (Phase 1: Code Decoupling)
*目标：让所有业务代码和 API 接口不再依赖或返回废弃字段。*

1. **清理遗留的兼容性返回**：
   - 移除 `src/services/permission_service.py` 中 `get_user_detailed_stats` 返回的 `"temp_credits": 0`。
   - 移除 `dashboard/backend/routers/stats.py` 和 `users.py` 中为了前端兼容而保留的 `total_temporary_ingot` 和 `temporary_ingot` 字段。
   - *(注意：前端如果强依赖这些字段，需同步更新前端代码，不再读取这些字段)*。
2. **从 ORM 模型中移除**：
   - 在 `src/database/models.py` 中，删除 `User` 类下的 `temp_credits` 和 `temporary_ingot` 列定义。
3. **部署新代码**：
   - 将包含上述修改的新代码构建并部署到生产环境。
   - **此时不生成也不执行任何数据库迁移脚本**。数据库表中依然保留这两个废弃列（仅占用极少量空间），但代码层面已经彻底不再认识它们了。

### 阶段二：数据库层面物理清理 (Phase 2: Database Physical Cleanup)
*目标：在确认所有旧容器均已下线后，从数据库中物理删除这两个字段。*

1. **确认旧服务已下线**：
   - 等待阶段一的代码完全上线，确保没有任何运行中的容器还在使用旧版的 `models.py`。
2. **生成 Alembic 迁移脚本**：
   - 在项目根目录下执行命令：
     ```bash
     alembic revision --autogenerate -m "drop_deprecated_columns_temp_credits"
     ```
   - Alembic 会对比代码（无这两个字段）和数据库（有这两个字段），自动生成包含 `op.drop_column('users', 'temp_credits')` 和 `op.drop_column('users', 'temporary_ingot')` 的迁移脚本。
3. **执行数据库迁移**：
   - 容器重启时，`init_db` 中的 `run_alembic_upgrade()` 会自动应用这个脚本，物理删除数据库中的列。
   - 至此，废弃字段被彻底、安全地移除。

---

## 执行建议
建议在当前的开发周期内完成**阶段一**，并在下一次系统维护或版本大更时执行**阶段二**。