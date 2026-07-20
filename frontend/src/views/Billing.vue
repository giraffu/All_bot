<script setup lang="ts">
import { computed } from 'vue'
import { 
  Wallet,
  Zap,
  CheckCircle,
  CreditCard,
  RefreshCw,
  Loader
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useBillingPayments } from '@/composables/useBillingPayments'
import { useProfileWelcomeSummary } from '@/composables/useProfileWelcomeSummary'
import { useAuthStore } from '@/stores/auth'
import ProfileBackButton from '@/components/profile/ProfileBackButton.vue'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const currentUser = computed(() => authStore.user)
const { identityExpireText } = useProfileWelcomeSummary({
  user: currentUser,
  t,
})
const {
  loadingPlans,
  plans,
  selectedPlan,
  payMethod,
  isPaying,
  showPaymentModal,
  orderStatus,
  tonWalletAddress,
  tonPaymentEnabled,
  handleRmbPay,
  handleTonPay,
  openTonConnectModal,
  disconnectTonWallet
} = useBillingPayments()

type BillingPlan = {
  id: number
  name: string
  description: string
  price_rmb: number
  price_ton: number
  duration_days: number
  identity_override: string
  credits_granted: number
  type: 'monthly' | 'one_time'
}

type BillingPlanDisplay = BillingPlan & {
  displayName: string
  displayDescription: string
  benefits: string[]
  durationLabel: string
}

const planDisplayMeta: Record<number, Pick<BillingPlanDisplay, 'displayName' | 'displayDescription' | 'benefits' | 'durationLabel'>> = {
  1: {
    displayName: '基础月卡',
    displayDescription: '获得内门弟子身份，适合日常稳定修炼。',
    benefits: ['获得内门弟子身份', '签到加成', '每日前100次享受加速加成'],
    durationLabel: '30 天',
  },
  2: {
    displayName: '高级月卡',
    displayDescription: '获得核心弟子身份，适合高频创作。',
    benefits: ['获得核心弟子身份', '签到加成', '每日前100次享受加速加成'],
    durationLabel: '30 天',
  },
  3: {
    displayName: '至尊月卡',
    displayDescription: '获得真传弟子身份，适合重度玩家长期使用。',
    benefits: ['获得真传弟子身份', '签到加成', '每日前100次享受加速加成'],
    durationLabel: '30 天',
  },
  5: {
    displayName: '一把灵石',
    displayDescription: '快速补充灵石，适合临时加量。',
    benefits: ['灵石即时到账', '不改变当前身份'],
    durationLabel: '即时到账',
  },
  6: {
    displayName: '一袋灵石',
    displayDescription: '中档补充灵石，适合连续修炼。',
    benefits: ['灵石即时到账', '不改变当前身份'],
    durationLabel: '即时到账',
  },
  7: {
    displayName: '一箱灵石',
    displayDescription: '大额补充灵石，适合冲刺使用。',
    benefits: ['灵石即时到账', '不改变当前身份'],
    durationLabel: '即时到账',
  },
}

const planDisplayOrder = [1, 2, 3, 5, 6, 7]

const displayPlans = computed<BillingPlanDisplay[]>(() => {
  const planMap = new Map<number, BillingPlan>(
    (plans.value as BillingPlan[]).map((plan) => [plan.id, plan])
  )

  return planDisplayOrder
    .map((id) => {
      const plan = planMap.get(id)
      if (!plan) {
        return null
      }

      const meta = planDisplayMeta[id]
      return {
        ...plan,
        displayName: meta?.displayName ?? plan.name,
        displayDescription: meta?.displayDescription ?? plan.description,
        benefits: meta?.benefits ?? [],
        durationLabel:
          meta?.durationLabel ?? (plan.duration_days > 0 ? `${plan.duration_days} 天` : '无'),
      }
    })
    .filter((plan): plan is BillingPlanDisplay => Boolean(plan))
})

const returnToProfile = () => {
  void router.push({ name: 'Profile' })
}

</script>

