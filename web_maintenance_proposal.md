# Web 端维护模式实现方案 (Proposal)

## 1. 背景与目标
目前系统在通过 `safe_deploy.sh` 部署时，会在 `tg-bot` 容器内创建 `/app/MAINTENANCE` 文件以拦截新任务并平滑清空队列。然而，**Web 前端（用户工作台）以及对应的 `web-api` 目前并没有接入此维护状态**。这就导致在后端服务重建期间，Web 用户仍然可以操作，可能会遭遇 API 报错（如 502/503）、任务丢失或页面卡死。

*注意：本方案仅针对 C 端用户 Web 工作台，不包含管理员 Admin Dashboard。*

**本方案目标**：在不破坏现有 `safe_deploy.sh` 核心逻辑的前提下，以最小的代价为 Web 端实现优雅的全局维护模式，并且保证维护状态能伴随容器的重建自动解除。

---

## 2. 核心架构设计
采用 **“后端中间件拦截 + 前端路由重定向”** 的方式，单点控制源继续复用容器内的 `/app/MAINTENANCE` 文件。

1. **部署层**：部署脚本同时向 `web-api` 容器写入维护标志文件。
2. **API 层 (FastAPI)**：通过全局中间件检测文件是否存在，存在则拦截请求并返回 `503 Service Unavailable`（需特殊处理 CORS 跨域问题）。
3. **前端层 (Vue3)**：Axios 全局响应拦截器捕捉到 503 状态后，自动跳转至专门的 `/maintenance` 维护提示页。

---

## 3. 具体实施步骤

### Step 1: 升级部署脚本 (`safe_deploy.sh`)
在脚本第一步（开启维护模式）中，除了给 `tg-bot` 开启外，也顺带给 `web-api` 开启。

```bash
# 修改 safe_deploy.sh 开启维护模式的逻辑：
if [ -n "$(docker ps -q -f name=^tg-bot$)" ]; then
    docker exec tg-bot touch /app/MAINTENANCE
    # 新增下面这行：给 Web API 也加上维护锁
    docker exec web-api touch /app/MAINTENANCE 2>/dev/null || true
    echo "✅ 已开启 tg-bot 与 web-api 维护模式。"
fi
```
> **原理优势**：当脚本执行重建 `web-api` 时，全新的容器是不包含 `/app/MAINTENANCE` 文件的，这意味着**维护模式会自动解除**，无需编写任何清理逻辑，与现有 Bot 端的行为完全保持一致。

### Step 2: 后端 API 中间件实现 (`src/web_api/main.py`)
在 FastAPI 注册一个自定义中间件，每次请求进来时检查文件是否存在。
**注意：为了让自带的 `CORSMiddleware` 正常处理 `OPTIONS` 预检请求和跨域头，自定义的维护中间件必须在 `CORSMiddleware` 之前添加（使其处于内层）。**

```python
import os
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

class MaintenanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # 检测维护标志文件
        if os.path.exists("/app/MAINTENANCE"):
            return JSONResponse(
                status_code=503,
                content={
                    "code": 5030,
                    "message": "System is under maintenance. Please try again later.",
                    "intent": "MAINTENANCE"
                }
            )
        return await call_next(request)

# --------- 在 main.py 的中间件注册部分 ---------
# 先添加 MaintenanceMiddleware
app.add_middleware(MaintenanceMiddleware)

# 必须确保 CORSMiddleware 是最后添加的（在 Starlette 中最后添加的在最外层执行）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[...], # 这里保留原有的 CORS 配置
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Step 3: 前端拦截与页面跳转 (`frontend/src/`)

**1. 拦截器更新 (`frontend/src/api/index.ts`)**
在已有的 Axios 响应错误拦截器中，增加对 `503` 状态码的处理逻辑：

```typescript
// 在 if (status === 401) { ... } else if (...) 分支中增加：
} else if (status === 503) {
  // 如果是维护模式，直接跳转到维护页面
  if (data?.code === 5030 || data?.intent === 'MAINTENANCE') {
    if (router.currentRoute.value.path !== '/maintenance') {
      router.push('/maintenance')
    }
  } else {
    message.error(t('api.system_error'))
  }
}
```

**2. 增加维护视图页面 (`frontend/src/views/Maintenance.vue`)**
创建一个全屏的维护提示页面，禁止用户操作，并提示稍后刷新：

```vue
<template>
  <div class="h-screen w-screen flex flex-col items-center justify-center bg-gray-900 text-white">
    <div class="text-6xl mb-6">🛠️</div>
    <h1 class="text-3xl font-bold mb-4">{{ $t('system.maintenance_title') }}</h1>
    <p class="text-gray-400 mb-8">{{ $t('system.maintenance_desc') }}</p>
    <a-button type="primary" @click="checkStatus">
      {{ $t('system.refresh') }}
    </a-button>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import api from '@/api'

const router = useRouter()
const checkStatus = async () => {
  try {
    // 请求一下 /api/health，如果不报错且不是 503，说明维护结束
    await api.get('/api/health')
    router.push('/')
  } catch (error) {
    // 依然维护中，无操作
  }
}
</script>
```

**3. 注册路由 (`frontend/src/router/index.ts`)**
将 `/maintenance` 添加到路由白名单，**必须配置 `requiresAuth: false`**，防止未登录状态下触发死循环。

```typescript
{
  path: '/maintenance',
  name: 'Maintenance',
  component: () => import('@/views/Maintenance.vue'),
  meta: { requiresAuth: false } // 必须显式标记免登录
}
```

**4. 补充多语言 (i18n) 键值**
在 `shared/locales/zh.json` 和 `en.json` 中添加维护页面的翻译文本，避免页面显示原生 key：

```json
// zh.json 示例
"system": {
  "maintenance_title": "系统维护中",
  "maintenance_desc": "我们正在进行系统升级与维护，请稍后再试...",
  "refresh": "刷新状态"
}
```

---

## 4. 方案总结
本方案完全复用了现有架构中的**文件锁机制 (`touch /app/MAINTENANCE`)**，避免了引入 Redis 全局锁带来的额外复杂度。
- **前端体验**：用户在操作时，一旦请求 API 被拦截，会立即跳转到友好的维护画面，避免看到一堆报错弹窗。
- **运维体验**：继续使用 `bash safe_deploy.sh` 一键发布，Bot 和 Web 自动同步进入/退出维护模式。
