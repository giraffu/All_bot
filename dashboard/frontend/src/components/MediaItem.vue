<script setup>
import { isVideo } from '../utils/helpers'
import { PlayCircleOutlined } from '@ant-design/icons-vue'

defineProps({
  file: {
    type: String,
    required: true
  },
  url: {
    type: String,
    required: true
  },
  label: {
    type: String,
    default: ''
  },
  size: {
    type: String,
    default: 'w-32 h-32'
  }
})

const openVideo = (url) => {
  if (url) window.open(url, '_blank')
}
</script>

<template>
  <div class="flex flex-col gap-1">
    <span v-if="label" class="text-[10px] text-gray-500 uppercase font-bold">{{ label }}</span>
    <div :class="[size, 'bg-gray-100 rounded-lg overflow-hidden border border-gray-200 relative group shadow-sm']">
      <template v-if="isVideo(file)">
        <video 
          :src="url"
          class="w-full h-full object-cover cursor-pointer"
          @click="openVideo(url)"
          muted
          loop
          onmouseover="this.play()"
          onmouseout="this.pause();this.currentTime=0;"
        ></video>
        <div class="absolute inset-0 flex items-center justify-center pointer-events-none group-hover:opacity-0 transition-opacity bg-black/10">
          <play-circle-outlined class="text-white text-3xl drop-shadow-md" />
        </div>
        <div class="absolute bottom-1 right-1 px-1 bg-black/60 text-white text-[8px] rounded uppercase font-bold pointer-events-none">
          Video
        </div>
      </template>
      <a-image
        v-else
        :src="url" 
        width="100%"
        height="100%"
        class="object-cover w-full h-full"
      />
    </div>
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
