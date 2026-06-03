import { onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import type { TonConnectUI } from '@tonconnect/ui'
import { message } from 'ant-design-vue'
import { useRoute } from 'vue-router'
import api from '@/api'
import { useAuthStore } from '@/stores/auth'

type PayMethod = 'alipay' | 'wxpay' | 'ton'
type OrderStatus = 'PENDING' | 'SUCCESS' | 'FAILED' | 'TIMEOUT'
type TelegramPaymentWebApp = {
  openLink?: (url: string, options?: { try_instant_view?: boolean }) => void
}
type TelegramPaymentWindow = Window & {
  Telegram?: {
    WebApp?: TelegramPaymentWebApp
  }
}

const DEFAULT_TON_RECEIVER = 'UQC2q_W2d061mO_g3zB-hK12v0p2u44-nI5z9F82L1j88g7b'
const MAX_POLL_COUNT = 100
const TONCONNECT_MANIFEST_URL =
  import.meta.env.VITE_TONCONNECT_MANIFEST_URL ||
  `${window.location.origin}/tonconnect-manifest.json`
const TONCONNECT_TWA_RETURN_URL =
  import.meta.env.VITE_TONCONNECT_TWA_RETURN_URL ||
  (import.meta.env.VITE_TELEGRAM_BOT_USERNAME
    ? `https://t.me/${import.meta.env.VITE_TELEGRAM_BOT_USERNAME}`
    : undefined)

export const getTelegramPaymentWebApp = (): TelegramPaymentWebApp | undefined =>
  (window as TelegramPaymentWindow).Telegram?.WebApp

export const hasTelegramExternalLinkOpener = () =>
  typeof getTelegramPaymentWebApp()?.openLink === 'function'

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

  const loadingPlans = ref(true)
  const plans = ref<any[]>([])
  const selectedPlan = ref<any>(null)
  const payMethod = ref<PayMethod>('alipay')
  const isPaying = ref(false)

  const rmbPollingTimer = ref<ReturnType<typeof setTimeout> | null>(null)
  const tonPollingTimer = ref<ReturnType<typeof setTimeout> | null>(null)
  const pollCount = ref(0)
  const showPaymentModal = ref(false)
  const orderStatus = ref<OrderStatus>('PENDING')

  const tonConnectUI = shallowRef<TonConnectUI | null>(null)
  const tonWalletAddress = ref<string | null>(null)
  const systemTonReceiver = ref<string>(DEFAULT_TON_RECEIVER)
  const currentTonOrderId = ref<string | null>(null)
  const pendingTonPayAfterConnect = ref(false)
  const isSubmittingTonPayment = ref(false)
  let tonBeginCell: ((typeof import('@ton/core'))['beginCell']) | null = null

  const resetTonConnectIntent = () => {
    pendingTonPayAfterConnect.value = false
  }

  const submitTonPayment = async (tonUI: TonConnectUI) => {
    if (!selectedPlan.value) return
    if (isSubmittingTonPayment.value) return

    isSubmittingTonPayment.value = true
    isPaying.value = true

    try {
      const res = await api.post('/payment/ton-orders', {
        plan_id: selectedPlan.value.id
      })
      const tonOrder = res.data?.data
      if (!tonOrder?.ton_comment || !tonOrder?.amount_nanotons) {
        throw new Error('invalid TON order response')
      }

      const textCellHex = await stringToCellHex(tonOrder.ton_comment)
      currentTonOrderId.value = tonOrder.order_id

      const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 600,
        messages: [
          {
            address: tonOrder.ton_receiver_address || systemTonReceiver.value,
            amount: tonOrder.amount_nanotons,
            payload: textCellHex
          }
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

  const handleTonWalletStatusChange = (
    wallet: { account: { address: string } } | null
  ) => {
    tonWalletAddress.value = wallet ? wallet.account.address : null

    if (!wallet) {
      resetTonConnectIntent()
      return
    }

    if (!pendingTonPayAfterConnect.value || payMethod.value !== 'ton' || !selectedPlan.value) {
      return
    }

    tonConnectUI.value?.closeModal('wallet-selected')
    void submitTonPayment(tonConnectUI.value!)
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

  const handlePaymentSuccess = async () => {
    message.success('支付成功，灵石/身份已到账！')
    await authStore.fetchUser()
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
        const status = res.data?.data?.status
        if (status === 'SUCCESS') {
          orderStatus.value = 'SUCCESS'
          await handlePaymentSuccess()
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
        const status = res.data?.data?.status
        if (status === 'SUCCESS') {
          orderStatus.value = 'SUCCESS'
          await handlePaymentSuccess()
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
    if (method !== 'ton') {
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
    selectedPlan,
    payMethod,
    isPaying,
    showPaymentModal,
    orderStatus,
    tonWalletAddress,
    handleRmbPay,
    handleTonPay,
    openTonConnectModal,
    disconnectTonWallet,
    fetchPlans
  }
}
