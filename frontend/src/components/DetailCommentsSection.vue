<script setup lang="ts">
import dayjs from 'dayjs'
import { MessageCircle } from 'lucide-vue-next'
import type { GalleryComment } from '@/composables/useGalleryComments'

const props = withDefaults(
  defineProps<{
    comments: GalleryComment[]
    commentsLoading: boolean
    commentsError: string
    commentsPage: number
    commentsTotal: number
    commentsHasMore: boolean
    isMobile: boolean
    sectionClass?: string
  }>(),
  {
    sectionClass: 'mt-6 flex flex-col min-h-[200px] lg:flex-1 lg:max-h-none lg:overflow-hidden',
  },
)

const emit = defineEmits<{
  retryInitial: []
  retryMore: []
  loadMore: []
}>()
</script>

<template>
  <div :class="sectionClass">
    <div class="flex items-center justify-between mb-4 shrink-0">
      <h3 class="detail-comments-title font-medium flex items-center gap-2">
        <MessageCircle :size="18" />
        {{ $t('gallery.comments.section_title', { count: commentsTotal }) }}
      </h3>
    </div>
    <div
      :class="isMobile
        ? 'pr-0'
        : 'flex-1 overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent'"
    >
      <div v-if="commentsLoading && commentsPage === 1" class="py-8 text-center">
        <div class="inline-block w-6 h-6 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin"></div>
      </div>
      <div v-else-if="commentsError && comments.length === 0" class="py-8 text-center text-sm">
        <p class="detail-comments-error">{{ commentsError }}</p>
        <button
          @click="emit('retryInitial')"
          class="detail-comments-link mt-3 transition-colors"
        >
          {{ $t('gallery.comments.retry') }}
        </button>
      </div>
      <div v-else-if="comments.length === 0" class="detail-comments-empty py-8 text-center text-sm">
        {{ $t('gallery.comments.empty') }}
      </div>
      <div v-else class="space-y-4 pb-24 lg:pb-4">
        <div v-if="commentsError" class="detail-comments-warning rounded-lg px-3 py-2 text-xs">
          <span>{{ commentsError }}</span>
          <button
            @click="emit('retryMore')"
            class="detail-comments-link ml-3 transition-colors"
          >
            {{ $t('gallery.comments.retry') }}
          </button>
        </div>
        <div v-for="comment in comments" :key="comment.id" class="flex gap-3">
          <div class="detail-comments-avatar w-8 h-8 rounded-full flex items-center justify-center shrink-0">
            <span class="detail-comments-avatar-text text-xs font-medium">{{ comment.user.author_name.charAt(0).toUpperCase() }}</span>
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span class="detail-comments-author text-sm font-medium truncate">{{ comment.user.author_name }}</span>
              <span class="detail-comments-time text-xs">{{ dayjs(comment.created_at).format('MM-DD HH:mm') }}</span>
            </div>
            <p class="detail-comments-body text-sm break-words whitespace-pre-wrap">{{ comment.content }}</p>
          </div>
        </div>
        <div v-if="commentsHasMore" class="pt-2 pb-4 text-center">
          <button
            @click="emit('loadMore')"
            :disabled="commentsLoading"
            class="detail-comments-link text-xs transition-colors disabled:opacity-50"
          >
            {{ commentsLoading ? $t('gallery.comments.loading_more') : $t('gallery.comments.load_more') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail-comments-title,
.detail-comments-author,
.detail-comments-body {
  color: var(--detail-modal-text-secondary);
}

.detail-comments-time,
.detail-comments-empty {
  color: var(--detail-modal-text-muted);
}

.detail-comments-error {
  color: #fda4af;
}

.detail-comments-warning {
  border: 1px solid rgba(245, 158, 11, 0.28);
  background: rgba(245, 158, 11, 0.12);
  color: #d97706;
}

.detail-comments-link {
  color: var(--detail-modal-link);
}

.detail-comments-link:hover {
  color: var(--detail-modal-link-hover);
}

.detail-comments-avatar {
  background: var(--detail-modal-avatar-bg);
  border: 1px solid var(--detail-modal-avatar-border);
}

.detail-comments-avatar-text {
  color: var(--detail-modal-text-secondary);
}
</style>
