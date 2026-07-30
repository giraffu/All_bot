<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { UsdtTonConfirmationDetails } from '@/composables/useBillingPayments'

defineProps<{
  open: boolean
  details: UsdtTonConfirmationDetails | null
  loading: boolean
}>()

defineEmits<{
  confirm: []
  cancel: []
}>()

const { t } = useI18n()
</script>

<template>
  <a-modal
    :open="open"
    :title="t('billing.usdt_ton_confirm_title')"
    :footer="null"
    :closable="false"
    :maskClosable="false"
    class="dark-modal usdt-confirm-modal"
  >
    <div v-if="details" class="space-y-4 py-2">
      <div class="rounded-2xl border border-emerald-400/20 bg-emerald-500/10 px-4 py-4 text-center">
        <p class="text-xs uppercase tracking-[0.18em] text-emerald-300">
          {{ t('billing.usdt_ton_confirm_amount_label') }}
        </p>
        <p class="mt-1 text-2xl font-extrabold text-white">
          {{ details.amount }}
        </p>
      </div>

      <dl class="space-y-3 rounded-2xl border border-slate-700/80 bg-slate-900/60 px-4 py-4">
        <div class="flex items-center justify-between gap-4">
          <dt class="text-sm text-slate-400">{{ t('billing.usdt_ton_confirm_network') }}</dt>
          <dd class="font-semibold text-cyan-300">{{ details.network }}</dd>
        </div>
        <div class="space-y-1.5">
          <dt class="text-sm text-slate-400">{{ t('billing.usdt_ton_confirm_receiver') }}</dt>
          <dd class="break-all rounded-lg bg-slate-950/70 px-3 py-2 font-mono text-xs leading-5 text-slate-200">
            {{ details.receiverAddress }}
          </dd>
        </div>
        <div class="flex items-center justify-between gap-4">
          <dt class="text-sm text-slate-400">{{ t('billing.usdt_ton_confirm_max_gas') }}</dt>
          <dd class="font-semibold text-amber-300">{{ details.maxGas }}</dd>
        </div>
      </dl>

      <div class="rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-3 text-xs leading-5 text-amber-100">
        {{ t('billing.usdt_ton_wallet_gas_only_notice') }}
      </div>

      <div class="grid grid-cols-2 gap-3 pt-1">
        <a-button size="large" class="usdt-confirm-cancel h-11" @click="$emit('cancel')">
          {{ t('billing.cancel') }}
        </a-button>
        <a-button
          type="primary"
          size="large"
          class="usdt-confirm-submit h-11 border-none font-bold"
          :loading="loading"
          @click="$emit('confirm')"
        >
          {{ t('billing.usdt_ton_open_wallet') }}
        </a-button>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
:global(.usdt-confirm-modal .ant-modal-content) {
  background: #0f172a;
  border: 1px solid rgba(71, 85, 105, 0.75);
  box-shadow: 0 28px 80px rgba(0, 0, 0, 0.55);
}

:global(.usdt-confirm-modal .ant-modal-header) {
  background: transparent;
  border-bottom: 1px solid rgba(71, 85, 105, 0.55);
  margin-bottom: 1rem;
  padding-bottom: 0.875rem;
}

:global(.usdt-confirm-modal .ant-modal-title) {
  color: #f8fafc;
}

:global(.usdt-confirm-modal .usdt-confirm-cancel) {
  background: #1e293b;
  border-color: #475569;
  color: #e2e8f0;
}

:global(.usdt-confirm-modal .usdt-confirm-cancel:hover) {
  background: #334155;
  border-color: #64748b;
  color: #ffffff;
}

:global(.usdt-confirm-modal .usdt-confirm-submit) {
  background: linear-gradient(90deg, #059669, #0891b2);
  color: #ffffff;
}

:global(.usdt-confirm-modal .usdt-confirm-submit:hover) {
  background: linear-gradient(90deg, #10b981, #06b6d4);
  color: #ffffff;
}

@media (max-width: 480px) {
  :global(.usdt-confirm-modal) {
    max-width: calc(100vw - 1.25rem);
  }

  :global(.usdt-confirm-modal .ant-modal-content) {
    padding: 1rem;
  }
}
</style>
