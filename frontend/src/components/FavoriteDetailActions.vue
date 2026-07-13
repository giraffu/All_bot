<script setup lang="ts">
import { MessageCircle, Trash2 } from 'lucide-vue-next'

withDefaults(
  defineProps<{
    commentsCount: number
    unfavoriteLabel: string
    compact?: boolean
    showCommentButton?: boolean
  }>(),
  {
    compact: false,
    showCommentButton: true,
  },
)

const emit = defineEmits<{
  unfavorite: []
  comment: []
}>()
</script>

<template>
  <div :class="compact ? 'flex items-center gap-1.5' : 'flex space-x-2'">
    <button
      type="button"
      :class="compact
        ? 'favorite-detail-action-compact favorite-detail-action-danger flex items-center gap-1.5 transition-all'
        : 'favorite-detail-action favorite-detail-action-danger flex-1 py-3 rounded-xl transition-all flex items-center justify-center group'
      "
      @click="emit('unfavorite')"
    >
      <Trash2 :size="compact ? 22 : 18" :class="compact ? '' : 'mr-2 transition-transform group-hover:scale-110'" />
      <span :class="compact ? 'text-sm font-medium' : 'font-medium'">{{ unfavoriteLabel }}</span>
    </button>
    <button
      v-if="showCommentButton"
      type="button"
      :class="compact
        ? 'favorite-detail-action-compact favorite-detail-action-neutral flex items-center gap-1.5 transition-all'
        : 'favorite-detail-action favorite-detail-action-neutral flex-1 py-3 rounded-xl transition-all flex items-center justify-center group'
      "
      @click="emit('comment')"
    >
      <MessageCircle :size="compact ? 22 : 20" :class="compact ? '' : 'favorite-detail-action-icon mr-2 transition-transform group-hover:scale-110 group-hover:text-blue-400'" />
      <span :class="compact ? 'text-sm font-medium' : 'favorite-detail-action-text font-medium'">{{ commentsCount }}</span>
    </button>
  </div>
</template>

<style scoped>
.favorite-detail-action {
  border: 1px solid var(--detail-modal-action-border);
}

.favorite-detail-action-neutral {
  background: var(--detail-modal-action-bg);
  color: var(--detail-modal-text-secondary);
}

.favorite-detail-action-neutral:hover {
  background: var(--detail-modal-action-hover-bg);
}

.favorite-detail-action-compact.favorite-detail-action-neutral {
  color: var(--detail-modal-text-secondary);
}

.favorite-detail-action-danger {
  color: #f87171;
}

.favorite-detail-action.favorite-detail-action-danger {
  border-color: rgba(239, 68, 68, 0.3);
  background: rgba(239, 68, 68, 0.1);
}

.favorite-detail-action.favorite-detail-action-danger:hover {
  background: rgba(239, 68, 68, 0.18);
}

.favorite-detail-action-icon {
  color: var(--detail-modal-text-muted);
}

.favorite-detail-action-text {
  color: var(--detail-modal-text-secondary);
}
</style>
