<script setup lang="ts">
import { DeleteOutlined, UploadOutlined, VideoCameraOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { UploadedReferenceVideo } from '@/composables/lab-workbench/types'

defineProps<{
  item: UploadedReferenceVideo | null
  uploading: boolean
  beforeUpload: (file: File) => Promise<boolean>
}>()

defineEmits<{ remove: [] }>()

const { t } = useI18n()
const promptReminder = computed(() => t(
  'lab.workbench.minimax_h3_reference_video_prompt_reminder',
  { videoTag: '<Video 1>' },
))
</script>

<template>
  <section class="h3-reference-video rounded-xl border border-white/10 bg-black/10 p-3">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="min-w-0">
        <div class="flex items-center gap-2 text-sm font-medium">
          <VideoCameraOutlined />
          <span>{{ $t('lab.workbench.minimax_h3_reference_video_title') }}</span>
          <span class="text-xs font-normal text-slate-400">{{ $t('lab.workbench.optional') }}</span>
        </div>
        <p class="mt-1 text-xs text-slate-400">
          {{ $t('lab.workbench.minimax_h3_reference_video_hint') }}
        </p>
      </div>
      <a-upload
        :show-upload-list="false"
        accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
        :before-upload="beforeUpload"
      >
        <a-button size="small" :loading="uploading">
          <template #icon><UploadOutlined /></template>
          {{ item ? $t('lab.workbench.minimax_h3_reference_video_replace') : $t('lab.workbench.minimax_h3_reference_video_add') }}
        </a-button>
      </a-upload>
    </div>

    <div v-if="item" class="mt-3 flex flex-col gap-2 rounded-lg border border-white/10 p-2 sm:flex-row sm:items-center">
      <video class="max-h-44 min-w-0 flex-1 rounded-lg bg-black" controls preload="metadata" :src="item.preview" />
      <div class="flex min-w-0 items-center justify-between gap-2 sm:max-w-56">
        <span class="truncate text-xs text-slate-300" :title="item.name">{{ item.name }}</span>
        <a-button type="text" danger size="small" :aria-label="$t('lab.workbench.minimax_h3_reference_video_remove')" @click="$emit('remove')">
          <template #icon><DeleteOutlined /></template>
        </a-button>
      </div>
    </div>

    <a-alert v-if="item" class="mt-3" type="info" show-icon :message="promptReminder" />
  </section>
</template>
