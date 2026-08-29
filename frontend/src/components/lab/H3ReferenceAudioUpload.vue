<script setup lang="ts">
import { AudioOutlined, DeleteOutlined, UploadOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { UploadedReferenceAudio } from '@/composables/lab-workbench/types'

defineProps<{
  item: UploadedReferenceAudio | null
  uploading: boolean
  beforeUpload: (file: File) => Promise<boolean>
}>()

defineEmits<{ remove: [] }>()

const { t } = useI18n()
const promptReminder = computed(() => t(
  'lab.workbench.minimax_h3_reference_audio_prompt_reminder',
  { audioTag: '<Audio 1>' },
))
</script>

<template>
  <section class="h3-reference-audio rounded-xl border border-white/10 bg-black/10 p-3">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="min-w-0">
        <div class="flex items-center gap-2 text-sm font-medium">
          <AudioOutlined />
          <span>{{ $t('lab.workbench.minimax_h3_reference_audio_title') }}</span>
          <span class="text-xs font-normal text-slate-400">{{ $t('lab.workbench.optional') }}</span>
        </div>
        <p class="mt-1 text-xs text-slate-400">
          {{ $t('lab.workbench.minimax_h3_reference_audio_hint') }}
        </p>
      </div>
      <a-upload
        :show-upload-list="false"
        accept="audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a,audio/ogg,audio/opus"
        :before-upload="beforeUpload"
      >
        <a-button size="small" :loading="uploading">
          <template #icon><UploadOutlined /></template>
          {{ item ? $t('lab.workbench.minimax_h3_reference_audio_replace') : $t('lab.workbench.minimax_h3_reference_audio_add') }}
        </a-button>
      </a-upload>
    </div>

    <div v-if="item" class="mt-3 flex flex-col gap-2 rounded-lg border border-white/10 p-2 sm:flex-row sm:items-center">
      <audio class="h-9 min-w-0 flex-1" controls preload="metadata" :src="item.preview" />
      <div class="flex min-w-0 items-center justify-between gap-2 sm:max-w-56">
        <span class="truncate text-xs text-slate-300" :title="item.name">{{ item.name }}</span>
        <a-button type="text" danger size="small" :aria-label="$t('lab.workbench.minimax_h3_reference_audio_remove')" @click="$emit('remove')">
          <template #icon><DeleteOutlined /></template>
        </a-button>
      </div>
    </div>

    <a-alert
      v-if="item"
      class="mt-3"
      type="info"
      show-icon
      :message="promptReminder"
    />
  </section>
</template>