<template>
  <div class="billing-container space-y-6">
    <div class="billing-return-row">
      <ProfileBackButton :label="t('profile.back_to_profile')" @click="returnToProfile" />
    </div>

    <div
      v-if="selectedPlan"
      class="billing-mask fixed inset-0 z-30 backdrop-blur-[1px]"
      @click="selectedPlan = null"
    ></div>

    <!-- Header -->
    <div class="billing-hero flex flex-col md:flex-row justify-between items-start md:items-center rounded-xl p-5 backdrop-blur-md">
      <div>
        <h1 class="billing-title text-2xl font-bold flex items-center drop-shadow-sm">
          <Wallet class="mr-2 text-amber-400" :size="28" />
          {{ t('billing.title', '充值中心') }}
        </h1>
        <p class="billing-subtitle text-sm mt-1">获取更多灵石，突破更高境界</p>
      </div>
      <div class="billing-identity-card mt-4 md:mt-0 px-4 py-2 rounded-lg">
        <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <span class="billing-meta-label">{{ t('profile.identity', '当前身份') }}</span>
          <span class="billing-meta-value billing-meta-value--identity font-bold">{{ authStore.user?.current_identity || '外门弟子' }}</span>
          <span class="billing-divider">|</span>
          <span class="billing-meta-label">身份到期</span>
          <span class="billing-meta-value billing-meta-value--expire font-medium">{{ identityExpireText }}</span>
        </div>
      </div>
    </div>

    <!-- Plans Grid -->
    <div v-if="loadingPlans" class="flex justify-center py-20">
      <Loader class="animate-spin text-cyan-500 w-10 h-10" />
    </div>
    
    <div v-else class="grid grid-cols-3 gap-2 md:gap-5">
      <div
        v-for="plan in displayPlans"
        :key="plan.id"
        @click="selectedPlan = plan"
        class="plan-card relative overflow-hidden cursor-pointer rounded-xl border-2 transition-all duration-300 backdrop-blur-sm min-h-[212px] md:min-h-[272px]"
        :class="{ 'is-selected': selectedPlan?.id === plan.id }"
      >
        <div class="p-3 md:p-5 flex h-full flex-col">
          <div class="flex items-start justify-between gap-2">
            <h3 class="plan-title text-sm md:text-lg font-bold leading-5">{{ plan.displayName }}</h3>
            <span
              v-if="plan.duration_days > 0 && authStore.user?.current_identity === plan.identity_override"
              class="shrink-0 rounded-full border border-emerald-400/40 bg-emerald-500/15 px-2 py-1 text-[10px] md:text-xs font-semibold leading-none text-emerald-300"
            >
              当前身份
            </span>
          </div>
          <p class="plan-description mt-1.5 md:mt-2 text-[11px] md:text-sm leading-4 md:leading-6 min-h-[32px] md:min-h-[48px] line-clamp-2 md:line-clamp-none">{{ plan.displayDescription }}</p>
          
          <div class="plan-stats mt-2.5 md:mt-4 pt-2.5 md:pt-4">
            <div class="flex justify-between items-baseline mb-1">
              <span class="plan-key text-[10px] md:text-sm">灵石</span>
              <span class="text-sm md:text-base font-bold text-cyan-400">{{ plan.credits_granted }}</span>
            </div>
            <div class="flex justify-between items-baseline mb-1">
              <span class="plan-key text-[10px] md:text-sm">{{ plan.duration_days > 0 ? '有效期' : '到账' }}</span>
              <span class="text-[11px] md:text-md font-medium text-indigo-300">{{ plan.durationLabel }}</span>
            </div>
          </div>

          <div class="mt-2.5 md:mt-4 space-y-1.5 md:space-y-2">
            <p class="plan-section-label text-[10px] md:text-xs uppercase tracking-[0.1em] md:tracking-[0.2em]">
              {{ plan.duration_days > 0 ? '月卡福利' : '购买说明' }}
            </p>
            <ul class="plan-benefits space-y-1 text-[11px] md:text-xs">
              <li
                v-for="benefit in plan.benefits"
                :key="benefit"
                class="flex items-start gap-1.5 md:gap-2 leading-4 md:leading-5"
              >
                <span class="mt-1 h-1.5 w-1.5 rounded-full bg-cyan-400 shrink-0"></span>
                <span class="line-clamp-2 md:line-clamp-none">{{ benefit }}</span>
              </li>
            </ul>
          </div>
          
          <div class="mt-auto pt-3 md:pt-4 flex items-end gap-1 md:gap-2">
            <span class="text-xl md:text-2xl font-extrabold text-amber-400">¥{{ plan.price_rmb }}</span>
            <span class="plan-price-note hidden md:inline text-xs md:text-sm mb-1 line-through" v-if="plan.price_ton">/ {{ plan.price_ton }} TON</span>
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
      <div
        v-if="selectedPlan"
        class="payment-sheet fixed left-1/2 top-1/2 z-40 w-[520px] max-w-[calc(100vw-1.5rem)] md:max-w-[calc(100vw-6rem)] -translate-x-1/2 -translate-y-1/2 rounded-3xl p-4 md:p-6 backdrop-blur-xl"
      >
        <div class="mb-3 flex items-start justify-between gap-3">
          <div>
            <p class="payment-kicker text-xs uppercase tracking-[0.18em]">已选套餐</p>
            <h3 class="payment-title mt-1 text-base font-semibold">{{ selectedPlan.displayName }}</h3>
            <p class="mt-1 text-sm text-amber-300">¥{{ selectedPlan.price_rmb }}</p>
          </div>
          <button
            type="button"
            class="payment-close rounded-full px-2.5 py-1 text-xs transition"
            @click="selectedPlan = null"
          >
            收起
          </button>
        </div>
        <h2 class="payment-heading text-lg md:text-2xl font-bold mb-3 md:mb-5">选择支付方式</h2>
        
        <div
          class="grid gap-2 md:gap-4 mb-3 md:mb-6"
          :class="tonPaymentEnabled ? 'grid-cols-3' : 'grid-cols-2'"
        >
          <button
            v-if="tonPaymentEnabled"
            @click="payMethod = 'alipay'"
            class="payment-option payment-option--blue rounded-lg border-2 flex items-center justify-center transition-all px-2 py-2 md:px-5 md:py-3.5 text-xs md:text-base"
            :class="{ 'is-selected': payMethod === 'alipay' }"
          >
            <CreditCard class="mr-1 md:mr-2 shrink-0" :size="16" />
            <span class="truncate">支付宝</span>
          </button>

          <button 
            @click="payMethod = 'wxpay'"
            class="payment-option payment-option--green rounded-lg border-2 flex items-center justify-center transition-all px-2 py-2 md:px-5 md:py-3.5 text-xs md:text-base"
            :class="{ 'is-selected': payMethod === 'wxpay' }"
          >
            <CreditCard class="mr-1 md:mr-2 shrink-0" :size="16" />
            <span class="truncate">微信</span>
          </button>
          
          <button 
            @click="payMethod = 'ton'"
            class="payment-option payment-option--cyan rounded-lg border-2 flex items-center justify-center transition-all px-2 py-2 md:px-5 md:py-3.5 text-xs md:text-base"
            :class="{ 'is-selected': payMethod === 'ton' }"
          >
            <Zap class="mr-1 md:mr-2 shrink-0" :size="16" />
            <span class="truncate">TON</span>
          </button>
        </div>
        <p
          v-if="!tonPaymentEnabled"
          class="payment-hint text-sm mb-3 md:mb-4 text-center"
        >
          {{ t('billing.ton_unavailable') }}
        </p>
        
        <!-- RMB Action -->
        <div v-if="payMethod === 'alipay' || payMethod === 'wxpay'" class="flex flex-col items-center">
          <p class="payment-hint text-sm md:text-base mb-3 md:mb-4 text-center">
            将前往易支付安全收银台完成{{ payMethod === 'wxpay' ? '微信支付' : '支付宝支付' }}
          </p>
          <a-button 
            type="primary" 
            size="large" 
            @click="handleRmbPay" 
            :loading="isPaying"
            class="w-full md:h-12 border-none h-11 text-base md:text-lg font-bold shadow-lg"
            :class="payMethod === 'wxpay'
              ? 'bg-gradient-to-r from-emerald-600 to-green-600 hover:from-emerald-500 hover:to-green-500'
              : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500'"
          >
            确认{{ payMethod === 'wxpay' ? '微信' : '支付宝' }}支付 ¥{{ selectedPlan.price_rmb }}
          </a-button>
        </div>
        
        <!-- TON Action -->
        <div v-if="payMethod === 'ton'" class="flex flex-col items-center">
          <p class="payment-hint text-sm md:text-base mb-3 md:mb-4 text-center">连接钱包并发送 {{ selectedPlan.price_ton }} TON 即可自动发货</p>
          
          <a-button 
            v-if="!tonWalletAddress"
            type="primary" 
            size="large" 
            @click="openTonConnectModal" 
            class="w-full bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 border-none h-11 md:h-12 text-base md:text-lg font-bold shadow-lg mb-4"
          >
            连接 TON 钱包
          </a-button>
          
          <div v-else class="w-full flex flex-col items-center">
            <div class="ton-wallet-card rounded-lg px-4 py-2 mb-4 text-sm flex items-center">
              已连接: {{ tonWalletAddress.slice(0, 4) }}...{{ tonWalletAddress.slice(-4) }}
              <a-button type="link" size="small" @click="disconnectTonWallet" class="ml-2 text-rose-400 hover:text-rose-300 p-0">断开</a-button>
            </div>
            <a-button 
              type="primary" 
              size="large" 
              @click="handleTonPay" 
              :loading="isPaying"
              class="w-full bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 border-none h-11 md:h-12 text-base md:text-lg font-bold shadow-lg"
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
.billing-return-row {
  display: flex;
  align-items: center;
  min-height: 2.625rem;
}

