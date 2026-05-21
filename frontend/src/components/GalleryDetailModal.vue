<script setup lang="ts">
import dayjs from 'dayjs'
import type { GalleryComment } from '@/composables/useGalleryComments'
import DetailMediaPreview from '@/components/DetailMediaPreview.vue'
import DetailModalShell from '@/components/DetailModalShell.vue'
import DetailCommentsSection from '@/components/DetailCommentsSection.vue'
import DetailMobileBottomBar from '@/components/DetailMobileBottomBar.vue'

type DetailPost = any

const props = withDefaults(
  defineProps<{
    open: boolean
    currentPost: DetailPost | null
    currentDetailMedia: any
    hasPrev: boolean
    hasNext: boolean
    isMobile: boolean
    title: string
    noTagsText: string
    formatTag: (tag: string) => string
    comments: GalleryComment[]
    commentsLoading: boolean
    commentsError: string
    commentsPage: number
    commentsTotal: number
    commentsHasMore: boolean
    commentInputOpen: boolean
    newComment: string
    submittingComment: boolean
    infoContentClass?: string
    desktopCloseButtonClass?: string
    commentsSectionClass?: string
    mobileLeftClass?: string
    mobileRightClass?: string
  }>(),
  {
    infoContentClass:
      'p-4 lg:p-6 flex-1 flex flex-col overflow-y-auto scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent',
    desktopCloseButtonClass: '',
    commentsSectionClass: '',
    mobileLeftClass: 'flex items-center gap-6',
    mobileRightClass: '',
  },
)

const emit = defineEmits<{
  'update:open': [value: boolean]
  'update:commentInputOpen': [value: boolean]
  'update:newComment': [value: string]
  prev: []
  next: []
  retryInitial: []
  retryMore: []
  loadMore: []
  submitComment: []
}>()

const closeModal = () => {
  emit('update:open', false)
}

const openCommentInput = () => {
  emit('update:commentInputOpen', true)
}

const closeCommentInput = () => {
  emit('update:commentInputOpen', false)
}

const handleNewCommentInput = (event: Event) => {
  emit('update:newComment', (event.target as HTMLTextAreaElement).value)
}
</script>

