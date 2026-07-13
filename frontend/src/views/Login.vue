<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore, checkWebAccess } from '@/stores/auth'
import api from '@/api'
import { message } from 'ant-design-vue'
import { LockOutlined, UserOutlined } from '@ant-design/icons-vue'

const FORCE_PASSWORD_LOGIN_KEY = 'force_password_login'
const PREFERRED_LOGIN_USERNAME_KEY = 'preferred_login_username'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const loading = ref(false)
const usernameInputRef = ref<{ focus?: () => void } | null>(null)
const telegramWidgetContainerRef = ref<HTMLDivElement | null>(null)
const telegramAuthHint = ref('')

const pwdFormState = reactive({
  username: '',
  password: ''
})

const TELEGRAM_AUTH_LOADING_HINT = '正在加载 Telegram 授权...'
const TELEGRAM_WEBAPP_DATA_PARAM = 'tgWebAppData'
const TELEGRAM_WEBAPP_OUTER_PARAM_BOUNDARY = /&tgWebApp(?:Version|Platform|ThemeParams|StartParam)=/

type TelegramWebAppLike = {
  initData?: string
  platform?: string
  expand?: () => void
}

const resolveAuthErrorMessage = (error: any, fallback: string) => {
  const data = error?.response?.data
  if (typeof data?.detail === 'string' && data.detail.trim()) {
    return data.detail
  }
  if (typeof data?.message === 'string' && data.message.trim()) {
    return data.message
  }
  return fallback
}

