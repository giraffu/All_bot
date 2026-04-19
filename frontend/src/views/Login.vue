<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import api from '@/api'
import { message } from 'ant-design-vue'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)

const handleTelegramAuth = async (user: any) => {
  loading.value = true
  try {
    const response = await api.post('/auth/telegram', user)
    if (response.data?.access_token) {
      const userData = response.data.user
      
      // 校验用户身份
      const allowedIdentities = ['内门弟子', '核心弟子', '真传弟子']
      const allowedGroups = ['金丹期', '元婴期', '化神期', '炼虚期', '合体期', '大乘期', '渡劫期']
      
      const isAllowed = allowedIdentities.includes(userData.current_identity) || 
                        allowedGroups.includes(userData.user_group)
                        
      if (!isAllowed) {
        message.error('权限不足：只有金丹期及以上境界，或内门及以上身份的弟子才能登录 Web 端')
        return
      }

      authStore.setAuth(response.data.access_token, userData)
      message.success('登录成功！')
      router.push('/profile')
    } else {
      throw new Error('Invalid token response')
    }
  } catch (error: any) {
    console.error('Login error:', error)
    message.error(error.response?.data?.detail || '登录失败，请重试')
  } finally {
    loading.value = false
  }
}

const checkWebAppLogin = async () => {
  // Check if we are running inside Telegram Mini App
  const tg = (window as any).Telegram
  if (tg && tg.WebApp && tg.WebApp.initData) {
    loading.value = true
    try {
      const initData = tg.WebApp.initData
      // Send initData to backend for verification
      const response = await api.post('/auth/telegram', { initData })
      
      if (response.data?.access_token) {
        const userData = response.data.user
        
        // 校验用户身份
        const allowedIdentities = ['内门弟子', '核心弟子', '真传弟子']
        const allowedGroups = ['金丹期', '元婴期', '化神期', '炼虚期', '合体期', '大乘期', '渡劫期']
        
        const isAllowed = allowedIdentities.includes(userData.current_identity) || 
                          allowedGroups.includes(userData.user_group)
                          
        if (!isAllowed) {
          message.error('权限不足：只有金丹期及以上境界，或内门及以上身份的弟子才能登录 Web 端')
          return false
        }

        authStore.setAuth(response.data.access_token, userData)
        message.success('Mini App 自动登录成功！')
        
        // Expand WebApp to full height if possible
        if (tg.WebApp.expand) {
          tg.WebApp.expand()
        }
        
        router.push('/profile')
        return true // Successfully logged in via WebApp
      }
    } catch (error: any) {
      console.error('WebApp Login error:', error)
      // Don't show error message here, let it fallback to widget
    } finally {
      loading.value = false
    }
  }
  return false // Not in WebApp or failed
}

const renderTelegramWidget = () => {
  const container = document.getElementById('telegram-widget-container')
  if (!container) return

  // Prevent multiple widgets
  container.innerHTML = ''

  // Create script tag for Telegram widget
  const script = document.createElement('script')
  script.async = true
  script.src = 'https://telegram.org/js/telegram-widget.js?22'
  
  // 从环境变量读取 Bot 用户名，或者直接在这里写死（注意：不带 @ 符号）
  const botUsername = import.meta.env.VITE_TELEGRAM_BOT_USERNAME || 'YourBotUsername'
  
  script.setAttribute('data-telegram-login', botUsername) 
  script.setAttribute('data-size', 'large')
  script.setAttribute('data-radius', '8')
  script.setAttribute('data-request-access', 'write')
  script.setAttribute('data-userpic', 'false')

  // Bind callback to global window object
  ;(window as any).onTelegramAuth = handleTelegramAuth
  script.setAttribute('data-onauth', 'onTelegramAuth(user)')

  container.appendChild(script)
}

onMounted(async () => {
  // Try WebApp auto-login first
  const isWebAppLogged = await checkWebAppLogin()
  
  // If not in WebApp, render the traditional widget
  if (!isWebAppLogged) {
    renderTelegramWidget()
  }
})
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-950 relative overflow-hidden">
    <!-- 沉浸式背景光效 -->
    <div class="absolute top-0 left-0 w-full h-full overflow-hidden z-0 pointer-events-none">
      <div class="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-600/20 blur-[120px]"></div>
      <div class="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-purple-600/20 blur-[120px]"></div>
    </div>

    <div class="relative z-10 max-w-md w-full space-y-8 bg-slate-900/60 backdrop-blur-xl p-10 rounded-2xl shadow-2xl border border-slate-700/50">
      <div>
        <div class="flex justify-center">
          <div class="h-20 w-20 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-full flex items-center justify-center shadow-[0_0_30px_rgba(99,102,241,0.4)] border border-indigo-400/30">
            <span class="text-white text-4xl drop-shadow-md">🪷</span>
          </div>
        </div>
        <h2 class="mt-6 text-center text-3xl font-extrabold text-white tracking-widest drop-shadow-sm">
          合欢密宗
        </h2>
        <p class="mt-3 text-center text-sm text-indigo-200/80 tracking-wide">
          修仙主题 AI 图像与视频工作台
        </p>
      </div>
      
      <div class="mt-10 flex flex-col items-center justify-center space-y-6">
        <a-spin :spinning="loading" tip="正在开启结界...">
          <div class="bg-white/5 p-6 rounded-xl border border-white/10 backdrop-blur-sm w-full flex justify-center hover:bg-white/10 transition-colors duration-300">
            <div id="telegram-widget-container" class="min-h-[40px] flex items-center justify-center">
              <!-- Widget will be rendered here -->
            </div>
          </div>
        </a-spin>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Custom styles if needed */
:deep(.ant-spin-nested-loading > div > .ant-spin) {
  color: #a5b4fc; /* indigo-300 */
}
:deep(.ant-spin-dot-item) {
  background-color: #818cf8; /* indigo-400 */
}
</style>