<template>
  <a-modal
    :open="open"
    :footer="null"
    :closable="false"
    :width="isMobile ? '100%' : '90%'"
    :style="isMobile ? { top: 0, padding: 0, margin: 0, maxWidth: '100%' } : { maxWidth: '1000px', top: '20px' }"
    :wrapClassName="isMobile ? 'mobile-full-modal' : ''"
    class="gallery-detail-modal"
    :bodyStyle="isMobile ? { padding: 0, height: '100%', backgroundColor: '#0f172a' } : { padding: 0, backgroundColor: 'transparent' }"
    destroyOnClose
    @update:open="emit('update:open', $event)"
  >
    <DetailModalShell
      v-if="currentPost"
      :info-content-class="infoContentClass"
      :desktop-close-button-class="desktopCloseButtonClass"
      @close="closeModal"
    >
      <template #mobile-header>
        <slot name="mobile-header" :post="currentPost">
          <span class="text-slate-200 font-medium text-sm">{{ title }}</span>
        </slot>
      </template>

      <template #media>
        <DetailMediaPreview
          :media="currentDetailMedia"
          :has-prev="hasPrev"
          :has-next="hasNext"
          @prev="emit('prev')"
          @next="emit('next')"
        />
      </template>

      <template #info>
        <h3 class="hidden lg:flex text-xl font-bold text-slate-100 mb-2 items-center">
          <span class="bg-gradient-to-r from-cyan-400 to-indigo-400 bg-clip-text text-transparent">{{ title }}</span>
        </h3>

        <div class="mb-4 lg:mb-6 mt-2 lg:mt-0">
          <div class="flex flex-wrap gap-2 mb-3">
            <span
              v-for="tag in currentPost.tags || []"
              :key="tag"
              class="text-xs bg-slate-800 lg:bg-slate-500 text-cyan-400 lg:text-cyan-200 border border-slate-700 lg:border-slate-400 px-2.5 py-1 rounded-full"
            >
              {{ tag.startsWith('#') ? formatTag(tag) : '#' + formatTag(tag) }}
            </span>
            <span
              v-if="!currentPost.tags || currentPost.tags.length === 0"
              class="text-sm text-slate-500 lg:text-slate-400"
            >
              {{ noTagsText }}
            </span>
          </div>
          <div class="text-xs text-slate-500 lg:text-slate-400 space-y-1">
            <div v-if="currentPost.created_at">
              <span>{{ dayjs(currentPost.created_at).format('YYYY-MM-DD HH:mm') }}</span>
            </div>
            <div class="flex space-x-4">
              <span v-if="currentPost.width">{{ currentPost.width }}x{{ currentPost.height }}</span>
              <span v-if="currentPost.duration">{{ currentPost.duration }}s</span>
            </div>
          </div>
        </div>

        <slot
          name="before-comments"
          :post="currentPost"
          :open-comment-input="openCommentInput"
        />

        <DetailCommentsSection
          :comments="comments"
          :comments-loading="commentsLoading"
          :comments-error="commentsError"
          :comments-page="commentsPage"
          :comments-total="commentsTotal"
          :comments-has-more="commentsHasMore"
          :is-mobile="isMobile"
          :section-class="commentsSectionClass"
          @retry-initial="emit('retryInitial')"
          @retry-more="emit('retryMore')"
          @load-more="emit('loadMore')"
        />

        <slot
          name="after-comments"
          :post="currentPost"
          :open-comment-input="openCommentInput"
        />
      </template>

      <DetailMobileBottomBar
        :left-class="mobileLeftClass"
        :right-class="mobileRightClass"
      >
        <template #left>
          <slot
            name="mobile-left"
            :post="currentPost"
            :open-comment-input="openCommentInput"
          />
        </template>
        <template #right>
          <slot
            name="mobile-right"
            :post="currentPost"
            :open-comment-input="openCommentInput"
          />
        </template>
      </DetailMobileBottomBar>
    </DetailModalShell>
  </a-modal>

  <a-modal
    :open="commentInputOpen"
    :title="$t('gallery.comments.modal_title')"
    :footer="null"
    :destroyOnClose="true"
    :width="isMobile ? '95%' : 500"
    :bodyStyle="{ padding: '24px' }"
    class="comment-modal"
    @update:open="emit('update:commentInputOpen', $event)"
  >
    <div class="flex flex-col gap-4">
      <textarea
        :value="newComment"
        maxlength="500"
        :placeholder="$t('gallery.comments.placeholder')"
        class="w-full h-32 p-3 rounded-xl bg-slate-800 border border-slate-600 text-slate-200 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
        @input="handleNewCommentInput"
      ></textarea>
      <div class="flex justify-between items-center">
        <span class="text-xs text-slate-500">{{ newComment.length }}/500</span>
        <div class="flex gap-3">
          <button
            @click="closeCommentInput"
            class="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 transition-colors text-sm font-medium"
          >
            {{ $t('gallery.comments.cancel') }}
          </button>
          <button
            @click="emit('submitComment')"
            :disabled="!newComment.trim() || submittingComment"
            class="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:hover:bg-cyan-600 text-white transition-colors text-sm font-medium flex items-center"
          >
            <div v-if="submittingComment" class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2"></div>
            {{ $t('gallery.comments.submit') }}
          </button>
        </div>
      </div>
    </div>
  </a-modal>
</template>

<style>
.gallery-detail-modal .ant-modal-content {
  background-color: transparent !important;
  box-shadow: none !important;
}

.gallery-detail-modal .ant-modal-mask {
  background-color: rgba(0, 0, 0, 0.85) !important;
  backdrop-filter: blur(8px);
}
</style>