const extractTelegramInitDataFromParamSource = (source: string) => {
  const normalized = source.replace(/^[?#]/, '')
  if (!normalized) return ''

  const parsedValue = new URLSearchParams(normalized).get(TELEGRAM_WEBAPP_DATA_PARAM)
  if (parsedValue?.includes('auth_date=') && parsedValue.includes('hash=')) {
    return parsedValue
  }

  const marker = `${TELEGRAM_WEBAPP_DATA_PARAM}=`
  const markerIndex = normalized.indexOf(marker)
  if (markerIndex < 0) return ''

  const valueWithRest = normalized.slice(markerIndex + marker.length)
  const boundaryIndex = valueWithRest.search(TELEGRAM_WEBAPP_OUTER_PARAM_BOUNDARY)
  const rawValue = boundaryIndex >= 0
    ? valueWithRest.slice(0, boundaryIndex)
    : valueWithRest

  if (!rawValue) return ''
  if (!/%(?:26|3D)/i.test(rawValue)) return rawValue

  try {
    return decodeURIComponent(rawValue)
  } catch {
    return rawValue
  }
}

const readTelegramLaunchInitData = () => (
  extractTelegramInitDataFromParamSource(window.location.hash)
  || extractTelegramInitDataFromParamSource(window.location.search)
)

const resolveTelegramInitData = (webApp?: TelegramWebAppLike) => {
  const sdkInitData = webApp?.initData?.trim()
  return sdkInitData || readTelegramLaunchInitData()
}

const hasTelegramLaunchContext = (webApp?: TelegramWebAppLike) => (
  Boolean(webApp?.platform && webApp.platform !== 'unknown')
  || window.location.hash.includes('tgWebApp')
  || window.location.search.includes('tgWebApp')
)

const shouldPreferPasswordLogin = () =>
  route.query.mode === 'password'
  || sessionStorage.getItem(FORCE_PASSWORD_LOGIN_KEY) === '1'

const restorePreferredPasswordLogin = async () => {
  const preferredUsername = sessionStorage.getItem(PREFERRED_LOGIN_USERNAME_KEY)
  if (preferredUsername && !pwdFormState.username) {
    pwdFormState.username = preferredUsername
  }

  sessionStorage.removeItem(FORCE_PASSWORD_LOGIN_KEY)
  sessionStorage.removeItem(PREFERRED_LOGIN_USERNAME_KEY)

  message.info('请使用刚设置的道号与密咒登录。')
  await nextTick()
  usernameInputRef.value?.focus?.()
}

const handlePasswordLogin = async () => {
  if (!pwdFormState.username || !pwdFormState.password) {
    message.warning('请填写道号与密咒')
    return
  }
  
  loading.value = true
  try {
    const response = await api.post('/auth/login', pwdFormState)
    if (response.data?.access_token) {
      authStore.setAuth(response.data.access_token, response.data.user)
      message.success('破界成功！')
      router.push('/profile')
    }
  } catch (error: any) {
    console.error('Password Login error:', error)
    message.error(error.response?.data?.detail || '破界失败，请检查道号与密咒')
  } finally {
    loading.value = false
  }
}

const handleTelegramAuth = async (user: any) => {
  loading.value = true
  try {
    const response = await api.post('/auth/telegram', user)
    if (response.data?.access_token) {
      const userData = response.data.user
      
      // 校验用户身份
      if (!checkWebAccess(userData)) {
        message.error('权限不足：只有练气期及以上境界，或内门及以上身份的弟子才能登录 Web 端')
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
  const webApp = (window as any).Telegram?.WebApp as TelegramWebAppLike | undefined
  const initData = resolveTelegramInitData(webApp)
  if (initData) {
    loading.value = true
    try {
      // Send initData to backend for verification
      const response = await api.post('/auth/telegram', { initData })
      
      if (response.data?.access_token) {
        const userData = response.data.user
        
        // 校验用户身份
        if (!checkWebAccess(userData)) {
          message.error('权限不足：只有练气期及以上境界，或内门及以上身份的弟子才能登录 Web 端')
          return false
        }

        authStore.setAuth(response.data.access_token, userData)
        message.success('Mini App 自动登录成功！')
        
        // Expand WebApp to full height if possible
        webApp?.expand?.()
        
        router.push('/profile')
        return true // Successfully logged in via WebApp
      }
    } catch (error: any) {
      console.error('WebApp Login error:', error)
      const errorMessage = resolveAuthErrorMessage(
        error,
        'Mini App 自动登录失败，请从 Bot 个人中心重新打开。'
      )
      telegramAuthHint.value = errorMessage
      message.error(errorMessage)
    } finally {
      loading.value = false
    }
  } else if (hasTelegramLaunchContext(webApp)) {
    telegramAuthHint.value = '当前入口缺少 Telegram 授权信息，请从 Bot 个人中心点击 Mini App 自动登录。'
  }
  return false // Not in WebApp or failed
}

const renderTelegramWidget = () => {
  const container = telegramWidgetContainerRef.value
  if (!container) return

  // Prevent multiple widgets
  container.innerHTML = ''
  if (!telegramAuthHint.value) {
    telegramAuthHint.value = TELEGRAM_AUTH_LOADING_HINT
  }

  // Create script tag for Telegram widget
  const script = document.createElement('script')
  script.async = true
  script.src = 'https://telegram.org/js/telegram-widget.js?22'
  
  // 从环境变量读取 Bot 用户名，或者直接在这里写死（注意：不带 @ 符号）
  const botUsername = import.meta.env.VITE_TELEGRAM_BOT_USERNAME
  if (!botUsername) {
    if (!telegramAuthHint.value || telegramAuthHint.value === TELEGRAM_AUTH_LOADING_HINT) {
      telegramAuthHint.value = 'Telegram 授权配置缺失，请使用已绑定的道号与密咒登录。'
    }
    return
  }
  
  script.setAttribute('data-telegram-login', botUsername) 
  script.setAttribute('data-size', 'large')
  script.setAttribute('data-radius', '8')
  script.setAttribute('data-request-access', 'write')
  script.setAttribute('data-userpic', 'false')
  script.addEventListener('load', () => {
    window.setTimeout(() => {
      if (container.querySelector('iframe')) {
        if (telegramAuthHint.value === TELEGRAM_AUTH_LOADING_HINT) {
          telegramAuthHint.value = ''
        }
      } else if (telegramAuthHint.value === TELEGRAM_AUTH_LOADING_HINT) {
        telegramAuthHint.value = 'Telegram 授权未显示，请从 Bot 个人中心点击 Mini App 自动登录。'
      }
    }, 2500)
  })
  script.addEventListener('error', () => {
    if (!telegramAuthHint.value || telegramAuthHint.value === TELEGRAM_AUTH_LOADING_HINT) {
      telegramAuthHint.value = 'Telegram 授权加载失败，请从 Bot 个人中心点击 Mini App 自动登录。'
    }
  })

  // Bind callback to global window object
  ;(window as any).onTelegramAuth = handleTelegramAuth
  script.setAttribute('data-onauth', 'onTelegramAuth(user)')

  container.appendChild(script)
}

const handleForgotPassword = () => {
  message.info('请使用下方 Telegram 授权登录后，前往个人中心重置密咒。')
}

onMounted(async () => {
  if (shouldPreferPasswordLogin()) {
    await restorePreferredPasswordLogin()
    renderTelegramWidget()
    return
  }

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

    <div class="relative z-10 max-w-md w-full space-y-6 bg-slate-500/60 backdrop-blur-xl p-8 rounded-2xl shadow-2xl border border-slate-400/50">
      <div>
        <div class="flex justify-center">
          <div class="h-16 w-16 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-full flex items-center justify-center shadow-[0_0_30px_rgba(99,102,241,0.4)] border border-indigo-400/30">
            <span class="text-white text-3xl drop-shadow-md">🪷</span>
          </div>
        </div>
        <h2 class="mt-4 text-center text-2xl font-extrabold text-white tracking-widest drop-shadow-sm">
          合欢密宗
        </h2>
        <p class="mt-2 text-center text-xs text-indigo-200/80 tracking-wide">
          修仙主题 AI 图像与视频工作台
        </p>
      </div>
      
      <a-spin :spinning="loading" tip="正在开启结界...">
        <div class="space-y-6">
          <!-- 账号密码登录区域 -->
          <div class="space-y-4">
            <a-input 
              ref="usernameInputRef"
              v-model:value="pwdFormState.username" 
              size="large" 
              placeholder="道号" 
              class="bg-slate-500/50 border-slate-400 text-white placeholder-slate-400 focus:border-indigo-500"
            >
              <template #prefix>
                <UserOutlined class="text-slate-400" />
              </template>
            </a-input>
            
            <a-input-password 
              v-model:value="pwdFormState.password" 
              size="large" 
              placeholder="密咒" 
              class="bg-slate-500/50 border-slate-400 text-white placeholder-slate-400 focus:border-indigo-500"
              @pressEnter="handlePasswordLogin"
            >
              <template #prefix>
                <LockOutlined class="text-slate-400" />
              </template>
            </a-input-password>
            
            <div class="flex justify-between items-center">
              <a-button type="link" size="small" class="text-indigo-400 px-0" @click="handleForgotPassword">
                忘记密咒？
              </a-button>
            </div>
            
            <a-button 
              type="primary" 
              size="large" 
              block 
              class="bg-indigo-600 hover:bg-indigo-500 border-none shadow-lg shadow-indigo-600/30 font-bold tracking-widest"
              @click="handlePasswordLogin"
            >
              破 界 登 录
            </a-button>
          </div>

          <!-- 分割线 -->
          <div class="relative flex items-center py-2">
            <div class="flex-grow border-t border-slate-400/50"></div>
            <span class="flex-shrink-0 mx-4 text-slate-500 text-xs tracking-wider">或使用 Telegram 开启结界</span>
            <div class="flex-grow border-t border-slate-400/50"></div>
          </div>

          <!-- Telegram 登录区域 -->
          <div class="flex justify-center">
            <div class="bg-white/5 p-4 rounded-xl border border-white/10 backdrop-blur-sm w-full flex flex-col items-center justify-center hover:bg-white/10 transition-colors duration-300">
              <div ref="telegramWidgetContainerRef" class="min-h-[40px] flex items-center justify-center">
                <!-- Widget will be rendered here -->
              </div>
              <div
                v-if="telegramAuthHint"
                class="mt-3 text-center text-xs leading-5 text-indigo-100/80"
              >
                {{ telegramAuthHint }}
              </div>
            </div>
          </div>
        </div>
      </a-spin>
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

/* 覆盖 ant-input 内部的背景色以适应深色模式 */
:deep(.ant-input-affix-wrapper),
:deep(.ant-input-password) {
  background-color: rgba(30, 41, 59, 0.5);
  border-color: rgba(51, 65, 85, 1);
}
:deep(.ant-input) {
  background-color: transparent;
  color: var(--theme-text-primary);
  -webkit-text-fill-color: var(--theme-text-primary);
  opacity: 1;
}
:deep(.ant-input::placeholder) {
  color: var(--theme-input-placeholder);
}
:deep(.ant-input-password-icon) {
  color: rgba(148, 163, 184, 1);
}
:deep(.ant-input-password-icon:hover) {
  color: rgba(165, 180, 252, 1);
}
</style>
