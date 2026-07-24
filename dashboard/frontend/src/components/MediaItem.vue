<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { isVideo } from '../utils/helpers'
import { PlayCircleOutlined } from '@ant-design/icons-vue'

interface Props {
  file: string
  url: string
  previewUrl?: string
  label?: string
  size?: string
}

const props = withDefaults(defineProps<Props>(), {
  previewUrl: '',
  label: '',
  size: 'w-32 h-32',
})

const videoOpen = ref(false)
const previewFailed = ref(false)
const videoFile = computed(() => isVideo(props.file))
const displayImageUrl = computed(() =>
  props.previewUrl && !previewFailed.value ? props.previewUrl : props.url,
)

watch(
  () => props.previewUrl,
  () => {
    previewFailed.value = false
  },
)

const openVideo = () => {
  if (props.url) {
    videoOpen.value = true
  }
}

const markPreviewFailed = () => {
  previewFailed.value = true
}
</script>

<template>
  <div class="flex flex-col gap-1">
    <span v-if="label" class="text-[10px] text-gray-500 uppercase font-bold">{{ label }}</span>
    <div :class="[size, 'bg-gray-100 rounded-lg overflow-hidden border border-gray-200 relative group shadow-sm']">
      <button
        v-if="videoFile"
        type="button"
        data-testid="media-video-trigger"
        class="w-full h-full border-0 p-0 bg-gray-900 cursor-pointer relative"
        aria-label="打开视频预览"
        @click="openVideo"
      >
        <img
          v-if="previewUrl && !previewFailed"
          data-testid="media-video-thumbnail"
          :src="previewUrl"
          alt="视频缩略图"
          loading="lazy"
          decoding="async"
          class="w-full h-full object-cover"
          @error="markPreviewFailed"
        />
        <div v-else class="w-full h-full bg-gradient-to-br from-slate-700 to-slate-950"></div>
        <div class="absolute inset-0 flex items-center justify-center pointer-events-none group-hover:opacity-0 transition-opacity bg-black/10">
          <play-circle-outlined class="text-white text-3xl drop-shadow-md" />
        </div>
        <div class="absolute bottom-1 right-1 px-1 bg-black/60 text-white text-[8px] rounded uppercase font-bold pointer-events-none">
          Video
        </div>
      </button>
      <a-image
        v-else
        :src="displayImageUrl"
        :preview="{ src: url }"
        loading="lazy"
        decoding="async"
        width="100%"
        height="100%"
        class="object-cover w-full h-full"
        @error="markPreviewFailed"
      />
    </div>

    <a-modal
      v-model:open="videoOpen"
      data-testid="media-video-modal"
      :title="file"
      :footer="null"
      width="min(920px, 92vw)"
      centered
      destroy-on-close
    >
      <video
        v-if="videoOpen"
        :src="url"
        class="w-full max-h-[78vh] rounded-lg bg-black"
        controls
        autoplay
        preload="metadata"
        playsinline
      ></video>
    </a-modal>
  </div>
</template>

<style scoped>
:deep(.ant-image) {
  display: block;
  width: 100%;
  height: 100%;
}
:deep(.ant-image-img) {
  object-fit: cover;
  width: 100%;
  height: 100%;
}
</style>
