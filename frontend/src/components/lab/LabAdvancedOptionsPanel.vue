<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { LabModeConfig } from '@/features/generation/labModeConfig'

type OptionItem = {
  value: string
  label: string
}

type LtxVideoLoraItem = {
  name: string
  strength: number
}

type Wan22ResolutionOption = OptionItem & {
  description: string
  cost: number
}

const props = defineProps<{
  mode: LabModeConfig
  editLoraOptions: readonly OptionItem[]
  selectedEditLora: string
  editLoraStrength: number
  videoLoraOptions: readonly OptionItem[]
  selectedVideoLora: string
  ltxLoraOptions: readonly OptionItem[]
  selectedLtxLoraNames: string[]
  ltxLoraItems: LtxVideoLoraItem[]
  resolutionOptions: readonly OptionItem[]
  selectedResolution: string
  durationOptions: readonly OptionItem[]
  selectedDuration: string
  negativePrompt: string
  wan22ResolutionOptions: readonly Wan22ResolutionOption[]
  selectedWan22ResolutionPreset: string
  isTemplateEditSettingsLocked: boolean
  isTemplateVideoSettingsLocked: boolean
}>()

const emit = defineEmits<{
  'update:selectedEditLora': [value: string]
  'update:editLoraStrength': [value: number]
  'update:selectedVideoLora': [value: string]
  'update:selectedLtxLoraNames': [value: string[]]
  'update:ltxLoraStrength': [name: string, value: number]
  removeLtxLoraItem: [name: string]
  'update:selectedResolution': [value: string]
  'update:selectedDuration': [value: string]
  'update:negativePrompt': [value: string]
  'update:selectedWan22ResolutionPreset': [value: string]
}>()

const { t } = useI18n()

