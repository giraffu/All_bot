import { computed, reactive, ref, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import api from '@/api'
import type { User } from '@/stores/auth'

const redeemCreditsPackages = [
  {
    amountUsdt: '1.0000',
    credits: 130,
    description: '1 USDT = 130 灵石'
  },
  {
    amountUsdt: '3.0000',
    credits: 390,
    description: '3 USDT = 390 灵石'
  },
  {
    amountUsdt: '6.0000',
    credits: 780,
    description: '6 USDT = 780 灵石'
  },
  {
    amountUsdt: '10.0000',
    credits: 1800,
    description: '10 USDT = 1800 灵石'
  },
  {
    amountUsdt: '15.0000',
    credits: 2700,
    description: '15 USDT = 2700 灵石'
  },
  {
    amountUsdt: '20.0000',
    credits: 4000,
    description: '20 USDT = 4000 灵石'
  }
] as const

const membershipRedeemOptions = [
  {
    key: 'inner_30d',
    label: '内门弟子 30 天',
    amountUsdt: '4.4118',
    bonusCredits: 400,
    description: '兑换后附加 400 灵石'
  },
  {
    key: 'core_30d',
    label: '核心弟子 30 天',
    amountUsdt: '10.2941',
    bonusCredits: 1200,
    description: '兑换后附加 1200 灵石'
  },
  {
    key: 'true_30d',
    label: '真传弟子 30 天',
    amountUsdt: '17.6471',
    bonusCredits: 3000,
    description: '兑换后附加 3000 灵石'
  }
] as const

interface UseAffiliateRedeemOptions {
  user: Ref<User | null | undefined>
  refreshUser: () => Promise<void>
}

const buildIdempotencyKey = (prefix: string) => {
  const randomPart =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}_${Math.random().toString(16).slice(2)}`
  return `${prefix}_${randomPart}`
}

export function useAffiliateRedeem(options: UseAffiliateRedeemOptions) {
  const redeemCreditsLoading = ref(false)
  const redeemMembershipLoading = ref(false)
  const showRedeemCreditsModal = ref(false)
  const showRedeemMembershipModal = ref(false)
  const redeemCreditsForm = reactive({
    amountUsdt: '1.0000'
  })
  const redeemMembershipForm = reactive({
    optionKey: 'inner_30d'
  })

  const availableCommissionUsdt = computed(() => {
    const raw =
      options.user.value?.invitation_recharge?.available_balance_usdt ??
      options.user.value?.invitation_recharge?.commission_usdt
    const parsed = Number(raw ?? 0)
    return Number.isFinite(parsed) ? parsed.toFixed(4) : '0.0000'
  })

  const totalCommissionUsdt = computed(() => {
    const raw =
      options.user.value?.invitation_recharge?.total_commission_usdt ??
      options.user.value?.invitation_recharge?.commission_usdt
    const parsed = Number(raw ?? 0)
    return Number.isFinite(parsed) ? parsed.toFixed(2) : '0.00'
  })

  const spentCommissionUsdt = computed(() => {
    const raw = options.user.value?.invitation_recharge?.spent_commission_usdt
    const parsed = Number(raw ?? 0)
    return Number.isFinite(parsed) ? parsed.toFixed(2) : '0.00'
  })

  const openRedeemCreditsModal = () => {
    showRedeemCreditsModal.value = true
  }

  const openRedeemMembershipModal = () => {
    showRedeemMembershipModal.value = true
  }

  const handleRedeemCredits = async () => {
    redeemCreditsLoading.value = true
    try {
      const selectedPackage = redeemCreditsPackages.find(
        (item) => item.amountUsdt === redeemCreditsForm.amountUsdt
      )
      await api.post('/users/me/affiliate/redeem-credits', {
        amount_usdt: redeemCreditsForm.amountUsdt,
        idempotency_key: buildIdempotencyKey('credits_redeem')
      })
      await options.refreshUser()
      message.success(
        selectedPackage
          ? `返佣兑换灵石成功：${selectedPackage.amountUsdt} USDT -> ${selectedPackage.credits} 灵石`
          : '返佣兑换灵石成功，灵石与返佣余额已更新'
      )
      showRedeemCreditsModal.value = false
    } catch (error: any) {
      console.error('Redeem credits error:', error)
      const detail = error.response?.data?.detail
      if (typeof detail === 'string') {
        message.error(detail)
      } else if (detail?.message) {
        message.error(detail.message)
      } else {
        message.error('返佣兑换灵石失败，请稍后重试')
      }
    } finally {
      redeemCreditsLoading.value = false
    }
  }

  const handleRedeemMembership = async () => {
    redeemMembershipLoading.value = true
    try {
      const selectedOption = membershipRedeemOptions.find(
        (option) => option.key === redeemMembershipForm.optionKey
      )
      await api.post('/users/me/affiliate/redeem-membership', {
        option_key: redeemMembershipForm.optionKey,
        idempotency_key: buildIdempotencyKey('membership_redeem')
      })
      await options.refreshUser()
      message.success(
        `返佣兑换身份成功${selectedOption ? `：${selectedOption.label}，附加 ${selectedOption.bonusCredits} 灵石` : ''}`
      )
      showRedeemMembershipModal.value = false
    } catch (error: any) {
      console.error('Redeem membership error:', error)
      const detail = error.response?.data?.detail
      if (typeof detail === 'string') {
        message.error(detail)
      } else if (detail?.message) {
        message.error(detail.message)
      } else {
        message.error('返佣兑换身份失败，请稍后重试')
      }
    } finally {
      redeemMembershipLoading.value = false
    }
  }

  return {
    redeemCreditsLoading,
    redeemMembershipLoading,
    showRedeemCreditsModal,
    showRedeemMembershipModal,
    redeemCreditsForm,
    redeemMembershipForm,
    redeemCreditsPackages,
    membershipRedeemOptions,
    availableCommissionUsdt,
    totalCommissionUsdt,
    spentCommissionUsdt,
    openRedeemCreditsModal,
    openRedeemMembershipModal,
    handleRedeemCredits,
    handleRedeemMembership
  }
}
