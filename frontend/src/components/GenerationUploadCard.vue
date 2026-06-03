<script setup lang="ts">
import type { UploadFileLike } from '@/types/upload'

const props = withDefaults(
  defineProps<{
    title: string
    step?: string
    fileList?: UploadFileLike[]
    previewUrl?: string | null
    previewKind?: 'image' | 'video'
    name?: string
    accept?: string
    multiple?: boolean
    wrapperClass?: string
    titleClass?: string
    previewClass?: string
    draggerClass?: string
    overlayButtonText?: string
    uploadText?: string
    uploadHint?: string
    showUploadList?: boolean
    disabled?: boolean
    locked?: boolean
    lockedText?: string
    beforeUpload?: (file: File) => boolean | Promise<boolean>
  }>(),
  {
    step: '',
    fileList: () => [],
    previewUrl: null,
    previewKind: 'image',
    name: 'file',
    accept: 'image/png, image/jpeg',
    multiple: false,
    wrapperClass:
      'upload-section flex flex-col w-full min-w-[160px] shrink-0 h-48 md:h-full',
    titleClass:
      'generation-upload-card__title text-sm font-bold mb-2 flex items-center shrink-0',
    previewClass:
      'generation-upload-card__preview relative group rounded-xl overflow-hidden flex items-center justify-center flex-grow w-full',
    draggerClass: 'upload-dragger flex-grow flex items-center justify-center w-full',
    overlayButtonText: '重新上传',
    uploadText: '点击/拖拽',
    uploadHint: 'JPG/PNG',
    showUploadList: false,
    disabled: false,
    locked: false,
    lockedText: '已锁定',
    beforeUpload: undefined,
  },
)

const emit = defineEmits<{
  'update:fileList': [files: UploadFileLike[]]
  remove: []
}>()
</script>

<template>
  <div :class="wrapperClass">
    <h3 :class="titleClass">
      <span v-if="step" class="generation-upload-card__step mr-2">{{ step }}</span>
      {{ title }}
    </h3>

    <div v-if="previewUrl" :class="previewClass">
      <slot name="preview">
        <a-image
          v-if="previewKind === 'image'"
          :src="previewUrl"
          class="max-w-full max-h-full object-contain"
          :preview="true"
        />
        <video
          v-else
          :src="previewUrl"
          class="max-w-full max-h-full bg-black object-contain"
          controls
        />
      </slot>

      <div
        class="absolute inset-0 bg-black/60 transition-opacity flex items-center justify-center pointer-events-none"
        :class="props.locked ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'"
      >
        <span
          v-if="props.locked"
          class="generation-upload-card__locked-badge px-3 py-1 rounded-full text-xs font-medium"
        >
          {{ props.lockedText }}
        </span>
        <a-button
          v-else
          danger
          type="primary"
          class="pointer-events-auto"
          size="small"
          @click="emit('remove')"
        >
          {{ overlayButtonText }}
        </a-button>
      </div>
    </div>

    <a-upload-dragger
      v-else
      :file-list="fileList"
      :name="name"
      :multiple="multiple"
      :accept="accept"
      :disabled="disabled"
      :before-upload="beforeUpload"
      :show-upload-list="showUploadList"
      :class="draggerClass"
      @update:fileList="emit('update:fileList', $event)"
      @remove="emit('remove')"
    >
      <slot name="placeholder">
        <div class="flex flex-col items-center justify-center h-full w-full p-4">
          <p class="ant-upload-drag-icon text-blue-500 text-3xl mb-2">
            <slot name="placeholder-icon" />
          </p>
          <p class="ant-upload-text font-medium text-slate-300 text-sm">
            {{ uploadText }}
          </p>
          <p class="ant-upload-hint text-slate-500 mt-1 text-xs">
            {{ uploadHint }}
          </p>
        </div>
      </slot>
    </a-upload-dragger>
  </div>
</template>

<style scoped>
.generation-upload-card__title {
  color: var(--theme-text-primary);
}

.generation-upload-card__step {
  color: var(--theme-text-secondary);
}

.generation-upload-card__preview {
  border: 1px solid var(--theme-border);
  background: var(--theme-card-strong-bg);
}

.generation-upload-card__locked-badge {
  color: #ecfeff;
  background: color-mix(in srgb, #0891b2 70%, black 30%);
  border: 1px solid color-mix(in srgb, #67e8f9 55%, transparent);
}

:deep(.ant-upload.ant-upload-drag) {
  background: var(--theme-card-strong-bg) !important;
  border-color: var(--theme-border) !important;
}

:deep(.ant-upload.ant-upload-drag.ant-upload-disabled) {
  cursor: not-allowed !important;
  opacity: 0.75;
}

:deep(.ant-upload.ant-upload-drag:hover) {
  border-color: var(--theme-border-strong) !important;
}

:deep(.ant-upload.ant-upload-drag .ant-upload-text) {
  color: var(--theme-text-primary) !important;
}

:deep(.ant-upload.ant-upload-drag .ant-upload-hint) {
  color: var(--theme-text-secondary) !important;
}
</style>
