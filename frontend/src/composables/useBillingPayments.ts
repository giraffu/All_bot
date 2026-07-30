import { onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import type { TonConnectUI } from '@tonconnect/ui'
import { message } from 'ant-design-vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '@/api'
import { useAuthStore, type PaymentAccountSummary } from '@/stores/auth'
import { getRuntimeConfig } from '@/config/runtime'
import { buildUsdtTonTransferMessage } from './usdtTonTransfer'

export type PayMethod = 'alipay' | 'wxpay' | 'ton' | 'usdt-ton'
export type BillingPlanKind = 'membership' | 'credits' | null
type OrderStatus = 'PENDING' | 'SUCCESS' | 'FAILED' | 'TIMEOUT'
type TelegramPaymentWebApp = {
  openLink?: (url: string, options?: { try_instant_view?: boolean }) => void
}
type TelegramPaymentWindow = Window & {
  Telegram?: {
    WebApp?: TelegramPaymentWebApp
  }
}

const MAX_POLL_COUNT = 100
const TONCONNECT_MANIFEST_URL =
  getRuntimeConfig('tonconnect_manifest_url', '') ||
  `${window.location.origin}/tonconnect-manifest.json`
const TONCONNECT_TWA_RETURN_URL =
  getRuntimeConfig('tonconnect_twa_return_url', '') ||
  (getRuntimeConfig('telegram_bot_username', '')
    ? `https://t.me/${getRuntimeConfig('telegram_bot_username', '')}`
    : undefined)

export const getTelegramPaymentWebApp = (): TelegramPaymentWebApp | undefined =>
  (window as TelegramPaymentWindow).Telegram?.WebApp

export const hasTelegramExternalLinkOpener = () =>
  typeof getTelegramPaymentWebApp()?.openLink === 'function'

const asSingleQueryValue = (value: unknown) => {
  if (value === null || value === undefined) return null
  return typeof value === 'string' ? value : undefined
}

export const resolveBillingEntry = (query: Record<string, unknown>): {
  method: PayMethod
  kind: BillingPlanKind
} => {
  const rawMethod = asSingleQueryValue(query.method)
  const rawKind = asSingleQueryValue(query.kind)
  const validMethod = rawMethod !== undefined
    && (rawMethod === null || ['alipay', 'wxpay', 'ton', 'usdt-ton'].includes(rawMethod))
  const validKind = rawKind !== undefined
    && (rawKind === null || ['membership', 'credits'].includes(rawKind))

  if (!validMethod || !validKind) {
    return { method: 'alipay', kind: null }
  }

  return {
    method: (rawMethod ?? 'alipay') as PayMethod,
    kind: rawKind as BillingPlanKind,
  }
}

export const filterPlansForBillingKind = <T extends { duration_days: number }>(
  plans: T[],
  kind: BillingPlanKind,
) => {
  if (kind === 'membership') return plans.filter((plan) => plan.duration_days > 0)
  if (kind === 'credits') return plans.filter((plan) => plan.duration_days === 0)
  return plans
}

type TonPlansAvailability = {
  ton_payment_enabled?: boolean
  ton_receiver_address?: string | null
  usdt_ton_payment_enabled?: boolean
  usdt_ton_receiver_address?: string | null
  usdt_ton_jetton_master_address?: string | null
}

type TonOrderTransaction = {
  ton_receiver_address?: string | null
  amount_nanotons?: string | null
}

export const resolveTonPaymentAvailability = (data: TonPlansAvailability) => {
  const receiverAddress = typeof data.ton_receiver_address === 'string'
    ? data.ton_receiver_address.trim()
    : ''
  const enabled = data.ton_payment_enabled === true && receiverAddress.length > 0
  return {
    enabled,
    receiverAddress: enabled ? receiverAddress : null,
  }
}

export const resolveUsdtTonPaymentAvailability = (data: TonPlansAvailability) => {
  const receiverAddress = typeof data.usdt_ton_receiver_address === 'string'
    ? data.usdt_ton_receiver_address.trim()
    : ''
  const jettonMasterAddress = typeof data.usdt_ton_jetton_master_address === 'string'
    ? data.usdt_ton_jetton_master_address.trim()
    : ''
  const enabled = data.usdt_ton_payment_enabled === true
    && receiverAddress.length > 0
    && jettonMasterAddress.length > 0
  return {
    enabled,
    receiverAddress: enabled ? receiverAddress : null,
    jettonMasterAddress: enabled ? jettonMasterAddress : null,
  }
}

export const buildTonTransactionMessage = (
  order: TonOrderTransaction,
  payload: string,
) => {
  const address = typeof order.ton_receiver_address === 'string'
    ? order.ton_receiver_address.trim()
    : ''
  const amount = typeof order.amount_nanotons === 'string'
    ? order.amount_nanotons.trim()
    : ''
  if (!address || !amount || !payload) {
    throw new Error('invalid TON order response')
  }
  return { address, amount, payload }
}

export const openExternalPaymentUrl = (
  payUrl: string,
  preopenedWindow?: Window | null
) => {
  const telegramWebApp = getTelegramPaymentWebApp()
  if (typeof telegramWebApp?.openLink === 'function') {
    try {
      telegramWebApp.openLink(payUrl, { try_instant_view: false })
      if (preopenedWindow && !preopenedWindow.closed) {
        preopenedWindow.close()
      }
      return
    } catch (error) {
      console.warn('Telegram openLink failed, falling back to browser navigation:', error)
    }
  }

  if (preopenedWindow && !preopenedWindow.closed) {
    preopenedWindow.location.href = payUrl
    return
  }

  const openedWindow = window.open(payUrl, '_blank')
  if (!openedWindow) {
    window.location.href = payUrl
  }
}

export function useBillingPayments() {
  const authStore = useAuthStore()
  const route = useRoute()
  const { t } = useI18n()

  const loadingPlans = ref(true)
  const plans = ref<any[]>([])
  const selectedPlan = ref<any>(null)
  const billingEntry = resolveBillingEntry(route.query)
  const payMethod = ref<PayMethod>(billingEntry.method)
  const planKind = ref<BillingPlanKind>(billingEntry.kind)
  const isPaying = ref(false)

  const rmbPollingTimer = ref<ReturnType<typeof setTimeout> | null>(null)
  const tonPollingTimer = ref<ReturnType<typeof setTimeout> | null>(null)
  const pollCount = ref(0)
  const showPaymentModal = ref(false)
  const orderStatus = ref<OrderStatus>('PENDING')

  const tonConnectUI = shallowRef<TonConnectUI | null>(null)
  const tonWalletAddress = ref<string | null>(null)
  const tonPaymentEnabled = ref(false)
  const usdtTonPaymentEnabled = ref(false)
  const currentTonOrderId = ref<string | null>(null)
  const pendingTonPayAfterConnect = ref(false)
  const isSubmittingTonPayment = ref(false)
  let tonBeginCell: ((typeof import('@ton/core'))['beginCell']) | null = null

  const resetTonConnectIntent = () => {
    pendingTonPayAfterConnect.value = false
  }

  const submitTonPayment = async (tonUI: TonConnectUI) => {
    if (!selectedPlan.value) return
    if (!tonPaymentEnabled.value) {
      message.warning(t('billing.ton_unavailable'))
      return
    }
    if (isSubmittingTonPayment.value) return

    isSubmittingTonPayment.value = true
    isPaying.value = true

    try {
      const res = await api.post('/payment/ton-orders', {
        plan_id: selectedPlan.value.id
      })
      const tonOrder = res.data?.data
      if (!tonOrder?.ton_comment) {
        throw new Error('invalid TON order response')
      }

      const textCellHex = await stringToCellHex(tonOrder.ton_comment)
      currentTonOrderId.value = tonOrder.order_id

      const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 600,
        messages: [
          buildTonTransactionMessage(tonOrder, textCellHex)
        ]
      }

      const result = await tonUI.sendTransaction(transaction)
      if (result) {
        showPaymentModal.value = true
        orderStatus.value = 'PENDING'
        startTonPolling(currentTonOrderId.value)
      }
    } catch (error) {
      console.error('TON transaction error:', error)
      message.error('支付已取消或发生错误')
    } finally {
      resetTonConnectIntent()
      isSubmittingTonPayment.value = false
      isPaying.value = false
    }
  }

  const submitUsdtTonPayment = async (tonUI: TonConnectUI) => {
    if (!selectedPlan.value || !tonWalletAddress.value) return
    if (!usdtTonPaymentEnabled.value) {
      message.warning(t('billing.usdt_ton_unavailable'))
      return
    }
    if (isSubmittingTonPayment.value) return

    isSubmittingTonPayment.value = true
    isPaying.value = true
    try {
      const res = await api.post('/payment/usdt-ton-orders', {
        plan_id: selectedPlan.value.id,
      })
      const usdtOrder = res.data?.data
      const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 600,
        messages: [
          buildUsdtTonTransferMessage(usdtOrder, tonWalletAddress.value),
        ],
      }
      currentTonOrderId.value = usdtOrder?.order_id
      const result = await tonUI.sendTransaction(transaction)
      if (result) {
        showPaymentModal.value = true
        orderStatus.value = 'PENDING'
        startTonPolling(currentTonOrderId.value)
      }
    } catch (error) {
      console.error('USDT-TON transaction error:', error)
      message.error(t('billing.usdt_ton_payment_error'))
    } finally {
      resetTonConnectIntent()
      isSubmittingTonPayment.value = false
      isPaying.value = false
    }
  }

  const submitSelectedCryptoPayment = async (tonUI: TonConnectUI) => {
    if (payMethod.value === 'usdt-ton') {
      await submitUsdtTonPayment(tonUI)
      return
    }
    await submitTonPayment(tonUI)
  }

  const handleTonWalletStatusChange = (
    wallet: { account: { address: string } } | null
  ) => {
    tonWalletAddress.value = wallet ? wallet.account.address : null

    if (!wallet) {
      resetTonConnectIntent()
      return
    }

    if (
      !pendingTonPayAfterConnect.value
      || !['ton', 'usdt-ton'].includes(payMethod.value)
      || !selectedPlan.value
    ) {
      return
    }

    tonConnectUI.value?.closeModal('wallet-selected')
    void submitSelectedCryptoPayment(tonConnectUI.value!)
  }

  const ensureTonModules = async () => {
    if (!tonConnectUI.value || !tonBeginCell) {
      const [{ TonConnectUI }, tonCore] = await Promise.all([
        import('@tonconnect/ui'),
        import('@ton/core')
      ])

      tonBeginCell ??= tonCore.beginCell

      if (!tonConnectUI.value) {
        const instance = new TonConnectUI({
          manifestUrl: TONCONNECT_MANIFEST_URL,
          actionsConfiguration: {
            ...(TONCONNECT_TWA_RETURN_URL ? { twaReturnUrl: TONCONNECT_TWA_RETURN_URL } : {})
          }
        })
        instance.onStatusChange(handleTonWalletStatusChange)
        tonConnectUI.value = instance
      }
    }

    return tonConnectUI.value
  }

  const fetchPlans = async () => {
    loadingPlans.value = true
    try {
      const res = await api.get('/payment/plans')
      if (res.data?.data) {
        plans.value = res.data.data.plans || res.data.data
        tonPaymentEnabled.value = resolveTonPaymentAvailability(
          res.data.data
        ).enabled
        usdtTonPaymentEnabled.value = resolveUsdtTonPaymentAvailability(
          res.data.data
        ).enabled
      }
    } catch (error) {
      console.error('Failed to fetch plans', error)
      message.error('无法加载充值套餐')
    } finally {
      loadingPlans.value = false
    }
  }

  const handlePaymentSuccess = async (account?: PaymentAccountSummary | null) => {
    message.success('支付成功，灵石/身份已到账！')
    if (account) authStore.applyPaymentAccount(account)
  }

  const stopRmbPolling = () => {
    if (rmbPollingTimer.value) {
      clearTimeout(rmbPollingTimer.value)
      rmbPollingTimer.value = null
    }
  }

  const stopTonPolling = () => {
    if (tonPollingTimer.value) {
      clearTimeout(tonPollingTimer.value)
      tonPollingTimer.value = null
    }
  }

  const startRmbPolling = (orderId: string) => {
    stopRmbPolling()
    pollCount.value = 0

    const poll = async () => {
      if (pollCount.value >= MAX_POLL_COUNT) {
        orderStatus.value = 'TIMEOUT'
        return
      }

      pollCount.value++
      try {
        const res = await api.get(`/payment/orders/${orderId}/status`)
        const statusData = res.data?.data
        const status = statusData?.status
        if (status === 'SUCCESS') {
          orderStatus.value = 'SUCCESS'
          await handlePaymentSuccess(statusData.account)
          return
        }
        if (status === 'FAILED') {
          orderStatus.value = 'FAILED'
          return
        }
      } catch (error) {
        console.error('Polling error', error)
      }

      rmbPollingTimer.value = setTimeout(poll, 3000)
    }

    rmbPollingTimer.value = setTimeout(poll, 3000)
  }

  const handleRmbPay = async () => {
    if (!selectedPlan.value) return

    isPaying.value = true
    const newWin = hasTelegramExternalLinkOpener()
      ? null
      : window.open('about:blank', '_blank')
    const payType = payMethod.value === 'wxpay' ? 'wxpay' : 'alipay'

    try {
      const res = await api.post('/payment/orders', {
        plan_id: selectedPlan.value.id,
        pay_type: payType
      })

      const { order_id, pay_url } = res.data?.data ?? {}
      if (!pay_url) {
        throw new Error('missing pay_url')
      }

      new URL(pay_url)
      openExternalPaymentUrl(pay_url, newWin)

      showPaymentModal.value = true
      orderStatus.value = 'PENDING'
      startRmbPolling(order_id)
    } catch (error) {
      console.error('Create order error', error)
      message.error('创建订单失败，请稍后重试')
      if (newWin) newWin.close()
    } finally {
      isPaying.value = false
    }
  }

  const stringToCellHex = async (text: string) => {
    await ensureTonModules()
    if (!tonBeginCell) {
      throw new Error('TON core is not initialized')
    }

    return tonBeginCell()
      .storeUint(0, 32)
      .storeStringTail(text)
      .endCell()
      .toBoc()
      .toString('base64')
  }

  const startTonPolling = (orderId?: string | null) => {
    stopTonPolling()
    const targetOrderId = orderId || currentTonOrderId.value
    if (!targetOrderId) {
      orderStatus.value = 'FAILED'
      return
    }

    let tonPollCount = 0
    const poll = async () => {
      if (tonPollCount >= MAX_POLL_COUNT) {
        orderStatus.value = 'TIMEOUT'
        return
      }
      tonPollCount++

      try {
        const res = await api.get(`/payment/orders/${targetOrderId}/status`)
        const statusData = res.data?.data
        const status = statusData?.status
        if (status === 'SUCCESS') {
          orderStatus.value = 'SUCCESS'
          await handlePaymentSuccess(statusData.account)
          return
        }
        if (status === 'FAILED') {
          orderStatus.value = 'FAILED'
          return
        }
      } catch (error) {
        console.error('TON Polling error', error)
      }

      tonPollingTimer.value = setTimeout(poll, 5000)
    }

    tonPollingTimer.value = setTimeout(poll, 5000)
  }

  const openTonConnectModal = async () => {
    const selectedMethodEnabled = payMethod.value === 'usdt-ton'
      ? usdtTonPaymentEnabled.value
      : tonPaymentEnabled.value
    if (!selectedMethodEnabled) {
      message.warning(t(
        payMethod.value === 'usdt-ton'
          ? 'billing.usdt_ton_unavailable'
          : 'billing.ton_unavailable',
      ))
      return
    }
    try {
      pendingTonPayAfterConnect.value = true
      const tonUI = await ensureTonModules()
      tonUI?.openModal()
    } catch (error) {
      resetTonConnectIntent()
      console.error('TON Connect modal open error:', error)
      message.error('TON 钱包组件加载失败，请稍后重试')
    }
  }

  const disconnectTonWallet = async () => {
    try {
      resetTonConnectIntent()
      const tonUI = await ensureTonModules()
      await tonUI?.disconnect()
    } catch (error) {
      console.error('TON wallet disconnect error:', error)
      message.error('断开 TON 钱包失败，请稍后重试')
    }
  }

  const handleTonPay = async () => {
    if (!selectedPlan.value) return
    if (!tonPaymentEnabled.value) {
      message.warning(t('billing.ton_unavailable'))
      return
    }

    let tonUI: TonConnectUI | null = null
    try {
      tonUI = await ensureTonModules()
    } catch (error) {
      console.error('TON modules load error:', error)
      message.error('TON 钱包组件加载失败，请稍后重试')
      return
    }

    if (!tonUI) {
      message.error('TON 钱包初始化失败，请稍后重试')
      return
    }

    if (!tonUI.connected) {
      message.warning('请先连接 TON 钱包')
      pendingTonPayAfterConnect.value = true
      tonUI.openModal()
      return
    }

    await submitTonPayment(tonUI)
  }

  const handleUsdtTonPay = async () => {
    if (!selectedPlan.value) return
    if (!usdtTonPaymentEnabled.value) {
      message.warning(t('billing.usdt_ton_unavailable'))
      return
    }
    let tonUI: TonConnectUI | null = null
    try {
      tonUI = await ensureTonModules()
    } catch (error) {
      console.error('TON modules load error:', error)
      message.error(t('billing.ton_wallet_load_error'))
      return
    }
    if (!tonUI) return
    if (!tonUI.connected) {
      pendingTonPayAfterConnect.value = true
      tonUI.openModal()
      return
    }
    await submitUsdtTonPayment(tonUI)
  }

  onMounted(async () => {
    await fetchPlans()
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

  watch(payMethod, async (method) => {
    if (!['ton', 'usdt-ton'].includes(method)) {
      resetTonConnectIntent()
      return
    }
    try {
      await ensureTonModules()
    } catch (error) {
      console.error('TON module preload error:', error)
    }
  })

  return {
    loadingPlans,
    plans,
    planKind,
    selectedPlan,
    payMethod,
    isPaying,
    showPaymentModal,
    orderStatus,
    tonWalletAddress,
    tonPaymentEnabled,
    usdtTonPaymentEnabled,
    handleRmbPay,
    handleTonPay,
    handleUsdtTonPay,
    openTonConnectModal,
    disconnectTonWallet,
    fetchPlans
  }
}
