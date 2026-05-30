<script setup lang="ts">
import { warnIfPropsExceedBudget } from '@/utils/componentPropsBudget'

const props = defineProps<{
  showOutputSettingsSection: boolean
  isLtxVideo: boolean
  resolution: string
  duration: string
}>()

warnIfPropsExceedBudget('TemplateApplyOutputSettingsSection', Object.keys(props).length)

const emit = defineEmits<{
  'update:resolution': [value: string]
  'update:duration': [value: string]
}>()
</script>

<template>
  <div v-if="showOutputSettingsSection" class="rounded-xl border border-slate-700 bg-slate-800/70 p-4">
    <div class="text-sm font-semibold text-slate-200 mb-3">{{ $t('template_apply.common.output_settings') }}</div>
    <div class="space-y-4">
      <div>
        <label class="block text-xs font-medium text-slate-300 mb-2">{{ $t('template_apply.common.resolution') }}</label>
        <a-radio-group
          v-if="isLtxVideo"
          :value="resolution"
          button-style="solid"
          class="w-full grid grid-cols-1 gap-2 max-w-[180px]"
          @update:value="emit('update:resolution', String($event ?? ''))"
        >
          <a-radio-button value="1280x704" class="w-full text-center">1280x704</a-radio-button>
        </a-radio-group>
        <a-radio-group
          v-else
          :value="resolution"
          button-style="solid"
          class="w-full grid grid-cols-3 gap-2"
          @update:value="emit('update:resolution', String($event ?? ''))"
        >
          <a-radio-button value="512" class="w-full text-center">512p</a-radio-button>
          <a-radio-button value="720" class="w-full text-center">720p</a-radio-button>
          <a-radio-button value="1024" class="w-full text-center" :disabled="duration === '10'">1024p</a-radio-button>
        </a-radio-group>
      </div>

      <div>
        <label class="block text-xs font-medium text-slate-300 mb-2">{{ $t('template_apply.common.duration') }}</label>
        <a-radio-group
          v-if="isLtxVideo"
          :value="duration"
          button-style="solid"
          class="w-full grid grid-cols-4 gap-2 max-w-[320px]"
          @update:value="emit('update:duration', String($event ?? ''))"
        >
          <a-radio-button value="5" class="w-full text-center">5 {{ $t('template_apply.common.seconds') }}</a-radio-button>
          <a-radio-button value="10" class="w-full text-center">10 {{ $t('template_apply.common.seconds') }}</a-radio-button>
          <a-radio-button value="15" class="w-full text-center">15 {{ $t('template_apply.common.seconds') }}</a-radio-button>
          <a-radio-button value="20" class="w-full text-center">20 {{ $t('template_apply.common.seconds') }}</a-radio-button>
        </a-radio-group>
        <a-radio-group
          v-else
          :value="duration"
          button-style="solid"
          class="w-full grid grid-cols-3 gap-2 max-w-[240px]"
          @update:value="emit('update:duration', String($event ?? ''))"
        >
          <a-radio-button value="5" class="w-full text-center">5 {{ $t('template_apply.common.seconds') }}</a-radio-button>
          <a-radio-button value="8" class="w-full text-center">8 {{ $t('template_apply.common.seconds') }}</a-radio-button>
          <a-radio-button value="10" class="w-full text-center" :disabled="resolution === '1024'">10 {{ $t('template_apply.common.seconds') }}</a-radio-button>
        </a-radio-group>
      </div>
    </div>
  </div>
</template>

<style scoped>
:deep(.ant-radio-button-wrapper) {
  background: rgba(15, 23, 42, 0.6);
  color: #cbd5e1;
  border-color: rgba(71, 85, 105, 0.9);
}

:deep(.ant-radio-button-wrapper-checked:not(.ant-radio-button-wrapper-disabled)) {
  background: rgba(34, 211, 238, 0.2);
  color: #67e8f9;
  border-color: rgba(34, 211, 238, 0.8);
}
</style>
