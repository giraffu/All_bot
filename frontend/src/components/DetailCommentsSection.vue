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
      <h3 class="text-slate-200 font-medium flex items-center gap-2">
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
        <p class="text-rose-300">{{ commentsError }}</p>
        <button
          @click="emit('retryInitial')"
          class="mt-3 text-cyan-400 hover:text-cyan-300 transition-colors"
        >
          {{ $t('gallery.comments.retry') }}
        </button>
      </div>
      <div v-else-if="comments.length === 0" class="py-8 text-center text-slate-500 text-sm">
        {{ $t('gallery.comments.empty') }}
      </div>
      <div v-else class="space-y-4 pb-24 lg:pb-4">
        <div v-if="commentsError" class="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          <span>{{ commentsError }}</span>
          <button
            @click="emit('retryMore')"
            class="ml-3 text-cyan-300 hover:text-cyan-200 transition-colors"
          >
            {{ $t('gallery.comments.retry') }}
          </button>
        </div>
        <div v-for="comment in comments" :key="comment.id" class="flex gap-3">
          <div class="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center shrink-0 border border-slate-600">
            <span class="text-slate-300 text-xs font-medium">{{ comment.user.author_name.charAt(0).toUpperCase() }}</span>
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span class="text-sm font-medium text-slate-300 truncate">{{ comment.user.author_name }}</span>
              <span class="text-xs text-slate-500">{{ dayjs(comment.created_at).format('MM-DD HH:mm') }}</span>
            </div>
            <p class="text-sm text-slate-300 break-words whitespace-pre-wrap">{{ comment.content }}</p>
          </div>
        </div>
        <div v-if="commentsHasMore" class="pt-2 pb-4 text-center">
          <button
            @click="emit('loadMore')"
            :disabled="commentsLoading"
            class="text-xs text-cyan-400 hover:text-cyan-300 transition-colors disabled:opacity-50"
          >
            {{ commentsLoading ? $t('gallery.comments.loading_more') : $t('gallery.comments.load_more') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
