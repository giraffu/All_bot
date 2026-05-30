<script setup lang="ts">
import type { LtxVideoLoraItem } from '@/features/generation/imageToVideo'
import {
  IMAGE_TO_VIDEO_LORA_OPTIONS,
  LTX_VIDEO_LORA_OPTIONS,
} from '@/features/generation/imageToVideo'
import { warnIfPropsExceedBudget } from '@/utils/componentPropsBudget'

const props = defineProps<{
  showActionSection: boolean
  isUnifiedImageToVideo: boolean
  isLtxVideo: boolean
  prompt: string
  loraSelection: string
  selectedLtxLoraNames: string[]
  ltxLoraItems: LtxVideoLoraItem[]
  expandedLtxLoraEditors: string[]
}>()

warnIfPropsExceedBudget('TemplateApplyLoraPromptSection', Object.keys(props).length)

const emit = defineEmits<{
  'update:prompt': [value: string]
  'update:loraSelection': [value: string]
  syncLtxLoraItems: [value: string[]]
  toggleLtxLoraStrengthEditor: [name: string]
  removeLtxLoraItem: [name: string]
  updateLtxLoraStrength: [name: string, value: number | null]
}>()
</script>

<template>
  <div v-if="showActionSection" class="rounded-xl border border-slate-700 bg-slate-800/70 p-4">
    <div class="text-sm font-semibold text-slate-200 mb-3">
      {{ isUnifiedImageToVideo ? $t('template_apply.image_to_video.action_and_model') : $t('template_apply.image_to_video.desc_and_params') }}
    </div>
    <div v-if="isUnifiedImageToVideo && !isLtxVideo" class="mb-3">
      <a-select
        :value="loraSelection"
        :placeholder="$t('template_apply.image_to_video.select_addon')"
        class="w-full"
        @update:value="emit('update:loraSelection', String($event ?? ''))"
      >
        <a-select-option
          v-for="option in IMAGE_TO_VIDEO_LORA_OPTIONS"
          :key="option.value"
          :value="option.value"
        >
          {{ option.label }}
        </a-select-option>
      </a-select>
    </div>

    <div v-else-if="isLtxVideo" class="mb-4 space-y-3">
      <a-select
        :value="selectedLtxLoraNames"
        mode="multiple"
        placeholder="选择要叠加的附加模型"
        class="w-full"
        :max-tag-count="2"
        :max-tag-placeholder="(omittedValues: Array<{ label: string; value: string }>) => `+${omittedValues.length}`"
        @change="emit('syncLtxLoraItems', $event as string[])"
      >
        <a-select-option
          v-for="option in LTX_VIDEO_LORA_OPTIONS.filter(item => item.value !== '__none__')"
          :key="option.value"
          :value="option.value"
        >
          {{ option.label }}
        </a-select-option>
      </a-select>
      <p class="text-xs text-slate-400">最多可叠加 3 个附加模型，每个模型可单独调整强度。</p>

      <div v-if="ltxLoraItems.length > 0" class="space-y-3">
        <div
          v-for="item in ltxLoraItems"
          :key="item.name"
          class="rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-3"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="text-sm text-slate-100">
              {{ LTX_VIDEO_LORA_OPTIONS.find(option => option.value === item.name)?.label ?? item.name }}
            </div>
            <div class="flex items-center gap-2">
              <span class="text-xs text-slate-400">默认/当前强度：{{ item.strength.toFixed(2) }}</span>
              <a-button size="small" @click="emit('toggleLtxLoraStrengthEditor', item.name)">
                {{ expandedLtxLoraEditors.includes(item.name) ? '收起设置' : '设置强度' }}
              </a-button>
              <a-button size="small" danger ghost @click="emit('removeLtxLoraItem', item.name)">移除</a-button>
            </div>
          </div>
          <div v-if="expandedLtxLoraEditors.includes(item.name)" class="mt-3 flex items-center gap-3">
            <a-slider
              :min="0.1"
              :max="2"
              :step="0.05"
              :value="item.strength"
              class="flex-1"
              @update:value="emit('updateLtxLoraStrength', item.name, $event as number)"
            />
            <a-input-number
              :min="0.1"
              :max="2"
              :step="0.05"
              :value="item.strength"
              size="small"
              @update:value="emit('updateLtxLoraStrength', item.name, $event as number | null)"
            />
          </div>
        </div>
      </div>
    </div>

    <a-textarea
      :value="prompt"
      :rows="6"
      :placeholder="isUnifiedImageToVideo ? $t('template_apply.image_to_video.prompt_placeholder_video_lora') : $t('template_apply.image_to_video.prompt_placeholder_custom')"
      @update:value="emit('update:prompt', String($event ?? ''))"
    />
  </div>
</template>
