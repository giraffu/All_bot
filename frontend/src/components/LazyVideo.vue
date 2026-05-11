<template>
  <video
    ref="videoRef"
    :class="className"
    :poster="poster"
    preload="none"
    muted
    loop
    playsinline
    @mouseenter="playVideo"
    @mouseleave="pauseVideo"
  ></video>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  src: string
  poster?: string
  className?: string | object | any[]
}>()

const videoRef = ref<HTMLVideoElement | null>(null)
const isLoaded = ref(false)

const playVideo = (e: Event) => {
  const v = e.target as HTMLVideoElement
  if (!isLoaded.value && v.src !== props.src) {
    v.src = props.src
    isLoaded.value = true
  }
  v.play().catch(() => {})
}

const pauseVideo = (e: Event) => {
  const v = e.target as HTMLVideoElement
  v.pause()
}

watch(() => props.src, (newSrc) => {
  if (isLoaded.value && videoRef.value) {
    videoRef.value.src = newSrc
  }
})
</script>
