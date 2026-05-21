<script setup lang="ts">
import { Image as ImageIcon, Play, Video } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    item: any
    mediaContainerStyle?: Record<string, string>
    mediaContainerClass?: string
    imageClass?: string
    overlayVisibilityClass?: string
  }>(),
  {
    mediaContainerStyle: () => ({ aspectRatio: '1/1' }),
    mediaContainerClass: 'relative w-full overflow-hidden bg-slate-500',
    imageClass: 'w-full h-full object-cover transition-opacity duration-300 absolute inset-0',
    overlayVisibilityClass:
      'opacity-0 group-hover:opacity-100 transition-opacity duration-300',
  },
)

const emit = defineEmits<{
  cardClick: []
  imageError: [event: Event]
}>()
</script>

<template>
  <div
    class="rounded-2xl overflow-hidden relative group cursor-pointer border border-slate-400/50 bg-slate-500/40 hover:border-cyan-500/40 transition-all duration-300 shadow-lg hover:shadow-[0_8px_30px_rgba(56,189,248,0.15)] hover:-translate-y-1"
    @click="emit('cardClick')"
  >
    <div :class="mediaContainerClass" :style="mediaContainerStyle">
      <slot name="media" :item="item">
        <img
          v-if="item.src"
          :src="item.src"
          :class="imageClass"
          loading="lazy"
          @error="emit('imageError', $event)"
        />
        <div v-else class="absolute inset-0 flex items-center justify-center text-slate-400">
          <ImageIcon v-if="!item.cardIsVideo" :size="24" />
          <Video v-else :size="24" />
        </div>
      </slot>

      <slot name="top-left" :item="item" />

      <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-sm rounded-full p-1.5 shadow-sm border border-white/10">
        <slot name="top-right" :item="item">
          <ImageIcon v-if="!item.cardIsVideo" :size="14" class="text-cyan-400" />
          <Video v-else :size="14" class="text-indigo-400" />
        </slot>
      </div>

      <div
        v-if="item.cardIsVideo"
        class="absolute inset-0 flex items-center justify-center pointer-events-none opacity-80 group-hover:opacity-0 transition-opacity duration-300"
      >
        <slot name="play-overlay" :item="item">
          <div class="w-12 h-12 bg-black/50 backdrop-blur-md rounded-full flex items-center justify-center border border-white/20 shadow-lg">
            <Play :size="24" class="text-white ml-1" />
          </div>
        </slot>
      </div>

      <div
        class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent flex flex-col p-4"
        :class="overlayVisibilityClass"
      >
        <slot name="overlay" :item="item" />
      </div>
    </div>

    <slot name="bottom" :item="item" />
  </div>
</template>
