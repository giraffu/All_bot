<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { 
  Wallet,
  Activity,
  CalendarCheck,
  Zap,
  Award,
  User,
  Clock
} from 'lucide-vue-next'
import dayjs from 'dayjs'

const authStore = useAuthStore()
const loading = ref(true)

const formatDate = (dateString?: string | null) => {
  if (!dateString) return '永久有效'
  return dayjs(dateString).format('YYYY-MM-DD HH:mm')
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
          <a-button type="primary" class="mt-3 bg-gradient-to-r from-indigo-500 to-cyan-600 hover:from-indigo-400 hover:to-cyan-500 border-none text-white font-bold w-full shadow-lg hover:shadow-cyan-500/20 transition-all transform hover:-translate-y-0.5">
            获取更多灵石
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
              <p class="text-slate-400 text-sm mb-1">模板贡献次数</p>
              <h3 class="text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.total_contributions || 0 }} 个</h3>
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
      
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
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
              <p class="text-slate-400 text-sm mb-1">受邀者充值笔数</p>
              <h3 class="text-xl font-bold text-slate-100 drop-shadow-sm">{{ authStore.user?.invitation_recharge?.total_recharge_count || 0 }} 笔</h3>
            </div>
          </div>
        </a-card>

        <a-card hoverable class="rounded-xl border border-slate-700/50 bg-slate-800/40 backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.2)] hover:border-emerald-500/30 hover:shadow-[0_8px_24px_rgba(16,185,129,0.1)] transition-all group">
          <div class="flex items-center">
            <div class="w-12 h-12 bg-slate-700/50 border border-slate-600 text-emerald-400 rounded-full flex items-center justify-center mr-4 group-hover:scale-110 transition-transform group-hover:shadow-[0_0_12px_rgba(16,185,129,0.4)]">
              <Wallet :size="24" />
            </div>
            <div>
              <p class="text-slate-400 text-sm mb-1">受邀者充值(法贝)</p>
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
      </div>
    </div>
    
    <div class="mt-8 bg-slate-900/40 backdrop-blur-sm rounded-xl p-6 border border-slate-700/50 shadow-[0_4px_12px_rgba(0,0,0,0.2)]">
      <h3 class="text-lg font-bold text-slate-200 mb-2 flex items-center drop-shadow-sm">
        <Activity :size="20" class="mr-2 text-cyan-400 drop-shadow-[0_0_5px_rgba(56,189,248,0.5)]" /> 快捷指引
      </h3>
      <p class="text-slate-400 mb-4">通过侧边栏的【自定义功能】探索更多 AI 图像与视频生成玩法。</p>
      <div class="flex flex-wrap gap-3">
        <a-button type="primary" @click="$router.push('/custom-features')" class="bg-gradient-to-r from-indigo-600 to-cyan-700 border-none hover:from-indigo-500 hover:to-cyan-600 shadow-md">
          前往 自定义功能
        </a-button>
      </div>
    </div>
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
  padding: 20px;
}
</style>
