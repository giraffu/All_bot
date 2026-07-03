<script setup lang="ts">
import { computed, watch } from 'vue'
import dayjs from 'dayjs'
import { ReceiptText } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useCreditLedger } from '@/composables/useCreditLedger'
import { useViewport } from '@/composables/useViewport'
import type { CreditLedgerItem } from '@/types/creditLedger'
import ProfileBackButton from '@/components/profile/ProfileBackButton.vue'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const { t, te } = useI18n()
const { isMobile } = useViewport()
const {
  items,
  loading,
  loadingMore,
  error,
  hasMore,
  reset,
  loadLedger,
  loadMore,
} = useCreditLedger(20)

const emptyText = computed(() =>
  error.value ? t('credit_ledger.load_failed') : t('credit_ledger.empty'),
)

const closeModal = () => {
  emit('update:open', false)
}

const formatDate = (dateString: string) => dayjs(dateString).format('YYYY-MM-DD HH:mm')

const formatCreditChange = (item: CreditLedgerItem) => {
  const amount = Math.abs(item.credit_change)
  return item.direction === 'income' ? `+${amount}` : `-${amount}`
}

const getOperationTypeLabel = (operationType: string) => {
  const normalized = operationType.replace(/-/g, '_')
  const key = `credit_ledger.operation_types.${normalized}`
  return te(key) ? t(key) : operationType
}

const getDirectionLabel = (item: CreditLedgerItem) =>
  t(`credit_ledger.${item.direction}`)

const getContextEntries = (item: CreditLedgerItem) =>
  Object.entries(item.display_context ?? {}).map(([key, value]) => {
    const labelKey = `credit_ledger.context.${key}`
    return {
      key,
      label: te(labelKey) ? t(labelKey) : key,
      value,
    }
  })

const retryLoad = () => {
  void loadLedger({ reset: true })
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      void loadLedger({ reset: true })
    } else {
      reset()
    }
  },
  { immediate: true },
)
</script>

<template>
  <a-modal
    :open="open"
    :footer="null"
    :closable="false"
    :width="isMobile ? '100%' : 760"
    :style="isMobile ? { top: 0, padding: 0, margin: 0, maxWidth: '100%' } : { top: '32px' }"
    class="profile-credit-ledger-modal"
    destroyOnClose
    @update:open="emit('update:open', $event)"
  >
    <div class="profile-credit-ledger-modal__panel p-5 sm:p-6">
      <div class="profile-credit-ledger-modal__header mb-4">
        <ProfileBackButton :label="t('profile.back_to_profile')" @click="closeModal" />
        <div class="flex items-center gap-2 min-w-0">
          <ReceiptText :size="18" class="profile-credit-ledger-modal__icon shrink-0" />
          <h3 class="profile-credit-ledger-modal__title text-lg font-bold truncate">
            {{ t('credit_ledger.title') }}
          </h3>
        </div>
      </div>

      <a-spin :spinning="loading">
        <div v-if="items.length" class="profile-credit-ledger-modal__list">
          <div
            v-for="item in items"
            :key="item.id"
            class="profile-credit-ledger-modal__item"
            :data-testid="`credit-ledger-item-${item.id}`"
          >
            <div class="profile-credit-ledger-modal__main">
              <div class="min-w-0">
                <div class="profile-credit-ledger-modal__name truncate">
                  {{ getOperationTypeLabel(item.operation_type) }}
                </div>
                <div class="profile-credit-ledger-modal__time">
                  {{ formatDate(item.created_at) }}
                </div>
              </div>
              <div
                :class="[
                  'profile-credit-ledger-modal__amount',
                  `profile-credit-ledger-modal__amount--${item.direction}`,
                ]"
              >
                <span>{{ getDirectionLabel(item) }}</span>
                <strong>{{ formatCreditChange(item) }}</strong>
              </div>
            </div>

            <div class="profile-credit-ledger-modal__meta">
              <span>
                {{ t('credit_ledger.balance_after') }} {{ item.current_balance }}
              </span>
              <span
                v-for="entry in getContextEntries(item)"
                :key="entry.key"
                class="profile-credit-ledger-modal__context"
              >
                {{ entry.label }} {{ entry.value }}
              </span>
            </div>
          </div>
        </div>

        <div
          v-else
          class="profile-credit-ledger-modal__empty"
          data-testid="credit-ledger-empty"
        >
          {{ emptyText }}
        </div>
      </a-spin>

      <div class="profile-credit-ledger-modal__footer mt-4">
        <a-button
          v-if="error"
          data-testid="credit-ledger-retry"
          class="profile-credit-ledger-modal__footer-btn"
          @click="retryLoad"
        >
          {{ t('credit_ledger.retry') }}
        </a-button>
        <a-button
          v-if="hasMore"
          data-testid="credit-ledger-load-more"
          class="profile-credit-ledger-modal__footer-btn"
          :loading="loadingMore"
          @click="loadMore"
        >
          {{ t('credit_ledger.load_more') }}
        </a-button>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.profile-credit-ledger-modal__panel {
  background: var(--theme-card-bg);
}

.profile-credit-ledger-modal__header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-height: 2.625rem;
}

.profile-credit-ledger-modal__icon {
  color: #0d9488;
}

.profile-credit-ledger-modal__title,
.profile-credit-ledger-modal__name {
  color: var(--theme-text-primary);
}

.profile-credit-ledger-modal__list {
  display: grid;
  gap: 0.75rem;
}

.profile-credit-ledger-modal__item,
.profile-credit-ledger-modal__empty {
  border: 1px solid var(--theme-border);
  border-radius: 0.5rem;
  background: var(--theme-card-strong-bg);
}

.profile-credit-ledger-modal__item {
  padding: 0.875rem;
}

.profile-credit-ledger-modal__main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.75rem;
  align-items: center;
}

.profile-credit-ledger-modal__name {
  font-weight: 650;
  line-height: 1.35;
}

.profile-credit-ledger-modal__time,
.profile-credit-ledger-modal__meta {
  color: var(--theme-text-secondary);
}

.profile-credit-ledger-modal__time {
  margin-top: 0.125rem;
  font-size: 0.8125rem;
}

.profile-credit-ledger-modal__amount {
  min-width: 5.75rem;
  min-height: 2.375rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  border-radius: 999px;
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
  white-space: nowrap;
}

.profile-credit-ledger-modal__amount--income {
  color: #047857;
  background: rgba(16, 185, 129, 0.14);
  border: 1px solid rgba(16, 185, 129, 0.28);
}

.profile-credit-ledger-modal__amount--expense {
  color: #be123c;
  background: rgba(244, 63, 94, 0.12);
  border: 1px solid rgba(244, 63, 94, 0.26);
}

.profile-credit-ledger-modal__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem 0.625rem;
  margin-top: 0.625rem;
  font-size: 0.8125rem;
}

.profile-credit-ledger-modal__context {
  min-width: 0;
}

.profile-credit-ledger-modal__empty {
  padding: 2rem;
  text-align: center;
  color: var(--theme-text-secondary);
}

.profile-credit-ledger-modal__footer {
  display: flex;
  justify-content: center;
  gap: 0.625rem;
}

.profile-credit-ledger-modal__footer-btn {
  min-width: 7rem;
}

@media (max-width: 420px) {
  .profile-credit-ledger-modal__main {
    grid-template-columns: minmax(0, 1fr);
  }

  .profile-credit-ledger-modal__amount {
    justify-self: start;
  }
}

:global(.profile-credit-ledger-modal .ant-modal-content) {
  background-color: var(--theme-card-bg) !important;
  color: var(--theme-text-primary) !important;
}
</style>
