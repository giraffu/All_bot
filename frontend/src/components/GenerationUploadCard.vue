<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    title: string
    step?: string
    fileList?: any[]
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
    beforeUpload?: (file: any) => boolean | Promise<boolean>
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
      'text-sm font-bold mb-2 text-slate-200 flex items-center shrink-0',
    previewClass:
      'relative group rounded-xl overflow-hidden border border-slate-400/50 bg-slate-500/50 flex items-center justify-center flex-grow w-full',
    draggerClass: 'upload-dragger flex-grow flex items-center justify-center w-full',
    overlayButtonText: '重新上传',
    uploadText: '点击/拖拽',
    uploadHint: 'JPG/PNG',
    showUploadList: false,
    beforeUpload: undefined,
  },
)

const emit = defineEmits<{
  'update:fileList': [files: any[]]
  remove: []
}>()
</script>

<template>
  <div :class="wrapperClass">
    <h3 :class="titleClass">
      <span v-if="step" class="text-slate-500 mr-2">{{ step }}</span>
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

      <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
        <a-button
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
