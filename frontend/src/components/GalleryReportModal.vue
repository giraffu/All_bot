<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { GalleryReportReason } from '@/api/gallery'

const props = withDefaults(
  defineProps<{
    open: boolean
    selectedReason: GalleryReportReason
    loading?: boolean
  }>(),
  {
    loading: false,
  },
)

const emit = defineEmits<{
  'update:open': [value: boolean]
  'update:selectedReason': [value: GalleryReportReason]
  submit: []
}>()

const { t } = useI18n()

const reasonOptions = computed<Array<{ value: GalleryReportReason; label: string }>>(() => [
  { value: 'children', label: t('gallery.report.reasons.children') },
  { value: 'gore', label: t('gallery.report.reasons.gore') },
  { value: 'gross', label: t('gallery.report.reasons.gross') },
  { value: 'other', label: t('gallery.report.reasons.other') },
])

const close = () => {
  if (!props.loading) {
    emit('update:open', false)
  }
}
</script>

<template>
  <a-modal
    :open="open"
    :footer="null"
    :destroyOnClose="true"
    :width="420"
    class="gallery-report-modal"
    @update:open="emit('update:open', $event)"
  >
    <div class="gallery-report-modal__panel">
      <h3 class="gallery-report-modal__title">{{ t('gallery.report.modal_title') }}</h3>

      <div class="gallery-report-modal__options">
        <label
          v-for="option in reasonOptions"
          :key="option.value"
          class="gallery-report-modal__option"
          :class="{ 'is-selected': selectedReason === option.value }"
        >
          <input
            class="gallery-report-modal__radio"
            type="radio"
            name="gallery-report-reason"
            :value="option.value"
            :checked="selectedReason === option.value"
            @change="emit('update:selectedReason', option.value)"
          />
          <span>{{ option.label }}</span>
        </label>
      </div>

      <div class="gallery-report-modal__actions">
        <button
          type="button"
          class="gallery-report-modal__secondary"
          :disabled="loading"
          @click="close"
        >
          {{ t('gallery.report.cancel') }}
        </button>
        <button
          type="button"
          class="gallery-report-modal__primary"
          :disabled="loading"
          @click="emit('submit')"
        >
          <span
            v-if="loading"
            class="gallery-report-modal__spinner"
            aria-hidden="true"
          ></span>
          {{ loading ? t('gallery.report.submitting') : t('gallery.report.submit') }}
        </button>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.gallery-report-modal__panel {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.gallery-report-modal__title {
  margin: 0;
  color: var(--theme-text-primary, #0f172a);
  font-size: 18px;
  font-weight: 700;
}

.gallery-report-modal__options {
  display: grid;
  gap: 10px;
}

.gallery-report-modal__option {
  display: flex;
  min-height: 44px;
  cursor: pointer;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--theme-border, #cbd5e1);
  border-radius: 8px;
  background: var(--theme-card-bg, #ffffff);
  color: var(--theme-text-primary, #0f172a);
  padding: 10px 12px;
  transition: border-color 0.18s ease, background 0.18s ease;
}

.gallery-report-modal__option:hover,
.gallery-report-modal__option.is-selected {
  border-color: #2563eb;
  background: color-mix(in srgb, #2563eb 8%, var(--theme-card-bg, #ffffff));
}

.gallery-report-modal__radio {
  width: 16px;
  height: 16px;
  accent-color: #2563eb;
}

.gallery-report-modal__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.gallery-report-modal__secondary,
.gallery-report-modal__primary {
  min-height: 40px;
  border-radius: 8px;
  border: none;
  padding: 0 16px;
  font-size: 14px;
  font-weight: 600;
}

.gallery-report-modal__secondary {
  background: var(--theme-pill-bg, #e2e8f0);
  color: var(--theme-text-secondary, #334155);
}

.gallery-report-modal__primary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: #dc2626;
  color: #ffffff;
}

.gallery-report-modal__secondary:disabled,
.gallery-report-modal__primary:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.gallery-report-modal__spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.38);
  border-top-color: #ffffff;
  border-radius: 999px;
  animation: gallery-report-spin 0.8s linear infinite;
}

@keyframes gallery-report-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
