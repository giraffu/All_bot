<script setup lang="ts">
import { Heart, MessageCircle, ThumbsDown } from 'lucide-vue-next'

withDefaults(
  defineProps<{
    likesCount: number
    dislikesCount: number
    commentsCount: number
    hasLiked?: boolean
    hasDisliked?: boolean
    compact?: boolean
    showCommentCount?: boolean
  }>(),
  {
    hasLiked: false,
    hasDisliked: false,
    compact: false,
    showCommentCount: true,
  },
)

const emit = defineEmits<{
  like: []
  dislike: []
  comment: []
}>()
</script>

<template>
  <div
    v-if="compact"
    class="flex items-center gap-1.5"
  >
    <button
      type="button"
      class="flex items-center gap-1.5 transition-all"
      :class="hasLiked ? 'text-pink-500' : 'text-slate-300'"
      @click="emit('like')"
    >
      <Heart :size="20" :class="{ 'fill-pink-500': hasLiked }" />
      <span class="text-xs font-medium">{{ likesCount }}</span>
    </button>
    <button
      type="button"
      class="flex items-center gap-1.5 transition-all"
      :class="hasDisliked ? 'text-slate-400' : 'text-slate-300'"
      @click="emit('dislike')"
    >
      <ThumbsDown :size="20" :class="{ 'fill-slate-400': hasDisliked }" />
      <span class="text-xs font-medium">{{ dislikesCount }}</span>
    </button>
    <button
      type="button"
      class="flex items-center gap-1.5 transition-all text-slate-300"
      @click="emit('comment')"
    >
      <MessageCircle :size="20" />
      <span
        v-if="showCommentCount"
        class="text-xs font-medium"
      >
        {{ commentsCount }}
      </span>
    </button>
  </div>

  <div
    v-else
    class="flex space-x-2"
  >
    <button
      type="button"
      class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group"
      @click="emit('like')"
    >
      <Heart
        :size="20"
        class="mr-2 transition-transform group-hover:scale-110"
        :class="hasLiked ? 'fill-pink-500 text-pink-500' : 'text-slate-400 group-hover:text-pink-400'"
      />
      <span class="font-medium" :class="hasLiked ? 'text-pink-400' : 'text-slate-300'">{{ likesCount }}</span>
    </button>
    <button
      type="button"
      class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group"
      @click="emit('dislike')"
    >
      <ThumbsDown
        :size="20"
        class="mr-2 transition-transform group-hover:scale-110"
        :class="hasDisliked ? 'fill-slate-400 text-slate-400' : 'text-slate-400 group-hover:text-slate-200'"
      />
      <span class="font-medium" :class="hasDisliked ? 'text-slate-400' : 'text-slate-300'">{{ dislikesCount }}</span>
    </button>
    <button
      type="button"
      class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group"
      @click="emit('comment')"
    >
      <MessageCircle
        :size="20"
        class="mr-2 transition-transform group-hover:scale-110 text-slate-400 group-hover:text-blue-400"
      />
      <span class="font-medium text-slate-300">{{ commentsCount }}</span>
    </button>
  </div>
</template>
