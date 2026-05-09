<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { useAuthStore } from '@/stores/auth'
import api from '@/api'
import { message } from 'ant-design-vue'
import { 
  Wallet,
  Activity,
  CalendarCheck,
  Zap,
  Award,
  User,
  Clock,
  Lock,
  Bookmark,
  Star,
  Globe,
  Server,
  RefreshCw
} from 'lucide-vue-next'
import dayjs from 'dayjs'
import { useViewport } from '@/composables/useViewport'
import { useTelegram } from '@/composables/useTelegram'
import { watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'

const authStore = useAuthStore()
const { isMobile } = useViewport()
const { showMainButton, hideMainButton, hapticFeedback, isTMA } = useTelegram()
const { t, locale } = useI18n()
const loading = ref(true)

const queueStatus = ref({
  loading: false,
  isFirstLoad: true,
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
    queueStatus.value.isFirstLoad = false
  }
}

const toggleLanguage = async () => {
  const newLang = locale.value === 'zh' ? 'en' : 'zh'
  locale.value = newLang
  
  // Persist language to backend
  try {
    await api.patch('/users/preferences', { language_code: newLang })
  } catch (error) {
    console.error('Failed to save language preference', error)
  }
}

const bindFormState = reactive({
  username: '',
  password: ''
})
const bindingLoading = ref(false)
const showBindModal = ref(false)

const handleBindPasswordModalOpen = () => {
  showBindModal.value = true
  if (authStore.user?.username) {
    bindFormState.username = authStore.user.username
  } else {
    bindFormState.username = ''
  }
  bindFormState.password = ''

  if (isMobile.value) {
    hapticFeedback('medium')
    showMainButton('确认结契', handleBindPassword)
  }
}

watch(showBindModal, (newVal) => {
  if (!newVal) {
    hideMainButton(handleBindPassword)
  }
})

onBeforeUnmount(() => {
  hideMainButton(handleBindPassword)
})

const handleBindPassword = async () => {
  if (!bindFormState.username || !bindFormState.password) {
    message.warning('请填写道号与密咒')
    return
  }
  
  if (bindFormState.password.length < 6) {
    message.warning('密咒长度不能少于 6 位')
    return
  }
  
  bindingLoading.value = true
  try {
    await api.post('/auth/bind-password', bindFormState)
    message.success('密咒设置成功！之后可以使用该道号与密咒破界登录。')
    
    // Update local user data
    if (authStore.user) {
      authStore.user.username = bindFormState.username
      authStore.setAuth(authStore.token!, authStore.user)
    }
    
    showBindModal.value = false
    bindFormState.password = '' // Clear password
  } catch (error: any) {
    console.error('Bind password error:', error)
    
    let errorMsg = '密咒设置失败'
    const detail = error.response?.data?.detail
    
    if (detail) {
      if (Array.isArray(detail)) {
         // Handle Pydantic Validation Error array
         errorMsg = detail.map(err => {
            if (err.loc && err.loc.includes('username')) return '道号格式不正确：' + err.msg
            if (err.loc && err.loc.includes('password')) return '密咒格式不正确：' + err.msg
            return err.msg
         }).join('; ')
      } else if (typeof detail === 'string') {
         errorMsg = detail
      }
    }
    
    message.error(errorMsg)
  } finally {
    bindingLoading.value = false
  }
}

const formatDate = (dateString?: string | null) => {
  if (!dateString) return '永久有效'
  return dayjs(dateString).format('YYYY-MM-DD HH:mm')
}

const checkinLoading = ref(false)

const handleCheckin = async () => {
  checkinLoading.value = true
  try {
    const response = await api.post('/users/checkin')
    const data = response.data
    if (data.success) {
      message.success(`签到成功！获得 ${data.reward} 灵石`)
      await authStore.fetchUser() // Refresh user stats
    } else {
      if (data.error_msg) {
        message.warning(data.error_msg)
      } else {
        message.warning('今日已领取灵石，请明天再来吧！')
      }
    }
  } catch (error: any) {
    console.error('Checkin error:', error)
    message.error('签到失败，请稍后重试')
  } finally {
    checkinLoading.value = false
  }
}

onMounted(async () => {
  await authStore.fetchUser()
  loading.value = false
  fetchQueueStatus()
})
</script>

<template>
  <div class="profile-container space-y-6">
    <div class="welcome-banner bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-500 rounded-xl p-5 md:p-8 text-white shadow-lg relative overflow-hidden border border-indigo-400/50">
      <div class="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center">
        <!-- Left Section -->
        <div class="w-full md:w-auto">
          <h1 class="text-xl md:text-3xl font-bold mb-3 md:mb-2 drop-shadow-sm text-slate-100">
            {{ $t('profile.welcome_back', { name: authStore.user?.full_name || authStore.user?.username }) }}
          </h1>
          
          <div class="flex flex-wrap items-center gap-2 mb-3 md:mb-2 text-sm md:text-lg text-slate-300">
            <div class="flex items-center bg-white/5 backdrop-blur-sm border border-white/10 rounded px-2.5 py-1">
              <span class="mr-1.5 text-slate-400">{{ $t('profile.group') }}:</span> 
              <span class="font-bold text-cyan-300 drop-shadow-sm">{{ authStore.user?.user_group ? $t(`group.${authStore.user.user_group}`) : $t('group.凡人') }}</span>
            </div>
            <div class="flex items-center bg-white/5 backdrop-blur-sm border border-white/10 rounded px-2.5 py-1">
              <span class="mr-1.5 text-slate-400">{{ $t('profile.identity') }}:</span>
              <span class="font-bold text-cyan-300 drop-shadow-sm">{{ authStore.user?.current_identity ? $t(`identity.${authStore.user.current_identity}`) : $t('identity.外门弟子') }}</span>
            </div>
            <!-- Language Switcher -->
            <button @click="toggleLanguage" class="flex items-center bg-cyan-500/10 hover:bg-cyan-500/20 backdrop-blur-sm border border-cyan-500/30 hover:border-cyan-500/50 rounded px-2.5 py-1 cursor-pointer transition-all">
              <Globe :size="16" class="mr-1.5 text-cyan-400" />
              <span class="font-bold text-cyan-300 drop-shadow-sm text-sm">{{ locale === 'zh' ? 'English' : '中文' }}</span>
            </button>
          </div>

          <div class="text-xs md:text-sm text-slate-400 flex items-center drop-shadow-sm">
            <Clock :size="14" class="mr-1.5 text-slate-500" />
            <span v-if="authStore.user?.current_identity === '外门弟子' || !authStore.user?.identity_expire_at">{{ $t('profile.valid_forever') }}</span>
            <span v-else>{{ $t('profile.valid_until') }}{{ formatDate(authStore.user?.identity_expire_at) }}</span>
          </div>
        </div>
        
        <!-- Right Section -->
        <div class="mt-5 md:mt-0 w-full md:w-auto flex flex-col items-end gap-3 border-t border-white/20 md:border-0 pt-4 md:pt-0">
          <div class="flex items-center bg-white/20 backdrop-blur-md px-4 py-2 md:px-5 md:py-3 rounded-lg border border-white/30 shadow-inner w-full md:w-auto justify-between md:justify-start">
            <div class="flex items-center">
              <Wallet :size="20" class="mr-2 md:mr-3 text-cyan-200 drop-shadow-[0_0_8px_rgba(255,255,255,0.5)]" />
              <div class="flex flex-col">
                <span class="text-[10px] md:text-xs text-slate-400 font-medium leading-none mb-1">{{ $t('profile.credits') }}</span>
                <span class="text-lg md:text-2xl font-bold leading-none drop-shadow-sm text-slate-100">{{ authStore.user?.credits || 0 }}</span>
              </div>
            </div>
            <a-button v-if="false" size="small" type="primary" @click="$router.push('/billing')" class="ml-4 bg-gradient-to-r from-amber-500 to-orange-500 border-none shadow-lg hover:shadow-orange-500/50 hover:from-amber-400 hover:to-orange-400 z-50 pointer-events-auto">
              💎 充值 / 升级
            </a-button>
          </div>
          <a-button type="primary" @click="handleCheckin" :loading="checkinLoading" class="bg-gradient-to-r from-indigo-500 to-cyan-600 hover:from-indigo-400 hover:to-cyan-500 border-none text-white font-bold px-6 w-full shadow-lg hover:shadow-cyan-500/20 transition-all transform hover:-translate-y-0.5 h-10 md:h-auto z-50 pointer-events-auto">
            {{ $t('profile.checkin_btn') }}
          </a-button>
        </div>
      </div>
      
      <!-- Decorative circles -->
      <div class="absolute -top-24 -right-24 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none"></div>
      <div class="absolute -bottom-24 right-12 w-48 h-48 bg-cyan-500/10 rounded-full blur-2xl pointer-events-none"></div>
    </div>
    
    <!-- Breakthrough Conditions Section Removed -->

    <div class="bg-slate-500/50 backdrop-blur-md rounded-xl p-6 border border-slate-400/50 shadow-[0_4px_12px_rgba(0,0,0,0.2)]">
      <h3 class="text-lg font-bold text-slate-200 mb-2 flex items-center drop-shadow-sm">
        <Activity :size="20" class="mr-2 text-cyan-400 drop-shadow-[0_0_5px_rgba(56,189,248,0.5)]" /> {{ $t('profile.quick_guide') }}
      </h3>
      <p class="text-slate-400 mb-4">{{ $t('profile.quick_guide_desc') }}</p>
      <div class="flex flex-wrap gap-3">
        <a-button type="primary" @click="$router.push('/custom-features')" class="bg-gradient-to-r from-indigo-600 to-cyan-700 border-none hover:from-indigo-500 hover:to-cyan-600 shadow-md">
          <Zap :size="16" class="mr-1 inline" /> {{ $t('profile.go_to_lab') }}
        </a-button>
        <a-button type="default" @click="$router.push('/my-submissions')" class="bg-slate-500 text-cyan-300 border-cyan-500/30 hover:text-cyan-200 hover:border-cyan-400 shadow-md">
          <Bookmark :size="16" class="mr-1 inline" /> {{ $t('menu.my_submissions') }}
        </a-button>
        <a-button type="default" @click="$router.push('/my-favorites')" class="bg-slate-500 text-amber-300 border-amber-500/30 hover:text-amber-200 hover:border-amber-400 shadow-md">
          <Star :size="16" class="mr-1 inline" /> {{ $t('menu.my_favorites') }}
        </a-button>
        <a-button type="default" @click="handleBindPasswordModalOpen" class="bg-slate-500 text-indigo-300 border-indigo-500/30 hover:text-indigo-200 hover:border-indigo-400 shadow-md">
          <Lock :size="16" class="mr-1 inline" /> {{ authStore.user?.username ? $t('profile.change_password') : $t('profile.set_password') }}
        </a-button>
      </div>
    </div>

    <!-- 宗门炼丹炉状态 (Queue Status) -->
    <div class="bg-slate-500/40 rounded-xl p-5 border border-slate-400/50 mt-4 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)]">
      <div class="flex items-center gap-3 mb-4">
        <div class="p-2 bg-cyan-500/20 rounded-xl border border-cyan-500/30">
          <Server class="w-5 h-5 text-cyan-400 drop-shadow-[0_0_5px_rgba(56,189,248,0.5)]" />
        </div>
        <h3 class="text-lg font-bold text-slate-200 drop-shadow-sm">{{ t('profile.queue_status_title', '炼丹炉状态') }}</h3>
        
        <div class="ml-auto flex items-center gap-2">
          <!-- 刷新按钮 -->
          <button @click="fetchQueueStatus" 
                  class="p-1.5 rounded-lg text-cyan-400 hover:bg-cyan-500/20 transition-all border border-transparent hover:border-cyan-500/30 flex items-center justify-center cursor-pointer"
                  :disabled="queueStatus.loading"
                  :title="t('profile.refresh_queue', '刷新')">
            <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': queueStatus.loading }" />
          </button>
          
          <!-- 在线状态指示器 -->
          <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border"
               :class="queueStatus.data.comfy_online ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border-rose-500/20'">
            <div class="w-1.5 h-1.5 rounded-full" :class="queueStatus.data.comfy_online ? 'bg-emerald-400 animate-pulse shadow-[0_0_5px_rgba(16,185,129,0.8)]' : 'bg-rose-400'"></div>
            {{ queueStatus.data.comfy_online ? t('profile.online', '运行中') : t('profile.offline', '休息中') }}
          </div>
        </div>
      </div>

      <!-- 加载状态 -->
      <div v-if="queueStatus.isFirstLoad && queueStatus.loading" class="flex justify-center py-6">
        <svg class="animate-spin h-6 w-6 text-cyan-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      </div>
      
      <div v-else class="space-y-3">
        <div class="flex justify-between items-center bg-slate-800/50 p-3 rounded-xl border border-slate-600/50">
          <div class="flex items-center gap-2 text-slate-300">
            <Activity class="w-4 h-4 text-indigo-400" />
            <span class="text-sm font-medium">{{ t('profile.total_queue', '总排队任务') }}</span>
          </div>
          <span class="text-lg font-bold text-slate-100">{{ queueStatus.data.queue_size }} <span class="text-xs text-slate-400 font-normal">{{ t('profile.tasks_unit', '个') }}</span></span>
        </div>

        <!-- 任务类型分布 -->
        <div v-if="Object.keys(queueStatus.data.queue_by_type || {}).length > 0" class="grid grid-cols-2 gap-2 mt-2">
          <div v-for="(count, type) in queueStatus.data.queue_by_type" :key="type"
               class="flex flex-col bg-slate-800/30 p-2.5 rounded-lg border border-slate-700/50">
            <span class="text-xs text-slate-400 mb-1 truncate">{{ t(`task_type.${type}`, String(type)) }}</span>
            <span class="text-sm font-bold text-slate-200">{{ count }} {{ t('profile.tasks_unit', '个') }}</span>
          </div>
        </div>
      </div>
    </div>

    <div>
      <h2 class="text-xl font-bold text-slate-200 mb-4 flex items-center drop-shadow-sm">
        <span class="w-1.5 h-6 bg-cyan-500 rounded-full mr-2 shadow-[0_0_8px_rgba(56,189,248,0.5)]"></span>
        {{ $t('profile.stats') }}
      </h2>
      
      <div class="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        <a-card hoverable class="rounded-xl border border-slate-400/50 bg-slate-500/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-cyan-500/30 hover:shadow-[0_8px_24px_rgba(56,189,248,0.1)] transition-all group">
          <div class="flex items-center flex-col md:flex-row text-center md:text-left">
            <div class="w-10 h-10 md:w-12 md:h-12 bg-slate-500/50 border border-slate-400 text-cyan-400 rounded-full flex items-center justify-center mb-2 md:mb-0 md:mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(56,189,248,0.4)]">
              <User :size="isMobile ? 20 : 24" />
            </div>
            <div>
              <p class="text-slate-400 text-xs md:text-sm mb-1">{{ $t('profile.system_id') }}</p>
              <h3 class="text-lg md:text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.telegram_id || authStore.user?.id || '---' }}</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-400/50 bg-slate-500/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-indigo-500/30 hover:shadow-[0_8px_24px_rgba(99,102,241,0.1)] transition-all group">
          <div class="flex items-center flex-col md:flex-row text-center md:text-left">
            <div class="w-10 h-10 md:w-12 md:h-12 bg-slate-500/50 border border-slate-400 text-indigo-400 rounded-full flex items-center justify-center mb-2 md:mb-0 md:mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(99,102,241,0.4)]">
              <Zap :size="isMobile ? 20 : 24" />
            </div>
            <div>
              <p class="text-slate-400 text-xs md:text-sm mb-1">{{ $t('profile.generations') }}</p>
              <h3 class="text-lg md:text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.generation_count || 0 }} {{ $t('profile.times_unit') }}</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-400/50 bg-slate-500/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-emerald-500/30 hover:shadow-[0_8px_24px_rgba(16,185,129,0.1)] transition-all group">
          <div class="flex items-center flex-col md:flex-row text-center md:text-left">
            <div class="w-10 h-10 md:w-12 md:h-12 bg-slate-500/50 border border-slate-400 text-emerald-400 rounded-full flex items-center justify-center mb-2 md:mb-0 md:mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(16,185,129,0.4)]">
              <CalendarCheck :size="isMobile ? 20 : 24" />
            </div>
            <div>
              <p class="text-slate-400 text-xs md:text-sm mb-1">{{ $t('profile.checkins') }}</p>
              <h3 class="text-lg md:text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.checkin_count || 0 }} {{ $t('profile.days_unit') }}</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-400/50 bg-slate-500/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-amber-500/30 hover:shadow-[0_8px_24px_rgba(245,158,11,0.1)] transition-all group">
          <div class="flex items-center flex-col md:flex-row text-center md:text-left">
            <div class="w-10 h-10 md:w-12 md:h-12 bg-slate-500/50 border border-slate-400 text-amber-400 rounded-full flex items-center justify-center mb-2 md:mb-0 md:mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(245,158,11,0.4)]">
              <Award :size="isMobile ? 20 : 24" />
            </div>
            <div>
              <p class="text-slate-400 text-xs md:text-sm mb-1">{{ $t('profile.priority') }}</p>
              <h3 class="text-lg md:text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.priority || 0 }}</h3>
            </div>
          </div>
        </a-card>
      </div>
    </div>
    
    <div class="mt-8">
      <h2 class="text-xl font-bold text-slate-200 mb-4 flex items-center drop-shadow-sm">
        <span class="w-1.5 h-6 bg-indigo-500 rounded-full mr-2 shadow-[0_0_8px_rgba(99,102,241,0.5)]"></span>
        {{ $t('profile.promotion_details') }}
      </h2>
      
      <div class="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-5 gap-3 md:gap-4">
        <a-card hoverable class="rounded-xl border border-slate-400/50 bg-slate-500/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-cyan-500/30 hover:shadow-[0_8px_24px_rgba(56,189,248,0.1)] transition-all group">
          <div class="flex items-center flex-col md:flex-row text-center md:text-left">
            <div class="w-10 h-10 md:w-12 md:h-12 bg-slate-500/50 border border-slate-400 text-cyan-400 rounded-full flex items-center justify-center mb-2 md:mb-0 md:mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(56,189,248,0.4)]">
              <User :size="isMobile ? 20 : 24" />
            </div>
            <div>
              <p class="text-slate-400 text-xs md:text-sm mb-1">{{ $t('profile.invitations') }}</p>
              <h3 class="text-lg md:text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.invitation_count || 0 }} {{ $t('profile.people_unit') }}</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-400/50 bg-slate-500/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-indigo-500/30 hover:shadow-[0_8px_24px_rgba(99,102,241,0.1)] transition-all group">
          <div class="flex items-center flex-col md:flex-row text-center md:text-left">
            <div class="w-10 h-10 md:w-12 md:h-12 bg-slate-500/50 border border-slate-400 text-indigo-400 rounded-full flex items-center justify-center mb-2 md:mb-0 md:mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(99,102,241,0.4)]">
              <Activity :size="isMobile ? 20 : 24" />
            </div>
            <div>
              <p class="text-slate-400 text-xs md:text-sm mb-1">{{ $t('profile.invited_recharge_ton') }}</p>
              <h3 class="text-lg md:text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.invitation_recharge?.total_ton || 0 }} TON</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-400/50 bg-slate-500/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-emerald-500/30 hover:shadow-[0_8px_24px_rgba(16,185,129,0.1)] transition-all group">
          <div class="flex items-center flex-col md:flex-row text-center md:text-left">
            <div class="w-10 h-10 md:w-12 md:h-12 bg-slate-500/50 border border-slate-400 text-emerald-400 rounded-full flex items-center justify-center mb-2 md:mb-0 md:mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(16,185,129,0.4)]">
              <Wallet :size="isMobile ? 20 : 24" />
            </div>
            <div>
              <p class="text-slate-400 text-xs md:text-sm mb-1">{{ $t('profile.invited_recharge_cny') }}</p>
              <h3 class="text-lg md:text-xl font-bold text-slate-100 drop-shadow-sm">¥ {{ authStore.user?.invitation_recharge?.total_rmb || 0 }}</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-400/50 bg-slate-500/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-amber-500/30 hover:shadow-[0_8px_24px_rgba(245,158,11,0.1)] transition-all group">
          <div class="flex items-center flex-col md:flex-row text-center md:text-left">
            <div class="w-10 h-10 md:w-12 md:h-12 bg-slate-500/50 border border-slate-400 text-amber-400 rounded-full flex items-center justify-center mb-2 md:mb-0 md:mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(245,158,11,0.4)]">
              <Zap :size="isMobile ? 20 : 24" />
            </div>
            <div>
              <p class="text-slate-400 text-xs md:text-sm mb-1">{{ $t('profile.invited_recharge_stars') }}</p>
              <h3 class="text-lg md:text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.invitation_recharge?.total_stars || 0 }} ⭐</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="col-span-2 sm:col-span-2 lg:col-span-1 rounded-xl border border-slate-400/50 bg-slate-500/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-rose-500/30 hover:shadow-[0_8px_24px_rgba(244,63,94,0.1)] transition-all group relative overflow-hidden">
          <div class="absolute top-0 right-0 -mr-2 -mt-2 w-16 h-16 bg-gradient-to-br from-rose-400 to-orange-500 rounded-full opacity-20 blur-xl"></div>
          <div class="flex items-center flex-col md:flex-row text-center md:text-left relative z-10">
            <div class="w-10 h-10 md:w-12 md:h-12 bg-rose-500/20 border border-rose-500/50 text-rose-400 rounded-full flex items-center justify-center mb-2 md:mb-0 md:mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_15px_rgba(244,63,94,0.5)]">
              <span class="font-bold text-xl">$</span>
            </div>
            <div>
              <p class="text-rose-300 font-medium text-xs md:text-sm mb-1 drop-shadow-sm">{{ $t('profile.estimated_revenue') }}</p>
              <h3 class="text-lg md:text-xl font-bold text-rose-100 drop-shadow-md">$ {{ authStore.user?.invitation_recharge?.commission_usdt || '0.00' }} USDT</h3>
            </div>
          </div>
        </a-card>
      </div>
    </div>
    

    
    <!-- 绑定/修改密码弹窗 (桌面端) -->
    <a-modal
      v-if="!isMobile"
      v-model:open="showBindModal"
      :title="authStore.user?.username ? $t('profile.change_password') : $t('profile.set_password')"
      :confirmLoading="bindingLoading"
      @ok="handleBindPassword"
      okText="确认"
      cancelText="取消"
      :okButtonProps="{ class: 'bg-indigo-600 hover:bg-indigo-500 border-none shadow-lg shadow-indigo-600/30' }"
      class="dark-modal"
    >
      <div class="py-4 space-y-4">
        <p class="text-slate-400 text-sm mb-4">
          设置道号与密咒后，你可以在 Web 端直接破界登录，无需依赖 Telegram 客户端。
        </p>
        
        <div>
          <label class="block text-slate-300 mb-1 text-sm">道号 (账号)</label>
          <a-input 
            v-model:value="bindFormState.username" 
            placeholder="请输入 3-20 位的道号" 
            class="bg-slate-500/50 border-slate-400 text-white placeholder-slate-500 focus:border-indigo-500"
          />
          <p class="text-slate-500 text-xs mt-1">如果你是首次结契，你可以自定义你喜欢的道号。一旦设置后，以后修改密咒时道号不可更改（需保持一致）。</p>
        </div>
        
        <div>
          <label class="block text-slate-300 mb-1 text-sm">密咒 (密码)</label>
          <a-input-password 
            v-model:value="bindFormState.password" 
            placeholder="请输入至少 6 位的密咒" 
            class="bg-slate-500/50 border-slate-400 text-white placeholder-slate-500 focus:border-indigo-500"
          />
        </div>
      </div>
    </a-modal>

    <!-- 绑定/修改密码底部抽屉 (移动端) -->
    <a-drawer
      v-else
      v-model:open="showBindModal"
      placement="bottom"
      :height="'auto'"
      :title="authStore.user?.username ? '修改密咒' : '设置道号与密咒'"
      class="dark-drawer"
      :bodyStyle="{ background: '#1e293b' }"
      :headerStyle="{ background: '#1e293b', borderBottom: '1px solid #334155', color: '#f1f5f9' }"
    >
      <div class="py-4 space-y-4 px-2 pb-10">
        <p class="text-slate-400 text-sm mb-4">
          设置道号与密咒后，你可以在 Web 端直接破界登录，无需依赖 Telegram 客户端。
        </p>
        
        <div>
          <label class="block text-slate-300 mb-1 text-sm">道号 (账号)</label>
          <a-input 
            v-model:value="bindFormState.username" 
            placeholder="请输入 3-20 位的道号" 
            class="bg-slate-500/50 border-slate-400 text-white placeholder-slate-500 focus:border-indigo-500 h-10"
          />
          <p class="text-slate-500 text-xs mt-1">如果你是首次结契，你可以自定义你喜欢的道号。一旦设置后，以后修改密咒时道号不可更改（需保持一致）。</p>
        </div>
        
        <div>
          <label class="block text-slate-300 mb-1 text-sm">密咒 (密码)</label>
          <a-input-password 
            v-model:value="bindFormState.password" 
            placeholder="请输入至少 6 位的密咒" 
            class="bg-slate-500/50 border-slate-400 text-white placeholder-slate-500 focus:border-indigo-500 h-10"
          />
        </div>

        <a-button 
          v-if="!isTMA"
          type="primary" 
          @click="handleBindPassword" 
          :loading="bindingLoading"
          class="w-full mt-4 h-12 bg-indigo-600 hover:bg-indigo-500 border-none shadow-lg shadow-indigo-600/30 text-lg font-bold"
        >
          确认结契
        </a-button>
      </div>
    </a-drawer>
  </div>
</template>

<style scoped>
.welcome-banner {
  background-size: cover;
  background-position: center;
}
:deep(.ant-card) {
  background: transparent;
}
:deep(.ant-card-body) {
  padding: 16px;
}
:deep(.dark-modal .ant-modal-content) {
  background-color: #1e293b;
  border: 1px solid #334155;
}
:deep(.dark-modal .ant-modal-header) {
  background-color: #1e293b;
  border-bottom: 1px solid #334155;
}
:deep(.dark-modal .ant-modal-title) {
  color: #f1f5f9;
}
:deep(.dark-modal .ant-modal-close) {
  color: #94a3b8;
}
:deep(.dark-modal .ant-modal-footer) {
  border-top: 1px solid #334155;
}
:deep(.dark-drawer .ant-drawer-content) {
  background-color: #1e293b;
}
:deep(.dark-drawer .ant-drawer-header) {
  background-color: #1e293b;
  border-bottom: 1px solid #334155;
}
:deep(.dark-drawer .ant-drawer-title) {
  color: #f1f5f9;
}
:deep(.dark-drawer .ant-drawer-close) {
  color: #94a3b8;
}
</style>
