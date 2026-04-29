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
  Lock
} from 'lucide-vue-next'
import dayjs from 'dayjs'

const authStore = useAuthStore()
const loading = ref(true)

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
}

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
})
</script>

<template>
  <div class="profile-container space-y-6">
    <div class="welcome-banner bg-gradient-to-r from-slate-800 via-slate-900 to-indigo-950 rounded-xl p-8 text-white shadow-lg relative overflow-hidden border border-slate-700/50">
      <div class="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center">
        <div>
          <h1 class="text-3xl font-bold mb-2 drop-shadow-sm text-slate-100">欢迎回来，{{ authStore.user?.full_name || authStore.user?.username }}!</h1>
          <p class="text-slate-300 text-lg max-w-2xl flex items-center">
            <span class="mr-2 drop-shadow-sm">你的当前修仙境界是</span> 
            <span class="font-bold text-cyan-300 bg-white/10 backdrop-blur-sm border border-white/20 px-2 py-0.5 rounded mr-3 shadow-sm">{{ authStore.user?.user_group || '凡人' }}</span>
            <span class="mr-2 drop-shadow-sm">宗门身份：</span>
            <span class="font-bold text-cyan-300 bg-white/10 backdrop-blur-sm border border-white/20 px-2 py-0.5 rounded shadow-sm">{{ authStore.user?.current_identity || '外门弟子' }}</span>
          </p>
          <div class="mt-2 text-sm text-slate-400 flex items-center drop-shadow-sm">
            <Clock :size="14" class="mr-1" />
            <span v-if="authStore.user?.current_identity === '外门弟子'">身份长期有效</span>
            <span v-else>身份到期时间: {{ formatDate(authStore.user?.identity_expire_at) }}</span>
          </div>
        </div>
        
        <div class="mt-6 md:mt-0 inline-flex flex-col items-end">
          <div class="inline-flex items-center bg-slate-900/40 backdrop-blur-md px-5 py-3 rounded-lg border border-slate-600/50 shadow-[0_4px_12px_rgba(0,0,0,0.3)]">
            <Wallet :size="24" class="mr-3 text-cyan-400 drop-shadow-[0_0_8px_rgba(56,189,248,0.5)]" />
            <div class="flex flex-col">
              <span class="text-xs text-slate-400 font-medium drop-shadow-sm">可用灵石余额</span>
              <span class="text-2xl font-bold leading-none drop-shadow-sm text-slate-100">{{ authStore.user?.credits || 0 }}</span>
            </div>
          </div>
          <a-button type="primary" @click="handleCheckin" :loading="checkinLoading" class="mt-3 bg-gradient-to-r from-indigo-500 to-cyan-600 hover:from-indigo-400 hover:to-cyan-500 border-none text-white font-bold w-full shadow-lg hover:shadow-cyan-500/20 transition-all transform hover:-translate-y-0.5">
            签到
          </a-button>
        </div>
      </div>
      
      <!-- Decorative circles -->
      <div class="absolute -top-24 -right-24 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none"></div>
      <div class="absolute -bottom-24 right-12 w-48 h-48 bg-cyan-500/10 rounded-full blur-2xl pointer-events-none"></div>
    </div>
    
    <div>
      <h2 class="text-xl font-bold text-slate-200 mb-4 flex items-center drop-shadow-sm">
        <span class="w-1.5 h-6 bg-cyan-500 rounded-full mr-2 shadow-[0_0_8px_rgba(56,189,248,0.5)]"></span>
        修仙数据总览
      </h2>
      
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <a-card hoverable class="rounded-xl border border-slate-700/50 bg-slate-800/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-cyan-500/30 hover:shadow-[0_8px_24px_rgba(56,189,248,0.1)] transition-all group">
          <div class="flex items-center">
            <div class="w-12 h-12 bg-slate-700/50 border border-slate-600 text-cyan-400 rounded-full flex items-center justify-center mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(56,189,248,0.4)]">
              <User :size="24" />
            </div>
            <div>
              <p class="text-slate-400 text-sm mb-1">系统ID (TG ID)</p>
              <h3 class="text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.telegram_id || authStore.user?.id || '---' }}</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-700/50 bg-slate-800/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-indigo-500/30 hover:shadow-[0_8px_24px_rgba(99,102,241,0.1)] transition-all group">
          <div class="flex items-center">
            <div class="w-12 h-12 bg-slate-700/50 border border-slate-600 text-indigo-400 rounded-full flex items-center justify-center mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(99,102,241,0.4)]">
              <Zap :size="24" />
            </div>
            <div>
              <p class="text-slate-400 text-sm mb-1">累计施法次数</p>
              <h3 class="text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.generation_count || 0 }} 次</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-700/50 bg-slate-800/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-emerald-500/30 hover:shadow-[0_8px_24px_rgba(16,185,129,0.1)] transition-all group">
          <div class="flex items-center">
            <div class="w-12 h-12 bg-slate-700/50 border border-slate-600 text-emerald-400 rounded-full flex items-center justify-center mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(16,185,129,0.4)]">
              <CalendarCheck :size="24" />
            </div>
            <div>
              <p class="text-slate-400 text-sm mb-1">累计签到天数</p>
              <h3 class="text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.checkin_count || 0 }} 天</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-700/50 bg-slate-800/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-amber-500/30 hover:shadow-[0_8px_24px_rgba(245,158,11,0.1)] transition-all group">
          <div class="flex items-center">
            <div class="w-12 h-12 bg-slate-700/50 border border-slate-600 text-amber-400 rounded-full flex items-center justify-center mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(245,158,11,0.4)]">
              <Award :size="24" />
            </div>
            <div>
              <p class="text-slate-400 text-sm mb-1">当前生成优先级</p>
              <h3 class="text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.priority || 0 }}</h3>
            </div>
          </div>
        </a-card>
      </div>
    </div>
    
    <div class="mt-8">
      <h2 class="text-xl font-bold text-slate-200 mb-4 flex items-center drop-shadow-sm">
        <span class="w-1.5 h-6 bg-indigo-500 rounded-full mr-2 shadow-[0_0_8px_rgba(99,102,241,0.5)]"></span>
        邀请与推广明细
      </h2>
      
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <a-card hoverable class="rounded-xl border border-slate-700/50 bg-slate-800/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-cyan-500/30 hover:shadow-[0_8px_24px_rgba(56,189,248,0.1)] transition-all group">
          <div class="flex items-center">
            <div class="w-12 h-12 bg-slate-700/50 border border-slate-600 text-cyan-400 rounded-full flex items-center justify-center mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(56,189,248,0.4)]">
              <User :size="24" />
            </div>
            <div>
              <p class="text-slate-400 text-sm mb-1">成功邀请同道</p>
              <h3 class="text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.invitation_count || 0 }} 人</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-700/50 bg-slate-800/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-indigo-500/30 hover:shadow-[0_8px_24px_rgba(99,102,241,0.1)] transition-all group">
          <div class="flex items-center">
            <div class="w-12 h-12 bg-slate-700/50 border border-slate-600 text-indigo-400 rounded-full flex items-center justify-center mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(99,102,241,0.4)]">
              <Activity :size="24" />
            </div>
            <div>
              <p class="text-slate-400 text-sm mb-1">受邀者充值(TON)</p>
              <h3 class="text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.invitation_recharge?.total_ton || 0 }} TON</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-700/50 bg-slate-800/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-emerald-500/30 hover:shadow-[0_8px_24px_rgba(16,185,129,0.1)] transition-all group">
          <div class="flex items-center">
            <div class="w-12 h-12 bg-slate-700/50 border border-slate-600 text-emerald-400 rounded-full flex items-center justify-center mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(16,185,129,0.4)]">
              <Wallet :size="24" />
            </div>
            <div>
              <p class="text-slate-400 text-sm mb-1">受邀者充值(人民币)</p>
              <h3 class="text-xl font-bold text-slate-100 drop-shadow-sm">¥ {{ authStore.user?.invitation_recharge?.total_rmb || 0 }}</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-700/50 bg-slate-800/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-amber-500/30 hover:shadow-[0_8px_24px_rgba(245,158,11,0.1)] transition-all group">
          <div class="flex items-center">
            <div class="w-12 h-12 bg-slate-700/50 border border-slate-600 text-amber-400 rounded-full flex items-center justify-center mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(245,158,11,0.4)]">
              <Zap :size="24" />
            </div>
            <div>
              <p class="text-slate-400 text-sm mb-1">受邀者充值(Stars)</p>
              <h3 class="text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.invitation_recharge?.total_stars || 0 }} ⭐</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-700/50 bg-slate-800/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-rose-500/30 hover:shadow-[0_8px_24px_rgba(244,63,94,0.1)] transition-all group relative overflow-hidden">
          <div class="absolute top-0 right-0 -mr-2 -mt-2 w-16 h-16 bg-gradient-to-br from-rose-400 to-orange-500 rounded-full opacity-20 blur-xl"></div>
          <div class="flex items-center relative z-10">
            <div class="w-12 h-12 bg-rose-500/20 border border-rose-500/50 text-rose-400 rounded-full flex items-center justify-center mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_15px_rgba(244,63,94,0.5)]">
              <span class="font-bold text-xl">$</span>
            </div>
            <div>
              <p class="text-rose-300 font-medium text-sm mb-1 drop-shadow-sm">预估邀请分成</p>
              <h3 class="text-xl font-bold text-rose-100 drop-shadow-md">$ {{ authStore.user?.invitation_recharge?.commission_usdt || '0.00' }} USDT</h3>
            </div>
          </div>
        </a-card>
      </div>
    </div>
    
    <div class="mt-8 bg-slate-900/40 backdrop-blur-sm rounded-xl p-6 border border-slate-700/50 shadow-[0_4px_12px_rgba(0,0,0,0.2)]">
      <h3 class="text-lg font-bold text-slate-200 mb-2 flex items-center drop-shadow-sm">
        <Activity :size="20" class="mr-2 text-cyan-400 drop-shadow-[0_0_5px_rgba(56,189,248,0.5)]" /> 快捷指引
      </h3>
      <p class="text-slate-400 mb-4">通过侧边栏的【练功房】探索更多 AI 图像与视频生成玩法。</p>
      <div class="flex flex-wrap gap-3">
        <a-button type="primary" @click="$router.push('/custom-features')" class="bg-gradient-to-r from-indigo-600 to-cyan-700 border-none hover:from-indigo-500 hover:to-cyan-600 shadow-md">
          前往 练功房
        </a-button>
        <a-button type="default" @click="handleBindPasswordModalOpen" class="bg-slate-800 text-indigo-300 border-indigo-500/30 hover:text-indigo-200 hover:border-indigo-400 shadow-md">
          <Lock :size="16" class="mr-1 inline" /> {{ authStore.user?.username ? '修改密咒' : '设置道号与密咒' }}
        </a-button>
      </div>
    </div>
    
    <!-- 绑定/修改密码弹窗 -->
    <a-modal
      v-model:open="showBindModal"
      :title="authStore.user?.username ? '修改密咒' : '设置道号与密咒'"
      :confirmLoading="bindingLoading"
      @ok="handleBindPassword"
      okText="确认结契"
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
            class="bg-slate-800/50 border-slate-700 text-white placeholder-slate-500 focus:border-indigo-500"
          />
          <p class="text-slate-500 text-xs mt-1">如果你是首次结契，你可以自定义你喜欢的道号。一旦设置后，以后修改密咒时道号不可更改（需保持一致）。</p>
        </div>
        
        <div>
          <label class="block text-slate-300 mb-1 text-sm">密咒 (密码)</label>
          <a-input-password 
            v-model:value="bindFormState.password" 
            placeholder="请输入至少 6 位的密咒" 
            class="bg-slate-800/50 border-slate-700 text-white placeholder-slate-500 focus:border-indigo-500"
          />
        </div>
      </div>
    </a-modal>
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
</style>
