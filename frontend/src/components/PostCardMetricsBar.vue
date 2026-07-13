<script setup lang="ts">
import { Heart, MessageCircle, ThumbsDown, Wand2 } from 'lucide-vue-next'

withDefaults(
  defineProps<{
    likesCount: number
    dislikesCount: number
    appliedCount: number
    commentsCount?: number | null
    hasLiked?: boolean
    hasDisliked?: boolean
    showComments?: boolean
    wrapperClass?: string
  }>(),
  {
    commentsCount: null,
    hasLiked: false,
    hasDisliked: false,
    showComments: false,
    wrapperClass:
      'absolute bottom-0 left-0 right-0 p-3 bg-black/60 backdrop-blur-md border-t border-white/10 flex justify-between items-center z-10 translate-y-0',
  },
)

const emit = defineEmits<{
  like: []
  dislike: []
  comment: []
}>()
</script>

<template>
  <div :class="wrapperClass">
    <div class="flex items-center space-x-3">
      <button
        type="button"
        class="flex items-center text-slate-300 hover:text-pink-400 transition-colors"
        @click.stop="emit('like')"
      >
        <Heart
          :size="14"
          class="mr-1"
          :class="{ 'fill-pink-500 text-pink-500': hasLiked }"
        />
        <span class="text-xs font-medium">{{ likesCount }}</span>
      </button>
      <button
        type="button"
        class="flex items-center text-slate-300 hover:text-slate-100 transition-colors"
        @click.stop="emit('dislike')"
      >
        <ThumbsDown
          :size="14"
          class="mr-1"
          :class="{ 'fill-slate-400 text-slate-400': hasDisliked }"
        />
        <span class="text-xs font-medium">{{ dislikesCount }}</span>
      </button>
      <button
        v-if="showComments"
        type="button"
        class="flex items-center text-slate-300 hover:text-blue-400 transition-colors"
        @click.stop="emit('comment')"
      >
        <MessageCircle :size="14" class="mr-1" />
        <span class="text-xs font-medium">{{ commentsCount ?? 0 }}</span>
      </button>
    </div>
    <div class="flex items-center text-indigo-300">
      <Wand2 :size="14" class="mr-1" />
      <span class="text-xs font-medium">{{ appliedCount }}</span>
    </div>
  </div>
</template>
