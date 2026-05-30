<script setup lang="ts">
import { VideoCameraOutlined } from '@ant-design/icons-vue'
import { warnIfPropsExceedBudget } from '@/utils/componentPropsBudget'

const props = defineProps<{
  taskCost: number
  isSubmitting: boolean
  hasPendingUploads: boolean
  hasObjectKey: boolean
}>()

warnIfPropsExceedBudget('TemplateApplyActionFooter', Object.keys(props).length)

const emit = defineEmits<{
  generate: []
}>()
</script>

<template>
  <div class="border-t border-slate-700 px-6 py-4 flex items-center justify-between gap-4">
    <div class="text-sm text-slate-300">
      {{ $t('template_apply.common.estimated_cost') }}
      <span class="text-cyan-300 font-semibold">{{ taskCost }}</span>
      {{ $t('template_apply.common.credits_unit') }}
    </div>
    <a-button
      type="primary"
      size="large"
      :loading="isSubmitting"
      :disabled="hasPendingUploads || !hasObjectKey"
      @click="emit('generate')"
    >
      <template #icon>
        <VideoCameraOutlined />
      </template>
      {{ $t('template_apply.common.generate_video') }}
    </a-button>
  </div>
</template>