.billing-mask {
  background: rgba(15, 23, 42, 0.38);
}

.billing-hero {
  background: var(--theme-panel-bg);
  border: 1px solid var(--theme-border);
  box-shadow: var(--theme-shadow);
}

.billing-title,
.plan-title,
.payment-title,
.payment-heading {
  color: var(--theme-text-primary);
}

.billing-subtitle,
.billing-meta-label,
.plan-key,
.plan-description,
.plan-benefits,
.payment-hint {
  color: var(--theme-text-secondary);
}

.billing-identity-card,
.ton-wallet-card {
  background: var(--theme-panel-strong-bg);
  border: 1px solid var(--theme-border);
}

.billing-meta-value--identity {
  color: #818cf8;
}

.billing-meta-value--expire {
  color: #67e8f9;
}

.billing-divider,
.plan-price-note,
.payment-kicker,
.plan-section-label {
  color: var(--theme-text-muted);
}

.plan-card {
  background: var(--theme-card-bg);
  border-color: var(--theme-border);
}

.plan-card:hover {
  background: var(--theme-card-hover-bg);
  border-color: var(--theme-border-strong);
  box-shadow: var(--theme-shadow);
}

.plan-card.is-selected {
  border-color: #fbbf24;
  box-shadow: 0 0 20px rgba(251, 191, 36, 0.3);
  transform: translateY(-0.25rem);
}

