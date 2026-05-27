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
    class="detail-reaction-compact flex items-center gap-1.5"
  >
    <button
      type="button"
      class="detail-reaction-compact-button flex items-center gap-1.5 transition-all"
      :class="hasLiked ? 'is-liked' : ''"
      @click="emit('like')"
    >
      <Heart :size="20" :class="{ 'fill-pink-500': hasLiked }" />
      <span class="text-xs font-medium">{{ likesCount }}</span>
    </button>
    <button
      type="button"
      class="detail-reaction-compact-button flex items-center gap-1.5 transition-all"
      :class="hasDisliked ? 'is-disliked' : ''"
      @click="emit('dislike')"
    >
      <ThumbsDown :size="20" :class="{ 'fill-slate-400': hasDisliked }" />
      <span class="text-xs font-medium">{{ dislikesCount }}</span>
    </button>
    <button
      type="button"
      class="detail-reaction-compact-button flex items-center gap-1.5 transition-all"
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
    class="detail-reaction-bar flex space-x-2"
  >
    <button
      type="button"
      class="detail-reaction-action detail-reaction-action-like flex-1 py-3 rounded-xl transition-all flex items-center justify-center group"
      @click="emit('like')"
    >
      <Heart
        :size="20"
        class="mr-2 transition-transform group-hover:scale-110"
        :class="hasLiked ? 'fill-pink-500 text-pink-500' : 'detail-reaction-icon group-hover:text-pink-400'"
      />
      <span class="font-medium" :class="hasLiked ? 'text-pink-400' : 'detail-reaction-count'">{{ likesCount }}</span>
    </button>
    <button
      type="button"
      class="detail-reaction-action detail-reaction-action-dislike flex-1 py-3 rounded-xl transition-all flex items-center justify-center group"
      @click="emit('dislike')"
    >
      <ThumbsDown
        :size="20"
        class="mr-2 transition-transform group-hover:scale-110"
        :class="hasDisliked ? 'fill-slate-400 text-slate-400' : 'detail-reaction-icon group-hover:text-[var(--detail-modal-text-primary)]'"
      />
      <span class="font-medium" :class="hasDisliked ? 'text-slate-400' : 'detail-reaction-count'">{{ dislikesCount }}</span>
    </button>
    <button
      type="button"
      class="detail-reaction-action detail-reaction-action-comment flex-1 py-3 rounded-xl transition-all flex items-center justify-center group"
      @click="emit('comment')"
    >
      <MessageCircle
        :size="20"
        class="detail-reaction-icon mr-2 transition-transform group-hover:scale-110 group-hover:text-blue-400"
      />
      <span class="detail-reaction-count font-medium">{{ commentsCount }}</span>
    </button>
  </div>
</template>

<style scoped>
.detail-reaction-compact-button {
  color: var(--detail-modal-text-secondary);
}

.detail-reaction-compact-button:hover,
.detail-reaction-compact-button:focus-visible {
  color: var(--detail-modal-text-primary);
}

.detail-reaction-compact-button.is-liked {
  color: #ec4899;
}

.detail-reaction-compact-button.is-disliked {
  color: var(--detail-modal-text-muted);
}

.detail-reaction-action {
  border: 1px solid var(--detail-modal-action-border);
  background: var(--detail-modal-action-bg);
}

.detail-reaction-action:hover {
  background: var(--detail-modal-action-hover-bg);
}

.detail-reaction-icon {
  color: var(--detail-modal-text-muted);
}

.detail-reaction-count {
  color: var(--detail-modal-text-secondary);
}
</style>
