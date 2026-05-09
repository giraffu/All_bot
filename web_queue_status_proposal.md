# Web 端“宏观大盘”（全局排队状态）开发方案

基于业务需求，我们在 Web 端个人中心（Profile）新增“宗门炼丹炉状态（系统排队）”模块。本方案采用“宏观大盘”模式（即只展示系统当前的整体排队任务数、各类型的排队数量以及在线节点状态），与 Telegram Bot 中的 `/queue` 命令保持对齐。

## 1. 方案设计目标
- **低成本与高复用**：直接复用底层已有的 `get_queue_info()` 逻辑，无需改动核心队列和调度引擎。
- **解耦隔离**：遵守架构红线，Web API 层负责对外提供安全、规范的接口封装，内部由 `task_core` 或 `api_client` 与内网核心通讯。
- **最佳实践**：遵循 `FastAPI` 与 `Vue3 Composition API` 的最佳实践，契合现有代码库（Ant Design Vue + Tailwind CSS）。

---

## 2. 后端 API 层改造

### 2.1 扩展现有 Web API 路由
为了保持代码整洁，无需新增 `system.py`，建议直接将获取队列大盘信息的接口置于 `src/web_api/routers/tasks.py` 下。

**端点设计**：
- **Path**: `GET /api/tasks/queue-status`
- **Auth**: 需要 JWT 鉴权（`Depends(get_current_user)`），防止接口被外部恶意爬取。

**代码实现思路 (`src/web_api/routers/tasks.py`)**：
```python
from fastapi import APIRouter, Depends
from typing import Annotated

from src.web_api.dependencies import get_current_user
from src.database.models import User
from src.services.image_service import image_service

# 假设 router 是现成的 tasks router
router = APIRouter(prefix="/tasks", tags=["Tasks"])

# 使用 Annotated 依赖注入
CurrentUserDep = Annotated[User, Depends(get_current_user)]

@router.get("/queue-status")
async def get_queue_status(current_user: CurrentUserDep) -> dict:
    """获取当前系统的排队宏观大盘数据"""
    # image_service 底层会调用 api_client 获取 /system/status
    status = await image_service.get_queue_info()
    if not status:
        return {"comfy_online": False, "queue_size": 0, "queue_by_type": {}}
    return status
```

---

## 3. 前端 Vue3 改造

### 3.1 接口调用规范
现有的前端项目使用的是 TypeScript (`frontend/src/api/index.ts`)，并且直接导出了全局 Axios 实例。因此无需在 API 层做额外的方法封装，直接在组件中使用 `api.get('/tasks/queue-status')` 即可。

### 3.2 `Profile.vue` 组件修改
遵循 Vue 最佳实践，使用 `<script setup lang="ts">` 和响应式引用。

**1. 引入图标与状态定义**
```typescript
import api from '@/api'
import { useI18n } from 'vue-i18n'
import { Server, Activity, Layers } from 'lucide-vue-next'

const { t, locale } = useI18n() // 解构出 t 函数供模板使用

const queueStatus = ref({
  loading: false,
  data: {
    comfy_online: false,
    queue_size: 0,
    queue_by_type: {} as Record<string, number>
  }
})

const fetchQueueStatus = async () => {
  queueStatus.value.loading = true
  try {
    const res = await api.get('/tasks/queue-status')
    queueStatus.value.data = res.data
  } catch (error) {
    console.error('Failed to fetch queue status', error)
  } finally {
    queueStatus.value.loading = false
  }
}

onMounted(() => {
  // 现有逻辑...
  fetchQueueStatus()
  
  // 可选：如果希望实时刷新，可以加入轮询 (polling)
  // const timer = setInterval(fetchQueueStatus, 30000)
  // onBeforeUnmount(() => clearInterval(timer))
})
```

**2. UI 模板插入**
在 `Profile.vue` 的“快捷指引”卡片下方（或适当位置），插入全新的排队信息卡片。已修复为 Tailwind 原生加载动画，移除了原方案错误的 daisyUI 样式。

```vue
<!-- 宗门炼丹炉状态 (Queue Status) -->
<div class="bg-slate-500/40 rounded-xl p-5 border border-slate-400/50 mt-4 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)]">
  <div class="flex items-center gap-3 mb-4">
    <div class="p-2 bg-cyan-500/20 rounded-xl border border-cyan-500/30">
      <Server class="w-5 h-5 text-cyan-400 drop-shadow-[0_0_5px_rgba(56,189,248,0.5)]" />
    </div>
    <h3 class="text-lg font-bold text-slate-200 drop-shadow-sm">{{ t('profile.queue_status_title', '炼丹炉状态') }}</h3>
    <!-- 在线状态指示器 -->
    <div class="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border"
         :class="queueStatus.data.comfy_online ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border-rose-500/20'">
      <div class="w-1.5 h-1.5 rounded-full" :class="queueStatus.data.comfy_online ? 'bg-emerald-400 animate-pulse shadow-[0_0_5px_rgba(16,185,129,0.8)]' : 'bg-rose-400'"></div>
      {{ queueStatus.data.comfy_online ? '运行中' : '休息中' }}
    </div>
  </div>

  <!-- 加载状态 -->
  <div v-if="queueStatus.loading && queueStatus.data.queue_size === 0" class="flex justify-center py-6">
    <svg class="animate-spin h-6 w-6 text-cyan-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
  </div>
  
  <div v-else class="space-y-3">
    <div class="flex justify-between items-center bg-slate-800/50 p-3 rounded-xl border border-slate-600/50">
      <div class="flex items-center gap-2 text-slate-300">
        <Activity class="w-4 h-4 text-indigo-400" />
        <span class="text-sm font-medium">总排队任务</span>
      </div>
      <span class="text-lg font-bold text-slate-100">{{ queueStatus.data.queue_size }} <span class="text-xs text-slate-400 font-normal">个</span></span>
    </div>

    <!-- 任务类型分布 -->
    <div v-if="Object.keys(queueStatus.data.queue_by_type || {}).length > 0" class="grid grid-cols-2 gap-2 mt-2">
      <div v-for="(count, type) in queueStatus.data.queue_by_type" :key="type"
           class="flex flex-col bg-slate-800/30 p-2.5 rounded-lg border border-slate-700/50">
        <span class="text-xs text-slate-400 mb-1 truncate">{{ t(`task_type.${type}`, type) }}</span>
        <span class="text-sm font-bold text-slate-200">{{ count }} 个</span>
      </div>
    </div>
  </div>
</div>
```

## 4. 国际化 (i18n) 适配要求
根据架构红线，后端仅返回原始数值与枚举，所有多语言文本由前端负责。
我们需要在 Vue i18n 语言包（`zh.json` 和 `en.json`）中补充：
- 标题相关的 Key（例如 `profile.queue_status_title`）
- 任务类型相关的映射字典，例如将 `img2img` 翻译为 `图生图`，将 `ltx_video` 翻译为 `视频生成` 等。

## 5. 落地步骤总结
1. **后端路由**：在 `src/web_api/routers/tasks.py` 添加 `/api/tasks/queue-status` 接口端点，正确导入 `get_current_user` 和 `User`。
2. **前端组件**：在 `frontend/src/views/Profile.vue` 添加响应式变量和 API 请求。
3. **前端 UI**：在 Profile 的快捷指引模块下方插入对应的卡片，并使用正确的 Tailwind + Ant Design Vue 样式风格。
4. **多语言词条**：在 `frontend/src/locales/` 补充 i18n 词条映射。