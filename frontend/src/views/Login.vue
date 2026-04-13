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
      authStore.setAuth(response.data.access_token, response.data.user)
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

onMounted(() => {
  renderTelegramWidget()
})
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
    <div class="max-w-md w-full space-y-8 bg-white p-10 rounded-xl shadow-lg border border-gray-100">
      <div>
        <div class="flex justify-center">
          <div class="h-16 w-16 bg-blue-600 rounded-full flex items-center justify-center shadow-md">
            <span class="text-white text-2xl font-bold">AB</span>
          </div>
        </div>
        <h2 class="mt-6 text-center text-3xl font-extrabold text-gray-900">
          All_bot Web
        </h2>
        <p class="mt-2 text-center text-sm text-gray-600">
          修仙主题 AI 图像与视频生成平台
        </p>
      </div>
      
      <div class="mt-8 flex flex-col items-center justify-center space-y-6">
        <a-spin :spinning="loading" tip="正在登录...">
          <div id="telegram-widget-container" class="min-h-[50px] flex items-center justify-center">
            <!-- Widget will be rendered here -->
          </div>
        </a-spin>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Custom styles if needed */
</style>
