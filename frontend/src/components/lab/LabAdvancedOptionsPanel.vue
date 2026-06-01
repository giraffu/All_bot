<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { LabModeConfig } from '@/features/generation/labModeConfig'

type OptionItem = {
  value: string
  label: string
}

const props = defineProps<{
  mode: LabModeConfig
  editLoraOptions: readonly OptionItem[]
  selectedEditLora: string
  editLoraStrength: number
  videoLoraOptions: readonly OptionItem[]
  selectedVideoLora: string
  resolutionOptions: readonly OptionItem[]
  selectedResolution: string
  durationOptions: readonly OptionItem[]
  selectedDuration: string
  isTemplateEditSettingsLocked: boolean
  isTemplateVideoSettingsLocked: boolean
}>()

const emit = defineEmits<{
  'update:selectedEditLora': [value: string]
  'update:editLoraStrength': [value: number]
  'update:selectedVideoLora': [value: string]
  'update:selectedResolution': [value: string]
  'update:selectedDuration': [value: string]
}>()

const { t } = useI18n()

const hasOptions = computed(() => props.mode.supportsAdvancedOptions)
</script>

<template>
  <div class="lab-advanced-panel rounded-3xl border p-4 sm:p-5">
    <div class="mb-4 flex items-center justify-between gap-3">
      <div>
        <div class="text-sm font-semibold">{{ t('lab.workbench.advanced_title') }}</div>
        <div class="mt-1 text-xs opacity-75">{{ t('lab.workbench.advanced_subtitle') }}</div>
      </div>
    </div>

    <div v-if="!hasOptions" class="text-sm opacity-80">
      {{ t('lab.workbench.no_advanced_options') }}
    </div>

    <div v-else class="space-y-5">
      <div v-if="mode.supportsEditLora" class="space-y-3">
        <div class="text-xs font-semibold uppercase tracking-[0.18em] opacity-70">
          {{ t('template_apply.common.addon_model') }}
        </div>
        <a-radio-group
          :value="selectedEditLora"
          button-style="solid"
          class="lab-advanced-panel__radio-group"
          :disabled="isTemplateEditSettingsLocked"
          @update:value="emit('update:selectedEditLora', $event as string)"
        >
          <a-radio-button
            v-for="option in editLoraOptions"
            :key="option.value"
            :value="option.value"
            class="lab-advanced-panel__radio-button"
          >
            {{ option.label }}
          </a-radio-button>
        </a-radio-group>

        <div v-if="selectedEditLora" class="space-y-3">
          <div class="flex items-center justify-between gap-3 text-xs opacity-75">
            <span>{{ t('template_apply.common.model_strength') }}</span>
            <span>{{ editLoraStrength.toFixed(2) }}</span>
          </div>
          <div class="flex items-center gap-3">
            <a-slider
              :value="editLoraStrength"
              :min="0.1"
              :max="2"
              :step="0.05"
              class="flex-1"
              :disabled="isTemplateEditSettingsLocked"
              @update:value="emit('update:editLoraStrength', Number($event))"
            />
            <a-input-number
              :value="editLoraStrength"
              :min="0.1"
              :max="2"
              :step="0.05"
              size="small"
              class="w-24"
              :disabled="isTemplateEditSettingsLocked"
              @update:value="emit('update:editLoraStrength', Number($event))"
            />
          </div>
        </div>
      </div>

      <div v-if="mode.supportsVideoOptions" class="space-y-5">
        <div class="space-y-3">
          <div class="text-xs font-semibold uppercase tracking-[0.18em] opacity-70">
            {{ t('template_apply.common.addon_model') }}
          </div>
          <a-select
            :value="selectedVideoLora"
            class="w-full"
            :disabled="isTemplateVideoSettingsLocked"
            popup-class-name="app-theme-overlay"
            @update:value="emit('update:selectedVideoLora', String($event))"
          >
            <a-select-option
              v-for="option in videoLoraOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </a-select-option>
          </a-select>
        </div>

        <div class="space-y-3">
          <div class="text-xs font-semibold uppercase tracking-[0.18em] opacity-70">
            {{ t('template_apply.common.resolution') }}
          </div>
          <a-radio-group
            :value="selectedResolution"
            button-style="solid"
            class="lab-advanced-panel__radio-group"
            :disabled="isTemplateVideoSettingsLocked"
            @update:value="emit('update:selectedResolution', $event as string)"
          >
            <a-radio-button
              v-for="option in resolutionOptions"
              :key="option.value"
              :value="option.value"
              class="lab-advanced-panel__radio-button"
              :disabled="option.value === '1024' && selectedDuration === '10'"
            >
              {{ option.label }}
            </a-radio-button>
          </a-radio-group>
        </div>

        <div class="space-y-3">
          <div class="text-xs font-semibold uppercase tracking-[0.18em] opacity-70">
            {{ t('template_apply.common.duration') }}
          </div>
          <a-radio-group
            :value="selectedDuration"
            button-style="solid"
            class="lab-advanced-panel__radio-group"
            :disabled="isTemplateVideoSettingsLocked"
            @update:value="emit('update:selectedDuration', $event as string)"
          >
            <a-radio-button
              v-for="option in durationOptions"
              :key="option.value"
              :value="option.value"
              class="lab-advanced-panel__radio-button"
              :disabled="option.value === '10' && selectedResolution === '1024'"
            >
              {{ option.label }}
            </a-radio-button>
          </a-radio-group>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lab-advanced-panel {
  background: var(--theme-card-bg);
  border-color: var(--theme-border);
  color: var(--theme-text-primary);
}

.lab-advanced-panel__radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

:deep(.lab-advanced-panel__radio-button.ant-radio-button-wrapper) {
  border-radius: 999px !important;
  border-left-width: 1px !important;
  border-color: var(--theme-border) !important;
  background: var(--theme-pill-bg) !important;
  color: var(--theme-text-secondary) !important;
}

:deep(.lab-advanced-panel__radio-button.ant-radio-button-wrapper-checked:not(.ant-radio-button-wrapper-disabled)) {
  border-color: rgba(56, 189, 248, 0.3) !important;
  background: rgba(14, 165, 233, 0.12) !important;
  color: var(--theme-text-primary) !important;
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.1) inset;
}

:deep(.lab-advanced-panel__radio-button.ant-radio-button-wrapper::before) {
  display: none !important;
}

:deep(.ant-select-selector),
:deep(.ant-input-number),
:deep(.ant-input-number-input) {
  background: var(--theme-card-strong-bg) !important;
  border-color: var(--theme-border) !important;
  color: var(--theme-text-primary) !important;
}
</style>
