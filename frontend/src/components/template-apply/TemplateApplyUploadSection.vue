<script setup lang="ts">
import { CloseCircleOutlined, InboxOutlined } from '@ant-design/icons-vue'
import { warnIfPropsExceedBudget } from '@/utils/componentPropsBudget'

const props = defineProps<{
  filePreview: string | null
  uploadingSlots: Record<string, boolean>
  progressBySlot: Record<string, number>
  beforeUpload: (rawFile: File | { originFileObj?: File }) => Promise<boolean> | boolean
}>()

warnIfPropsExceedBudget('TemplateApplyUploadSection', Object.keys(props).length)

const emit = defineEmits<{
  remove: []
}>()
</script>

<template>
  <div class="rounded-xl border border-slate-700 bg-slate-800/70 p-4">
    <div class="text-sm font-semibold text-slate-200 mb-3">{{ $t('template_apply.common.base_image') }}</div>
    <div v-if="filePreview" class="relative rounded-xl overflow-hidden border border-slate-700 bg-slate-950/80">
      <img :src="filePreview" class="h-56 w-full object-contain bg-slate-950/80" />
      <button
        class="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-full bg-black/55 text-white"
        @click="emit('remove')"
      >
        <CloseCircleOutlined />
      </button>
    </div>
    <a-upload-dragger
      v-else
      :before-upload="beforeUpload"
      :show-upload-list="false"
      accept="image/*"
      class="template-upload"
    >
      <p class="ant-upload-drag-icon">
        <InboxOutlined class="text-cyan-400" />
      </p>
      <p class="text-slate-200">{{ $t('template_apply.common.upload_base_image') }}</p>
      <p class="text-slate-400 text-xs">{{ $t('template_apply.common.continue_after_close') }}</p>
    </a-upload-dragger>
  </div>

  <div
    v-if="Object.values(uploadingSlots).some(Boolean)"
    class="mt-4 space-y-2"
  >
    <div
      v-for="(progress, slot) in progressBySlot"
      :key="slot"
      v-show="uploadingSlots[slot]"
      class="rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-2"
    >
      <div class="flex items-center justify-between text-xs text-slate-300 mb-1">
        <span>{{ slot }}</span>
        <span>{{ progress }}%</span>
      </div>
      <a-progress :percent="progress" size="small" />
    </div>
  </div>
</template>

<style scoped>
.template-upload :deep(.ant-upload.ant-upload-drag) {
  background: rgba(15, 23, 42, 0.75);
  border-color: rgba(71, 85, 105, 0.9);
}

.template-upload :deep(.ant-upload.ant-upload-drag:hover) {
  border-color: rgba(34, 211, 238, 0.8);
}
</style>
