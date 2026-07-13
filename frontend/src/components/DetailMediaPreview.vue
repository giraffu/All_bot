<script setup lang="ts">
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { computed } from 'vue'
import type { MediaDetailView } from '@/utils/mediaCardView'

const props = defineProps<{
  media: MediaDetailView | null
  hasPrev: boolean
  hasNext: boolean
}>()

const emit = defineEmits<{
  prev: []
  next: []
}>()

const posterSrc = computed(() => props.media?.posterSrc || undefined)
</script>

<template>
  <div class="w-full lg:w-2/3 bg-black flex items-center justify-center relative group/media">
    <template v-if="media?.mediaSrc">
      <img
        v-if="!media.isVideo"
        :src="media.mediaSrc"
        class="w-full h-auto max-h-[65vh] object-contain lg:max-w-full lg:max-h-[80vh]"
      />
      <video
        v-else
        :src="media.mediaSrc"
        :poster="posterSrc"
        class="w-full h-auto max-h-[65vh] object-contain lg:max-w-full lg:max-h-[80vh]"
        controls
        autoplay
        loop
        playsinline
      />
    </template>

    <button
      v-if="hasPrev"
      @click.stop="emit('prev')"
      class="absolute left-2 top-1/2 -translate-y-1/2 w-10 h-10 sm:w-12 sm:h-12 bg-black/40 hover:bg-black/60 rounded-full flex items-center justify-center text-white/80 hover:text-white transition-all z-20 border border-white/10 backdrop-blur-sm opacity-100 lg:opacity-0 lg:group-hover/media:opacity-100"
    >
      <ChevronLeft :size="24" />
    </button>
    <button
      v-if="hasNext"
      @click.stop="emit('next')"
      class="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 sm:w-12 sm:h-12 bg-black/40 hover:bg-black/60 rounded-full flex items-center justify-center text-white/80 hover:text-white transition-all z-20 border border-white/10 backdrop-blur-sm opacity-100 lg:opacity-0 lg:group-hover/media:opacity-100"
    >
      <ChevronRight :size="24" />
    </button>
  </div>
</template>
