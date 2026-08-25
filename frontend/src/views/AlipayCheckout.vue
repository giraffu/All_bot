<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import QRCode from 'qrcode'

import api from '@/api'
import { getRuntimeConfig } from '@/config/runtime'

type CheckoutStatus = 'PENDING' | 'SUCCESS' | 'FAILED'

type CheckoutData = {
  order_id: string
  subject: string
  amount: string
  status: CheckoutStatus
  created_at: string
}

const POLL_INTERVAL_MS = 3000

const route = useRoute()
const { t, locale } = useI18n()
const checkout = ref<CheckoutData | null>(null)
const qrDataUrl = ref('')
const loading = ref(true)
const errorState = ref<'expired' | 'failed' | null>(null)
let pollTimer: ReturnType<typeof setTimeout> | null = null

const token = computed(() => String(route.params.token || ''))
const checkoutPath = computed(
  () => `/payment/alipay-checkout/${encodeURIComponent(token.value)}`,
)
const launchUrl = computed(() => {
  const apiBase = String(getRuntimeConfig('api_base_url', '/api')).replace(/\/$/, '')
  return new URL(
    `${apiBase}${checkoutPath.value}/launch`,
    window.location.origin,
  ).toString()
})
const displayCreatedAt = computed(() => {
  if (!checkout.value?.created_at) return '—'
  const value = new Date(checkout.value.created_at)
  if (Number.isNaN(value.getTime())) return '—'
  return new Intl.DateTimeFormat(locale.value === 'en' ? 'en-US' : 'zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(value)
})

const stopPolling = () => {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

const goBack = () => window.history.back()

const schedulePoll = () => {
  stopPolling()
  if (checkout.value?.status !== 'PENDING') return
  pollTimer = setTimeout(() => void loadCheckout(false), POLL_INTERVAL_MS)
}

const ensureQrCode = async () => {
  if (qrDataUrl.value) return
  qrDataUrl.value = await QRCode.toDataURL(launchUrl.value, {
    errorCorrectionLevel: 'M',
    margin: 2,
    width: 360,
    color: {
      dark: '#111111',
      light: '#ffffff',
    },
  })
}

const loadCheckout = async (initial: boolean) => {
  try {
    const response = await api.get(checkoutPath.value, {
      suppressGlobalError: true,
    })
    const data = response.data?.data as CheckoutData
    checkout.value = data
    if (data.status === 'FAILED') {
      stopPolling()
      errorState.value = 'failed'
      return
    }
    errorState.value = null
    await ensureQrCode()
    schedulePoll()
  } catch (error: any) {
    stopPolling()
    const reason = error?.response?.data?.reason || error?.response?.data?.detail?.reason
    errorState.value = reason === 'ALIPAY_CHECKOUT_EXPIRED' ? 'expired' : 'failed'
  } finally {
    if (initial) loading.value = false
  }
}

onMounted(() => void loadCheckout(true))
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="checkout-page">
    <header class="mobile-app-bar">
      <button
        type="button"
        class="mobile-back"
        :aria-label="t('alipay_checkout.go_back')"
        @click="goBack"
      >
        ‹
      </button>
      <strong>{{ t('alipay_checkout.pay_now') }}</strong>
      <span aria-hidden="true" class="mobile-menu">•••</span>
    </header>

    <header class="desktop-brand-bar">
      <div class="alipay-mark" aria-hidden="true">支</div>
      <span>{{ t('alipay_checkout.scan_title') }}</span>
    </header>

    <main class="checkout-main">
      <section v-if="loading" class="state-card">
        <span class="state-spinner" />
        <p>{{ t('alipay_checkout.loading') }}</p>
      </section>

      <section v-else-if="errorState" class="state-card">
        <div class="state-icon">!</div>
        <h1>
          {{ t(errorState === 'expired' ? 'alipay_checkout.expired' : 'alipay_checkout.failed') }}
        </h1>
        <p>{{ t('alipay_checkout.retry_hint') }}</p>
      </section>

      <section v-else-if="checkout" class="checkout-content">
        <h1 class="mobile-hero-title">{{ t('alipay_checkout.pay_now') }}</h1>

        <div v-if="checkout.status === 'SUCCESS'" class="success-card" data-testid="checkout-success">
          <div class="success-icon">✓</div>
          <h1>{{ t('alipay_checkout.success') }}</h1>
          <p>{{ t('alipay_checkout.success_hint') }}</p>
          <div class="success-order">{{ checkout.order_id }}</div>
        </div>

        <template v-else>
          <section class="mobile-order-card">
            <div>
              <span>{{ t('alipay_checkout.order_number') }}</span>
              <strong data-testid="checkout-order">{{ checkout.order_id }}</strong>
            </div>
            <div>
              <span>{{ t('alipay_checkout.order_amount') }}</span>
              <strong class="mobile-amount">¥{{ checkout.amount }}</strong>
            </div>
          </section>

          <section class="payment-ticket">
            <div class="ticket-amount" data-testid="checkout-amount">¥{{ checkout.amount }}</div>
            <div class="qr-frame">
              <img
                v-if="qrDataUrl"
                :src="qrDataUrl"
                :alt="t('alipay_checkout.qr_alt')"
                data-testid="checkout-qr"
              >
            </div>

            <p class="mobile-scan-hint">{{ t('alipay_checkout.scan_hint') }}</p>

            <dl class="desktop-order-details">
              <div>
                <dt>{{ t('alipay_checkout.product') }}</dt>
                <dd>{{ checkout.subject }}</dd>
              </div>
              <div>
                <dt>{{ t('alipay_checkout.merchant_order') }}</dt>
                <dd>{{ checkout.order_id }}</dd>
              </div>
              <div>
                <dt>{{ t('alipay_checkout.created_at') }}</dt>
                <dd>{{ displayCreatedAt }}</dd>
              </div>
            </dl>

            <div class="desktop-scan-footer">
              <span class="scan-corners" aria-hidden="true" />
              <p>
                {{ t('alipay_checkout.scan_with_alipay') }}<br>
                {{ t('alipay_checkout.scan_to_finish') }}
              </p>
            </div>
          </section>

          <a
            :href="launchUrl"
            class="mobile-launch-button"
            data-testid="checkout-launch"
          >
            {{ t('alipay_checkout.pay_now') }}
          </a>
        </template>
      </section>
    </main>
  </div>
</template>

<style scoped>
.checkout-page {
  --alipay-blue: #1677ff;
  min-height: 100vh;
  color: #2d2d2d;
  background: #f3f5f8;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.mobile-app-bar {
  height: 72px;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e8ebef;
  font-size: 22px;
}

.mobile-back {
  padding: 0;
  color: inherit;
  background: transparent;
  border: 0;
  cursor: pointer;
  font-size: 46px;
  font-family: inherit;
  font-weight: 300;
  line-height: 1;
}

.mobile-menu {
  letter-spacing: 3px;
  font-size: 17px;
}

.desktop-brand-bar {
  display: none;
}

.checkout-main {
  width: 100%;
  padding: 42px 24px 56px;
}

.checkout-content {
  width: min(100%, 440px);
  margin: 0 auto;
}

.mobile-hero-title {
  margin: 0 0 32px;
  color: var(--alipay-blue);
  text-align: center;
  font-size: 34px;
  font-weight: 600;
}

.mobile-order-card,
.payment-ticket,
.state-card,
.success-card {
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 12px 28px rgba(32, 55, 88, 0.06);
}

.mobile-order-card {
  padding: 28px 26px;
  margin-bottom: 28px;
}

.mobile-order-card > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-width: 0;
}

.mobile-order-card > div + div {
  margin-top: 23px;
}

.mobile-order-card span {
  color: #9299a3;
  font-size: 18px;
  flex: 0 0 auto;
}

.mobile-order-card strong {
  overflow: hidden;
  color: #343940;
  font-size: 18px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mobile-order-card .mobile-amount {
  color: #ff5a17;
  font-size: 22px;
  font-weight: 650;
}

.payment-ticket {
  padding: 42px 24px 34px;
  text-align: center;
}

.ticket-amount,
.desktop-order-details,
.desktop-scan-footer {
  display: none;
}

.qr-frame {
  width: min(100%, 310px);
  aspect-ratio: 1;
  padding: 18px;
  margin: 0 auto;
  display: grid;
  place-items: center;
  background: #fff;
}

.qr-frame img {
  display: block;
  width: 100%;
  height: 100%;
  image-rendering: pixelated;
}

.mobile-scan-hint {
  margin: 22px 0 0;
  color: #6e747d;
  font-size: 18px;
  line-height: 1.5;
}

.mobile-launch-button {
  height: 64px;
  margin-top: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: linear-gradient(110deg, #1877ff, #12aaf3);
  border-radius: 32px;
  box-shadow: 0 14px 28px rgba(22, 119, 255, 0.22);
  font-size: 23px;
  font-weight: 600;
  text-decoration: none;
}

.state-card,
.success-card {
  width: min(calc(100% - 48px), 480px);
  margin: 72px auto 0;
  padding: 52px 32px;
  text-align: center;
}

.state-card h1,
.success-card h1 {
  margin: 18px 0 10px;
  font-size: 26px;
}

.state-card p,
.success-card p {
  color: #7d848d;
  line-height: 1.6;
}

.state-icon,
.success-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: #fff;
  background: #ff8a3d;
  font-size: 36px;
}

.success-icon {
  background: #22b573;
}

.success-order {
  margin-top: 22px;
  color: #8b929c;
  font-size: 14px;
}

.state-spinner {
  width: 40px;
  height: 40px;
  margin: 0 auto 18px;
  display: block;
  border: 4px solid #dbe7f8;
  border-top-color: var(--alipay-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (min-width: 768px) {
  .checkout-page {
    background: #f5f5f5;
  }

  .mobile-app-bar,
  .mobile-hero-title,
  .mobile-order-card,
  .mobile-scan-hint,
  .mobile-launch-button {
    display: none;
  }

  .desktop-brand-bar {
    height: 72px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    background: #fff;
    border-bottom: 1px solid #dedede;
    font-size: 20px;
  }

  .alipay-mark {
    width: 38px;
    height: 38px;
    display: grid;
    place-items: center;
    color: #fff;
    background: var(--alipay-blue);
    border-radius: 9px;
    font-size: 26px;
    font-weight: 700;
  }

  .checkout-main {
    padding: 22px 24px 64px;
  }

  .checkout-content {
    width: min(100%, 880px);
  }

  .payment-ticket {
    min-height: 720px;
    padding: 44px 88px 0;
    border-radius: 0;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  }

  .ticket-amount {
    display: block;
    margin-bottom: 24px;
    font-size: 52px;
    font-weight: 500;
    line-height: 1;
  }

  .qr-frame {
    width: 300px;
    padding: 16px;
  }

  .desktop-order-details {
    margin: 36px 0 0;
    padding: 30px 0;
    display: block;
    border-top: 1px solid #e3e3e3;
    text-align: left;
  }

  .desktop-order-details > div {
    display: grid;
    grid-template-columns: 1fr 1.4fr;
    gap: 30px;
    font-size: 15px;
    line-height: 1.9;
  }

  .desktop-order-details dt {
    color: #555;
  }

  .desktop-order-details dd {
    margin: 0;
    text-align: right;
    overflow-wrap: anywhere;
  }

  .desktop-scan-footer {
    min-height: 96px;
    margin: 0 -88px;
    padding: 22px 88px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 22px;
    border-top: 1px dashed #dedede;
    color: #474747;
    text-align: left;
    line-height: 1.7;
  }

  .scan-corners {
    width: 52px;
    height: 52px;
    border: 3px solid var(--alipay-blue);
    border-left-color: transparent;
    border-right-color: transparent;
    border-radius: 8px;
    position: relative;
  }

  .scan-corners::before,
  .scan-corners::after {
    content: '';
    position: absolute;
    top: 8px;
    bottom: 8px;
    width: 3px;
    background: var(--alipay-blue);
  }

  .scan-corners::before { left: -3px; }
  .scan-corners::after { right: -3px; }

  .desktop-scan-footer p {
    margin: 0;
  }

  .success-card,
  .state-card {
    margin-top: 110px;
  }
}
</style>