.plan-stats {
  border-top: 1px solid var(--theme-divider);
}

.payment-sheet {
  background: var(--theme-card-strong-bg);
  border: 1px solid var(--theme-border);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.28);
}

.payment-close {
  border: 1px solid var(--theme-border);
  color: var(--theme-text-secondary);
}

.payment-close:hover {
  border-color: var(--theme-border-strong);
  color: var(--theme-text-primary);
}

.payment-option {
  border-color: var(--theme-border);
  background: var(--theme-card-bg);
  color: var(--theme-text-secondary);
}

.payment-option:hover {
  background: var(--theme-card-hover-bg);
}

.payment-option.is-selected.payment-option--blue {
  border-color: #3b82f6;
  background: rgba(59, 130, 246, 0.18);
  color: #93c5fd;
}

.payment-option.is-selected.payment-option--green {
  border-color: #10b981;
  background: rgba(16, 185, 129, 0.18);
  color: #6ee7b7;
}

.payment-option.is-selected.payment-option--cyan {
  border-color: #06b6d4;
  background: rgba(6, 182, 212, 0.18);
  color: #67e8f9;
}

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
  background-color: var(--theme-card-strong-bg);
  border: 1px solid var(--theme-border);
}
:deep(.dark-modal .ant-modal-header) {
  background-color: var(--theme-card-strong-bg);
  border-bottom: 1px solid var(--theme-border);
}
:deep(.dark-modal .ant-modal-title) {
  color: var(--theme-text-primary);
}
:deep(.dark-modal .ant-modal-close) {
  color: var(--theme-text-muted);
}
</style>
