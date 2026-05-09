<script setup lang="ts">
import { ref, shallowRef, onMounted, onUnmounted, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import api from '@/api'
import { message } from 'ant-design-vue'
import { 
  Wallet,
  Zap,
  CheckCircle,
  CreditCard,
  RefreshCw,
  Loader
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { TonConnectUI } from '@tonconnect/ui'
import { beginCell } from '@ton/core'

const authStore = useAuthStore()
const { t } = useI18n()
const route = useRoute()

// ================= State =================
const loadingPlans = ref(true)
const plans = ref<any[]>([])
const selectedPlan = ref<any>(null)
const payMethod = ref<'rmb' | 'ton'>('rmb')
const isPaying = ref(false)

// RMB Polling State
const rmbPollingTimer = ref<any>(null)
const pollCount = ref(0)
const maxPollCount = 100 // 5 mins with 3s interval
const showPaymentModal = ref(false)
const orderStatus = ref<'PENDING' | 'SUCCESS' | 'FAILED' | 'TIMEOUT'>('PENDING')

// TON State
const tonConnectUI = shallowRef<TonConnectUI | null>(null)
const tonWalletAddress = ref<string | null>(null)
const tonPollingTimer = ref<any>(null)
const systemTonReceiver = ref<string>("UQC2q_W2d061mO_g3zB-hK12v0p2u44-nI5z9F82L1j88g7b")

// ================= Initialization =================
onMounted(async () => {
  fetchPlans()
  
  // 初始化 TON Connect UI (不挂载原生按钮，使用自定义按钮唤起)
  try {
    tonConnectUI.value = new TonConnectUI({
      manifestUrl: 'https://web.aivison.it.com/tonconnect-manifest.json'
    })
    
    tonConnectUI.value.onStatusChange(wallet => {
      if (wallet) {
        tonWalletAddress.value = wallet.account.address
      } else {
        tonWalletAddress.value = null
      }
    })
  } catch (error) {
    console.error("TON Connect UI Init Error:", error)
  }

  // 检查是否从支付网关跳回
  if (route.query.order_id) {
    showPaymentModal.value = true
    orderStatus.value = 'PENDING'
    startRmbPolling(route.query.order_id as string)
  }
})

onUnmounted(() => {
  stopRmbPolling()
  stopTonPolling()
})

// ================= API Calls =================
const fetchPlans = async () => {
  loadingPlans.value = true
  try {
    const res = await api.get('/payment/plans')
    if (res.data?.data) {
      plans.value = res.data.data.plans || res.data.data
      if (res.data.data.ton_receiver_address) {
        systemTonReceiver.value = res.data.data.ton_receiver_address
      }
    }
  } catch (error) {
    console.error('Failed to fetch plans', error)
    message.error('无法加载充值套餐')
  } finally {
    loadingPlans.value = false
  }
}

// ================= RMB Payment =================
const handleRmbPay = async () => {
  if (!selectedPlan.value) return
  
  isPaying.value = true
  // 提前打开空白页，防止浏览器拦截弹窗
  const newWin = window.open('about:blank', '_blank')
  
  try {
    const res = await api.post('/payment/orders', {
      plan_id: selectedPlan.value.id,
      pay_type: 'alipay'
    })
    
    if (res.data?.data?.pay_url) {
      const { order_id, pay_url } = res.data.data
      
      // 赋值真实的支付链接
      if (newWin) {
        newWin.location.href = pay_url
      } else {
        // 如果 window.open 还是被拦截，降级为当前页跳转
        window.location.href = pay_url
        return
      }
      
      showPaymentModal.value = true
      orderStatus.value = 'PENDING'
      startRmbPolling(order_id)
    }
  } catch (error) {
    console.error('Create order error', error)
    message.error('创建订单失败，请稍后重试')
    if (newWin) newWin.close()
  } finally {
    isPaying.value = false
  }
}

const startRmbPolling = (orderId: string) => {
  stopRmbPolling()
  pollCount.value = 0
  
  const poll = async () => {
    if (pollCount.value >= maxPollCount) {
      orderStatus.value = 'TIMEOUT'
      return
    }
    
    pollCount.value++
    try {
      const res = await api.get(`/payment/orders/${orderId}/status`)
      const status = res.data?.data?.status
      if (status === 'SUCCESS') {
        orderStatus.value = 'SUCCESS'
        handlePaymentSuccess()
        return // 结束轮询
      } else if (status === 'FAILED') {
        orderStatus.value = 'FAILED'
        return // 结束轮询
      }
    } catch (error) {
      console.error('Polling error', error)
    }
    
    // 继续下一次轮询
    rmbPollingTimer.value = setTimeout(poll, 3000)
  }
  
  // 启动第一次
  rmbPollingTimer.value = setTimeout(poll, 3000)
}

const stopRmbPolling = () => {
  if (rmbPollingTimer.value) {
    clearTimeout(rmbPollingTimer.value)
    rmbPollingTimer.value = null
  }
}

// ================= TON Payment =================
const handleTonPay = async () => {
  if (!selectedPlan.value || !tonConnectUI.value) return
  
  if (!tonConnectUI.value.connected) {
    message.warning('请先连接 TON 钱包')
    tonConnectUI.value.openModal()
    return
  }

  const tgId = authStore.user?.telegram_id
  if (!tgId) {
    message.error('未绑定 Telegram 账号，无法使用 TON 支付')
    return
  }

  isPaying.value = true
  try {
    // 构建 Payload: ORDER:{tg_id}:{plan_id}:{timestamp}
    const timestamp = Date.now()
    const payloadStr = `ORDER:${tgId}:${selectedPlan.value.id}:${timestamp}`
    
    // Convert string to hex for text payload
    const textCellHex = stringToCellHex(payloadStr)
    
    const amountNanotons = Math.floor(selectedPlan.value.price_ton * 1000000000).toString()
    
    const transaction = {
      validUntil: Math.floor(Date.now() / 1000) + 600, // 10 minutes
      messages: [
        {
          address: systemTonReceiver.value, // 动态获取的系统收款钱包
          amount: amountNanotons,
          payload: textCellHex
        }
      ]
    }
    
    const result = await tonConnectUI.value.sendTransaction(transaction)
    
    if (result) {
      showPaymentModal.value = true
      orderStatus.value = 'PENDING'
      startTonPolling()
    }
  } catch (error) {
    console.error("TON transaction error:", error)
    message.error('支付已取消或发生错误')
  } finally {
    isPaying.value = false
  }
}

// Helper for TON Payload
const stringToCellHex = (text: string) => {
  return beginCell()
    .storeUint(0, 32) // Text comment OP code
    .storeStringTail(text)
    .endCell()
    .toBoc()
    .toString('base64')
}

const startTonPolling = () => {
  stopTonPolling()
  const oldCredits = authStore.user?.credits || 0
  const oldExpireAt = authStore.user?.identity_expire_at
  let tonPollCount = 0
  
  const poll = async () => {
    if (tonPollCount >= maxPollCount) {
      orderStatus.value = 'TIMEOUT'
      return
    }
    tonPollCount++
    
    try {
      await authStore.fetchUser()
      const newCredits = authStore.user?.credits || 0
      const newExpireAt = authStore.user?.identity_expire_at
      
      // 判定逻辑：灵石增加，或者过期时间增加
      if (newCredits > oldCredits || (newExpireAt && newExpireAt !== oldExpireAt)) {
        orderStatus.value = 'SUCCESS'
        handlePaymentSuccess()
        return // 结束轮询
      }
    } catch (error) {
      console.error('TON Polling error', error)
    }
    
    // 继续下一次轮询
    tonPollingTimer.value = setTimeout(poll, 5000)
  }
  
  // 启动第一次
  tonPollingTimer.value = setTimeout(poll, 5000)
}

const stopTonPolling = () => {
  if (tonPollingTimer.value) {
    clearTimeout(tonPollingTimer.value)
    tonPollingTimer.value = null
  }
}

// ================= Success Handling =================
const handlePaymentSuccess = async () => {
  message.success('支付成功，灵石/身份已到账！')
  await authStore.fetchUser()
  // Trigger fireworks or confetti if you have a library
}

</script>

<template>
  <div class="billing-container space-y-6">
    <!-- Header -->
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center bg-slate-500/30 backdrop-blur-md rounded-xl p-5 border border-slate-400/50 shadow-lg">
      <div>
        <h1 class="text-2xl font-bold text-slate-100 flex items-center drop-shadow-sm">
          <Wallet class="mr-2 text-amber-400" :size="28" />
          {{ t('billing.title', '充值中心') }}
        </h1>
        <p class="text-slate-400 text-sm mt-1">获取更多灵石，突破更高境界</p>
      </div>
      <div class="mt-4 md:mt-0 flex items-center bg-slate-800/50 px-4 py-2 rounded-lg border border-slate-600/50">
        <div class="mr-4">
          <span class="text-xs text-slate-400 block">{{ t('profile.credits', '当前灵石') }}</span>
          <span class="text-xl font-bold text-cyan-300">{{ authStore.user?.credits || 0 }}</span>
        </div>
        <div class="pl-4 border-l border-slate-600/50">
          <span class="text-xs text-slate-400 block">{{ t('profile.identity', '当前身份') }}</span>
          <span class="text-lg font-bold text-indigo-300">{{ authStore.user?.current_identity || '外门弟子' }}</span>
        </div>
      </div>
    </div>

    <!-- Plans Grid -->
    <div v-if="loadingPlans" class="flex justify-center py-20">
      <Loader class="animate-spin text-cyan-500 w-10 h-10" />
    </div>
    
    <div v-else class="grid grid-cols-1 md:grid-cols-3 gap-5">
      <div 
        v-for="plan in plans" 
        :key="plan.id"
        @click="selectedPlan = plan"
        class="relative overflow-hidden cursor-pointer rounded-xl border-2 transition-all duration-300 bg-slate-800/60 backdrop-blur-sm"
        :class="selectedPlan?.id === plan.id ? 'border-amber-400 shadow-[0_0_20px_rgba(251,191,36,0.3)] transform -translate-y-1' : 'border-slate-600/50 hover:border-slate-400 hover:shadow-lg'"
      >
        <!-- Highlight badge for current identity -->
        <div v-if="authStore.user?.current_identity === plan.identity_override" 
             class="absolute top-0 right-0 bg-emerald-500 text-white text-xs font-bold px-3 py-1 rounded-bl-lg z-10">
          当前身份
        </div>
        
        <div class="p-6">
          <h3 class="text-xl font-bold text-slate-100 mb-2">{{ plan.name }}</h3>
          <p class="text-slate-400 text-sm h-10 line-clamp-2">{{ plan.description }}</p>
          
          <div class="mt-4 pt-4 border-t border-slate-700">
            <div class="flex justify-between items-baseline mb-1">
              <span class="text-slate-400 text-sm">灵石额度</span>
              <span class="text-lg font-bold text-cyan-400">{{ plan.credits_granted }}</span>
            </div>
            <div class="flex justify-between items-baseline mb-1">
              <span class="text-slate-400 text-sm">身份有效期</span>
              <span class="text-md font-medium text-indigo-300">{{ plan.duration_days > 0 ? `${plan.duration_days} 天` : '无' }}</span>
            </div>
          </div>
          
          <div class="mt-6 flex items-end gap-2">
            <span class="text-3xl font-extrabold text-amber-400">¥{{ plan.price_rmb }}</span>
            <span class="text-sm text-slate-500 mb-1 line-through" v-if="plan.price_ton">/ {{ plan.price_ton }} TON</span>
          </div>
        </div>
        
        <!-- Check overlay -->
        <div v-if="selectedPlan?.id === plan.id" class="absolute top-3 right-3 text-amber-400">
          <CheckCircle :size="24" class="fill-amber-400/20" />
        </div>
      </div>
    </div>

    <!-- Payment Area (Slide Fade) -->
    <Transition name="slide-fade">
      <div v-if="selectedPlan" class="bg-slate-500/20 backdrop-blur-md rounded-xl p-6 border border-slate-400/50 shadow-xl mt-8">
        <h2 class="text-xl font-bold text-slate-200 mb-4">选择支付方式</h2>
        
        <div class="flex gap-4 mb-6">
          <button 
            @click="payMethod = 'rmb'"
            class="flex-1 py-3 px-4 rounded-lg border-2 flex items-center justify-center transition-all"
            :class="payMethod === 'rmb' ? 'border-blue-500 bg-blue-500/20 text-blue-300' : 'border-slate-600 bg-slate-800/50 text-slate-400 hover:bg-slate-700'"
          >
            <CreditCard class="mr-2" :size="20" /> 支付宝 / 微信
          </button>
          
          <button 
            @click="payMethod = 'ton'"
            class="flex-1 py-3 px-4 rounded-lg border-2 flex items-center justify-center transition-all"
            :class="payMethod === 'ton' ? 'border-cyan-500 bg-cyan-500/20 text-cyan-300' : 'border-slate-600 bg-slate-800/50 text-slate-400 hover:bg-slate-700'"
          >
            <Zap class="mr-2" :size="20" /> TON 钱包
          </button>
        </div>
        
        <!-- RMB Action -->
        <div v-if="payMethod === 'rmb'" class="flex flex-col items-center">
          <p class="text-slate-400 mb-4">将前往易支付安全收银台完成支付</p>
          <a-button 
            type="primary" 
            size="large" 
            @click="handleRmbPay" 
            :loading="isPaying"
            class="w-full md:w-64 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 border-none h-12 text-lg font-bold shadow-lg"
          >
            确认支付 ¥{{ selectedPlan.price_rmb }}
          </a-button>
        </div>
        
        <!-- TON Action -->
        <div v-if="payMethod === 'ton'" class="flex flex-col items-center">
          <p class="text-slate-400 mb-4">连接钱包并发送 {{ selectedPlan.price_ton }} TON 即可自动发货</p>
          
          <a-button 
            v-if="!tonWalletAddress"
            type="primary" 
            size="large" 
            @click="tonConnectUI?.openModal()" 
            class="w-full md:w-64 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 border-none h-12 text-lg font-bold shadow-lg mb-4"
          >
            连接 TON 钱包
          </a-button>
          
          <div v-else class="w-full flex flex-col items-center">
            <div class="bg-slate-800/50 border border-slate-600/50 rounded-lg px-4 py-2 mb-4 text-slate-300 text-sm flex items-center">
              已连接: {{ tonWalletAddress.slice(0, 4) }}...{{ tonWalletAddress.slice(-4) }}
              <a-button type="link" size="small" @click="tonConnectUI?.disconnect()" class="ml-2 text-rose-400 hover:text-rose-300 p-0">断开</a-button>
            </div>
            <a-button 
              type="primary" 
              size="large" 
              @click="handleTonPay" 
              :loading="isPaying"
              class="w-full md:w-64 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 border-none h-12 text-lg font-bold shadow-lg"
            >
              确认发送 {{ selectedPlan.price_ton }} TON
            </a-button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Payment Polling Modal -->
    <a-modal
      v-model:open="showPaymentModal"
      title="订单状态"
      :footer="null"
      :closable="orderStatus === 'FAILED' || orderStatus === 'TIMEOUT' || orderStatus === 'SUCCESS'"
      :maskClosable="false"
      class="dark-modal"
    >
      <div class="py-8 flex flex-col items-center justify-center">
        <!-- PENDING -->
        <template v-if="orderStatus === 'PENDING'">
          <RefreshCw class="animate-spin text-cyan-500 w-16 h-16 mb-4" />
          <h3 class="text-xl font-bold text-slate-200">等待支付完成</h3>
          <p class="text-slate-400 mt-2 text-center">
            请在弹出的页面/钱包中完成支付。<br/>
            我们正在等待区块链或网关确认，请勿关闭此窗口...
          </p>
        </template>
        
        <!-- SUCCESS -->
        <template v-else-if="orderStatus === 'SUCCESS'">
          <CheckCircle class="text-emerald-500 w-16 h-16 mb-4" />
          <h3 class="text-xl font-bold text-emerald-400">支付成功！</h3>
          <p class="text-slate-400 mt-2">灵石已入账，感谢道友的赞助。</p>
          <a-button type="primary" class="mt-6 bg-emerald-600 border-none" @click="showPaymentModal = false">
            关闭
          </a-button>
        </template>

        <!-- TIMEOUT -->
        <template v-else-if="orderStatus === 'TIMEOUT'">
          <h3 class="text-xl font-bold text-amber-400">查询超时</h3>
          <p class="text-slate-400 mt-2 text-center">
            订单可能尚未支付，或网络延迟导致未查询到结果。<br/>
            若您已扣款，系统将在几分钟内自动补发，请稍后刷新页面查看。
          </p>
          <a-button class="mt-6" @click="showPaymentModal = false">关闭</a-button>
        </template>
        
        <!-- FAILED -->
        <template v-else>
          <h3 class="text-xl font-bold text-rose-400">支付失败或已取消</h3>
          <p class="text-slate-400 mt-2">如果您遇到问题，请联系客服。</p>
          <a-button class="mt-6" @click="showPaymentModal = false">关闭</a-button>
        </template>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.slide-fade-enter-active {
  transition: all 0.3s ease-out;
}

.slide-fade-leave-active {
  transition: all 0.3s cubic-bezier(1, 0.5, 0.8, 1);
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  transform: translateY(20px);
  opacity: 0;
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
</style>