const hasOptions = computed(() => props.mode.supportsAdvancedOptions)
const showVideoLoraOptions = computed(() => props.mode.supportsVideoOptions && props.mode.supportsVideoLora !== false)
const showLtxLoraItems = computed(() => props.mode.supportsLtxLoraItems)
const showDurationOptions = computed(() => props.mode.supportsVideoOptions && props.mode.supportsDurationOptions !== false)
const showStandardResolutionOptions = computed(() => (
  props.mode.supportsVideoOptions
  && props.mode.supportsResolutionOptions !== false
  && !props.mode.supportsWan22ResolutionPreset
))
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
        <div v-if="showLtxLoraItems" class="lab-advanced-panel__ltx-lora space-y-3">
          <div class="text-xs font-semibold uppercase tracking-[0.18em] opacity-70">
            {{ t('template_apply.common.addon_model') }}
          </div>
          <a-select
            :value="selectedLtxLoraNames"
            mode="multiple"
            class="w-full"
            :max-tag-count="2"
            :placeholder="t('lab.workbench.ltx_lora_placeholder')"
            popup-class-name="app-theme-overlay"
            @update:value="emit('update:selectedLtxLoraNames', $event as string[])"
          >
            <a-select-option
              v-for="option in ltxLoraOptions.filter(item => item.value !== '__none__')"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </a-select-option>
          </a-select>
          <div class="text-xs opacity-70">{{ t('lab.workbench.ltx_lora_hint') }}</div>

          <div v-if="ltxLoraItems.length > 0" class="lab-advanced-panel__lora-list space-y-3">
            <div
              v-for="item in ltxLoraItems"
              :key="item.name"
              class="lab-advanced-panel__lora-card rounded-2xl border p-3"
            >
              <div class="mb-2 flex items-center justify-between gap-3">
                <div class="min-w-0 truncate text-sm font-medium">
                  {{ ltxLoraOptions.find(option => option.value === item.name)?.label ?? item.name }}
                </div>
                <a-button size="small" danger ghost @click="emit('removeLtxLoraItem', item.name)">
                  {{ t('lab.workbench.remove_asset') }}
                </a-button>
              </div>
              <div class="flex items-center justify-between gap-3 text-xs opacity-75">
                <span>{{ t('template_apply.common.model_strength') }}</span>
                <span>{{ item.strength.toFixed(2) }}</span>
              </div>
              <div class="mt-2 flex items-center gap-3">
                <a-slider
                  :value="item.strength"
                  :min="0.1"
                  :max="2"
                  :step="0.05"
                  class="flex-1"
                  @update:value="emit('update:ltxLoraStrength', item.name, Number($event))"
                />
                <a-input-number
                  :value="item.strength"
                  :min="0.1"
                  :max="2"
                  :step="0.05"
                  size="small"
                  class="w-24"
                  @update:value="emit('update:ltxLoraStrength', item.name, Number($event))"
                />
              </div>
            </div>
          </div>
        </div>

        <div v-if="showVideoLoraOptions" class="space-y-3">
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

        <div v-if="showStandardResolutionOptions" class="space-y-3">
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

        <div v-if="showDurationOptions" class="space-y-3">
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

        <div v-if="mode.supportsWan22ResolutionPreset" class="space-y-3">
          <div class="text-xs font-semibold uppercase tracking-[0.18em] opacity-70">
            {{ t('template_apply.common.resolution') }}
          </div>
          <a-radio-group
            :value="selectedWan22ResolutionPreset"
            class="lab-advanced-panel__preset-grid"
            :disabled="isTemplateVideoSettingsLocked"
            @update:value="emit('update:selectedWan22ResolutionPreset', String($event))"
          >
            <label
              v-for="option in wan22ResolutionOptions"
              :key="option.value"
              class="lab-advanced-panel__preset-card rounded-2xl border p-3"
              :class="{ 'lab-advanced-panel__preset-card--active': selectedWan22ResolutionPreset === option.value }"
            >
              <a-radio :value="option.value">
                <span class="text-sm font-medium">{{ option.label }}</span>
              </a-radio>
              <div class="mt-2 text-xs font-semibold">{{ option.cost }} {{ t('app.credits') }}</div>
              <div class="mt-1 text-xs opacity-70">{{ option.description }}</div>
            </label>
          </a-radio-group>
        </div>

        <div v-if="mode.supportsNegativePrompt" class="space-y-3">
          <div class="text-xs font-semibold uppercase tracking-[0.18em] opacity-70">
            {{ t('lab.workbench.negative_prompt') }}
          </div>
          <a-textarea
            :value="negativePrompt"
            :rows="4"
            :maxlength="2000"
            class="lab-advanced-panel__textarea"
            :placeholder="t('lab.workbench.negative_prompt_placeholder')"
            @update:value="emit('update:negativePrompt', String($event))"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lab-advanced-panel {
  max-height: min(680px, 72vh);
  overflow-y: auto;
  background: var(--theme-card-bg);
  border-color: var(--theme-border);
  color: var(--theme-text-primary);
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.55) transparent;
}

.lab-advanced-panel::-webkit-scrollbar,
.lab-advanced-panel__lora-list::-webkit-scrollbar {
  width: 6px;
}

.lab-advanced-panel::-webkit-scrollbar-thumb,
.lab-advanced-panel__lora-list::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.5);
}

.lab-advanced-panel::-webkit-scrollbar-track,
.lab-advanced-panel__lora-list::-webkit-scrollbar-track {
  background: transparent;
}

.lab-advanced-panel__lora-list {
  max-height: min(360px, 38vh);
  overflow-y: auto;
  padding-right: 4px;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.55) transparent;
}

.lab-advanced-panel__radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.lab-advanced-panel__lora-card,
.lab-advanced-panel__preset-card {
  background: var(--theme-panel-bg);
  border-color: var(--theme-border);
}

.lab-advanced-panel__preset-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.lab-advanced-panel__preset-card {
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.lab-advanced-panel__preset-card--active {
  border-color: rgba(37, 99, 235, 0.7);
  background: color-mix(in srgb, #2563eb 10%, var(--theme-panel-bg));
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
:deep(.ant-input-number-input),
:deep(.lab-advanced-panel__textarea textarea) {
  background: var(--theme-card-strong-bg) !important;
  border-color: var(--theme-border) !important;
  color: var(--theme-text-primary) !important;
}

@media (max-width: 640px) {
  .lab-advanced-panel__preset-grid {
    grid-template-columns: 1fr;
  }
}
</style>
