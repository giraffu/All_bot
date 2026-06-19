<script setup lang="ts">
import dayjs from 'dayjs'
import type { GalleryComment } from '@/composables/useGalleryComments'
import DetailApplyActions from '@/components/DetailApplyActions.vue'
import DetailReactionBar from '@/components/DetailReactionBar.vue'
import DetailMediaPreview from '@/components/DetailMediaPreview.vue'
import DetailModalShell from '@/components/DetailModalShell.vue'
import DetailCommentsSection from '@/components/DetailCommentsSection.vue'
import DetailMobileBottomBar from '@/components/DetailMobileBottomBar.vue'
import DetailDesktopActions from '@/components/DetailDesktopActions.vue'
import OriginalInputsPanel from '@/components/OriginalInputsPanel.vue'
import PromptCopyButton from '@/components/PromptCopyButton.vue'
import PromptPreviewPanel from '@/components/PromptPreviewPanel.vue'

type DetailPost = any

interface DetailStandardActions {
  showDesktopReaction?: boolean
  showDesktopApply?: boolean
  showDesktopCopy?: boolean
  showMobileReaction?: boolean
  showMobileApply?: boolean
  showMobileCopy?: boolean
  showPromptPanelCopy?: boolean
  showPromptPanelUnlock?: boolean
  maskPromptText?: boolean
  promptVisibleRatio?: number
  desktopApplyPlacement?: 'before' | 'after'
  desktopApplyInline?: boolean
  applyLabel?: string
  applyLoading?: boolean
  applyDisabled?: boolean
  applyLoadingLabel?: string
  applyHint?: string
  copyLabel?: string
  unlockLabel?: string
  unlockLoading?: boolean
  onLike?: () => void
  onDislike?: () => void
  onComment?: () => void
  onApply?: () => void
  onCopy?: () => void
  onUnlockPrompt?: () => void
}

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
    standardActions?: DetailStandardActions | null
    showCommentsSection?: boolean
    showCommentComposer?: boolean
  }>(),
  {
    infoContentClass:
      'p-4 lg:p-6 flex-1 flex flex-col overflow-y-auto scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent',
    desktopCloseButtonClass: '',
    commentsSectionClass: '',
    mobileLeftClass: 'flex items-center gap-6',
    mobileRightClass: '',
    standardActions: null,
    showCommentsSection: true,
    showCommentComposer: true,
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
  if (!props.showCommentComposer) {
    return
  }
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
    :bodyStyle="isMobile ? { padding: 0, height: '100%', backgroundColor: 'var(--detail-modal-shell-bg)' } : { padding: 0, backgroundColor: 'transparent' }"
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
          <span class="detail-modal-mobile-title font-medium text-sm">{{ title }}</span>
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
        <h3 class="detail-modal-title hidden lg:flex text-xl font-bold mb-2 items-center">
          <span class="bg-gradient-to-r from-cyan-400 to-indigo-400 bg-clip-text text-transparent">{{ title }}</span>
        </h3>

        <div class="mb-4 lg:mb-6 mt-2 lg:mt-0">
          <div class="flex flex-wrap gap-2 mb-3">
            <span
              v-for="tag in currentPost.tags || []"
              :key="tag"
              class="detail-modal-tag text-xs px-2.5 py-1 rounded-full"
            >
              {{ tag.startsWith('#') ? formatTag(tag) : '#' + formatTag(tag) }}
            </span>
            <span
              v-if="!currentPost.tags || currentPost.tags.length === 0"
              class="detail-modal-empty-tag text-sm"
            >
              {{ noTagsText }}
            </span>
          </div>
          <div class="detail-modal-meta text-xs space-y-1">
            <div v-if="currentPost.created_at">
              <span>{{ dayjs(currentPost.created_at).format('YYYY-MM-DD HH:mm') }}</span>
            </div>
            <div class="flex space-x-4">
              <span v-if="currentPost.width">{{ currentPost.width }}x{{ currentPost.height }}</span>
              <span v-if="currentPost.duration">{{ currentPost.duration }}s</span>
            </div>
          </div>
        </div>

        <OriginalInputsPanel
          :source="currentPost"
          class="mb-4 lg:mb-6"
        />

        <PromptPreviewPanel
          v-if="currentPost.prompt?.trim()"
          class="mb-4 lg:mb-6"
          :title="$t('prompt_panel.title')"
          :prompt="currentPost.prompt"
          :expand-label="$t('prompt_panel.expand')"
          :collapse-label="$t('prompt_panel.collapse')"
          :show-copy="!!standardActions?.showPromptPanelCopy"
          :show-unlock="!!standardActions?.showPromptPanelUnlock"
          :mask-text="!!standardActions?.maskPromptText"
          :visible-ratio="standardActions?.promptVisibleRatio ?? 0.5"
          :copy-label="standardActions?.copyLabel || ''"
          :unlock-label="standardActions?.unlockLabel || ''"
          :unlock-loading="!!standardActions?.unlockLoading"
          @copy="standardActions?.onCopy?.()"
          @unlock="standardActions?.onUnlockPrompt?.()"
        />

        <slot
          name="before-comments"
          :post="currentPost"
          :open-comment-input="openCommentInput"
        >
          <DetailDesktopActions
            v-if="standardActions && (standardActions.showDesktopReaction || (standardActions.showDesktopApply && standardActions.desktopApplyPlacement === 'before'))"
            top-class="space-x-2 mb-4 pt-4"
            bottom-class="mt-8"
          >
            <template v-if="standardActions.showDesktopReaction" #top>
              <DetailReactionBar
                :likes-count="currentPost.likes_count || 0"
                :dislikes-count="currentPost.dislikes_count || 0"
                :comments-count="currentPost.comments_count || 0"
                :has-liked="currentPost.has_liked"
                :has-disliked="currentPost.has_disliked"
                @like="standardActions.onLike?.()"
                @dislike="standardActions.onDislike?.()"
                @comment="standardActions.onComment?.()"
              />
            </template>
            <template
              v-if="standardActions.showDesktopApply && standardActions.desktopApplyPlacement === 'before'"
              #bottom
            >
              <DetailApplyActions
                :apply-label="standardActions.applyLabel || title"
                :apply-loading="standardActions.applyLoading"
                :apply-disabled="standardActions.applyDisabled"
                :apply-loading-label="standardActions.applyLoadingLabel"
                :hint-text="standardActions.applyHint"
                @apply="standardActions.onApply?.()"
              />
            </template>
          </DetailDesktopActions>
        </slot>
        <slot
          name="before-comments-extra"
          :post="currentPost"
          :open-comment-input="openCommentInput"
        />

        <DetailCommentsSection
          v-if="showCommentsSection"
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
        >
          <DetailDesktopActions
            v-if="standardActions?.showDesktopApply && standardActions.desktopApplyPlacement !== 'before'"
            container-class="mt-auto"
            :bottom-class="standardActions.desktopApplyInline ? 'pt-4 border-t border-slate-700 lg:border-slate-400/30' : 'space-y-4 pt-4'"
          >
            <template #bottom>
              <DetailApplyActions
                :inline="standardActions.desktopApplyInline"
                :show-copy="standardActions.showDesktopCopy && !!currentPost.prompt?.trim()"
                :copy-label="standardActions.copyLabel || ''"
                :apply-label="standardActions.applyLabel || title"
                :apply-loading="standardActions.applyLoading"
                :apply-disabled="standardActions.applyDisabled"
                :apply-loading-label="standardActions.applyLoadingLabel"
                :hint-text="standardActions.applyHint"
                @copy="standardActions.onCopy?.()"
                @apply="standardActions.onApply?.()"
              />
            </template>
          </DetailDesktopActions>
        </slot>
        <slot
          name="after-comments-extra"
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
          >
            <template v-if="standardActions && (standardActions.showMobileReaction || (standardActions.showMobileCopy && !!currentPost.prompt?.trim()))">
              <DetailReactionBar
                v-if="standardActions.showMobileReaction"
                compact
                :likes-count="currentPost.likes_count || 0"
                :dislikes-count="currentPost.dislikes_count || 0"
                :comments-count="currentPost.comments_count || 0"
                :has-liked="currentPost.has_liked"
                :has-disliked="currentPost.has_disliked"
                @like="standardActions.onLike?.()"
                @dislike="standardActions.onDislike?.()"
                @comment="standardActions.onComment?.()"
              />
              <PromptCopyButton
                v-if="standardActions.showMobileCopy && !!currentPost.prompt?.trim()"
                compact
                :label="standardActions.copyLabel || ''"
                @click="standardActions.onCopy?.()"
              />
            </template>
          </slot>
          <slot
            name="mobile-left-extra"
            :post="currentPost"
            :open-comment-input="openCommentInput"
          />
        </template>
        <template #right>
          <slot
            name="mobile-right"
            :post="currentPost"
            :open-comment-input="openCommentInput"
          >
            <DetailApplyActions
              v-if="standardActions?.showMobileApply"
              inline
              compact-apply
              :apply-label="standardActions.applyLabel || title"
              :apply-loading="standardActions.applyLoading"
              :apply-disabled="standardActions.applyDisabled"
              :apply-loading-label="standardActions.applyLoadingLabel"
              :hint-text="standardActions.applyHint"
              @apply="standardActions.onApply?.()"
            />
          </slot>
          <slot
            name="mobile-right-extra"
            :post="currentPost"
            :open-comment-input="openCommentInput"
          />
        </template>
      </DetailMobileBottomBar>
    </DetailModalShell>
  </a-modal>

  <a-modal
    v-if="showCommentComposer"
    :open="commentInputOpen"
    :title="$t('gallery.comments.modal_title')"
    :footer="null"
    :destroyOnClose="true"
    :width="isMobile ? '95%' : 500"
    :bodyStyle="{ padding: '24px' }"
    class="comment-modal"
    @update:open="emit('update:commentInputOpen', $event)"
  >
    <div class="comment-modal-panel flex flex-col gap-4">
      <textarea
        :value="newComment"
        maxlength="500"
        :placeholder="$t('gallery.comments.placeholder')"
        class="comment-modal-textarea w-full h-32 p-3 rounded-xl outline-none resize-none"
        @input="handleNewCommentInput"
      ></textarea>
      <div class="flex justify-between items-center">
        <span class="comment-modal-counter text-xs">{{ newComment.length }}/500</span>
        <div class="flex gap-3">
          <button
            type="button"
            @click="closeCommentInput"
            class="comment-modal-secondary-btn px-4 py-2 rounded-lg transition-colors text-sm font-medium"
          >
            {{ $t('gallery.comments.cancel') }}
          </button>
          <button
            type="button"
            @click="emit('submitComment')"
            :disabled="!newComment.trim() || submittingComment"
            class="comment-modal-primary-btn px-4 py-2 rounded-lg transition-colors text-sm font-medium flex items-center"
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
.gallery-detail-modal {
  --detail-modal-shell-bg: #0f172a;
  --detail-modal-header-bg: rgba(15, 23, 42, 0.9);
  --detail-modal-panel-bg: rgba(71, 85, 105, 0.8);
  --detail-modal-bottom-bar-bg: rgba(15, 23, 42, 0.95);
  --detail-modal-border: rgba(148, 163, 184, 0.34);
  --detail-modal-divider: rgba(51, 65, 85, 0.95);
  --detail-modal-shadow: 0 24px 60px rgba(2, 6, 23, 0.38);
  --detail-modal-text-primary: #f8fafc;
  --detail-modal-text-secondary: #cbd5e1;
  --detail-modal-text-muted: #94a3b8;
  --detail-modal-link: #22d3ee;
  --detail-modal-link-hover: #67e8f9;
  --detail-modal-action-bg: rgba(100, 116, 139, 0.22);
  --detail-modal-action-hover-bg: rgba(100, 116, 139, 0.34);
  --detail-modal-action-border: rgba(148, 163, 184, 0.4);
  --detail-modal-copy-button-bg: rgba(100, 116, 139, 0.9);
  --detail-modal-copy-button-hover-bg: rgba(148, 163, 184, 0.92);
  --detail-modal-copy-button-text: #ffffff;
  --detail-modal-primary-gradient: linear-gradient(90deg, #0891b2, #4f46e5);
  --detail-modal-primary-gradient-hover: linear-gradient(90deg, #06b6d4, #6366f1);
  --detail-modal-primary-glow: 0 0 20px rgba(56, 189, 248, 0.32);
  --detail-modal-primary-solid: #0891b2;
  --detail-modal-primary-solid-hover: #06b6d4;
  --detail-modal-avatar-bg: rgba(51, 65, 85, 0.92);
  --detail-modal-avatar-border: rgba(100, 116, 139, 0.85);
  --detail-modal-tag-bg: rgba(15, 23, 42, 0.72);
  --detail-modal-tag-border: rgba(71, 85, 105, 0.92);
  --detail-modal-tag-text: #22d3ee;
  --prompt-preview-bg: rgba(15, 23, 42, 0.58);
  --prompt-preview-border: rgba(71, 85, 105, 0.9);
  --prompt-preview-shadow: inset 0 1px 0 rgba(148, 163, 184, 0.06);
  --prompt-preview-title: #f8fafc;
  --prompt-preview-text: #dbeafe;
  --prompt-preview-muted: #94a3b8;
  --prompt-preview-action-bg: rgba(15, 23, 42, 0.72);
  --prompt-preview-action-hover: rgba(30, 41, 59, 0.88);
  --prompt-preview-action-border: rgba(71, 85, 105, 0.95);
  --prompt-preview-action-text: #f8fafc;
}

html[data-theme='light'] .gallery-detail-modal {
  --detail-modal-shell-bg: #ffffff;
  --detail-modal-header-bg: rgba(255, 255, 255, 0.92);
  --detail-modal-panel-bg: rgba(248, 250, 252, 0.96);
  --detail-modal-bottom-bar-bg: rgba(255, 255, 255, 0.96);
  --detail-modal-border: rgba(203, 213, 225, 0.92);
  --detail-modal-divider: rgba(226, 232, 240, 0.96);
  --detail-modal-shadow: 0 24px 60px rgba(15, 23, 42, 0.14);
  --detail-modal-text-primary: #0f172a;
  --detail-modal-text-secondary: #334155;
  --detail-modal-text-muted: #64748b;
  --detail-modal-link: #2563eb;
  --detail-modal-link-hover: #1d4ed8;
  --detail-modal-action-bg: rgba(241, 245, 249, 0.98);
  --detail-modal-action-hover-bg: rgba(226, 232, 240, 0.98);
  --detail-modal-action-border: rgba(148, 163, 184, 0.35);
  --detail-modal-copy-button-bg: rgba(226, 232, 240, 0.98);
  --detail-modal-copy-button-hover-bg: rgba(203, 213, 225, 0.98);
  --detail-modal-copy-button-text: #334155;
  --detail-modal-primary-gradient: linear-gradient(90deg, #2563eb, #4f46e5);
  --detail-modal-primary-gradient-hover: linear-gradient(90deg, #1d4ed8, #4338ca);
  --detail-modal-primary-glow: 0 16px 30px rgba(59, 130, 246, 0.2);
  --detail-modal-primary-solid: #2563eb;
  --detail-modal-primary-solid-hover: #1d4ed8;
  --detail-modal-avatar-bg: rgba(241, 245, 249, 0.95);
  --detail-modal-avatar-border: rgba(203, 213, 225, 0.95);
  --detail-modal-tag-bg: rgba(219, 234, 254, 0.8);
  --detail-modal-tag-border: rgba(147, 197, 253, 0.6);
  --detail-modal-tag-text: #1d4ed8;
  --prompt-preview-bg: rgba(248, 250, 252, 0.96);
  --prompt-preview-border: rgba(203, 213, 225, 0.92);
  --prompt-preview-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.82);
  --prompt-preview-title: #0f172a;
  --prompt-preview-text: #334155;
  --prompt-preview-muted: #64748b;
  --prompt-preview-action-bg: rgba(241, 245, 249, 0.98);
  --prompt-preview-action-hover: rgba(226, 232, 240, 0.98);
  --prompt-preview-action-border: rgba(203, 213, 225, 0.95);
  --prompt-preview-action-text: #1e293b;
}

.gallery-detail-modal .detail-modal-mobile-title,
.gallery-detail-modal .detail-modal-title {
  color: var(--detail-modal-text-primary);
}

.gallery-detail-modal .detail-modal-tag {
  background: var(--detail-modal-tag-bg);
  border: 1px solid var(--detail-modal-tag-border);
  color: var(--detail-modal-tag-text);
}

.gallery-detail-modal .detail-modal-empty-tag,
.gallery-detail-modal .detail-modal-meta {
  color: var(--detail-modal-text-muted);
}

.comment-modal {
  --comment-modal-surface: #0f172a;
  --comment-modal-border: rgba(51, 65, 85, 0.95);
  --comment-modal-title: #f8fafc;
  --comment-modal-text: #e2e8f0;
  --comment-modal-muted: #94a3b8;
  --comment-modal-hover: rgba(51, 65, 85, 0.7);
  --comment-modal-input-bg: #111827;
  --comment-modal-input-border: rgba(100, 116, 139, 0.9);
  --comment-modal-input-border-focus: #06b6d4;
  --comment-modal-secondary-bg: #334155;
  --comment-modal-secondary-hover: #475569;
  --comment-modal-secondary-text: #e2e8f0;
  --comment-modal-primary-bg: #0891b2;
  --comment-modal-primary-hover: #06b6d4;
  --comment-modal-primary-shadow: 0 12px 28px rgba(8, 145, 178, 0.24);
}

html[data-theme='light'] .comment-modal {
  --comment-modal-surface: rgba(255, 255, 255, 0.98);
  --comment-modal-border: rgba(203, 213, 225, 0.9);
  --comment-modal-title: #0f172a;
  --comment-modal-text: #0f172a;
  --comment-modal-muted: #64748b;
  --comment-modal-hover: rgba(226, 232, 240, 0.85);
  --comment-modal-input-bg: #ffffff;
  --comment-modal-input-border: rgba(148, 163, 184, 0.95);
  --comment-modal-input-border-focus: #2563eb;
  --comment-modal-secondary-bg: #e2e8f0;
  --comment-modal-secondary-hover: #cbd5e1;
  --comment-modal-secondary-text: #334155;
  --comment-modal-primary-bg: #2563eb;
  --comment-modal-primary-hover: #1d4ed8;
  --comment-modal-primary-shadow: 0 12px 28px rgba(37, 99, 235, 0.18);
}

.comment-modal .ant-modal-content {
  background-color: var(--comment-modal-surface) !important;
  background-image: linear-gradient(var(--comment-modal-surface), var(--comment-modal-surface)) !important;
  border: 1px solid var(--comment-modal-border) !important;
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.18) !important;
  color: var(--comment-modal-text) !important;
}

.comment-modal .ant-modal-header {
  background: transparent !important;
  border-bottom: none !important;
}

.comment-modal .ant-modal-title {
  color: var(--comment-modal-title) !important;
}

.comment-modal .ant-modal-close {
  color: var(--comment-modal-muted) !important;
}

.comment-modal .ant-modal-close:hover {
  color: var(--comment-modal-title) !important;
  background: var(--comment-modal-hover) !important;
}

.comment-modal-panel {
  color: var(--comment-modal-text);
  forced-color-adjust: none;
}

.comment-modal-textarea {
  appearance: none;
  -webkit-appearance: none;
  background-color: var(--comment-modal-input-bg) !important;
  background-image: linear-gradient(var(--comment-modal-input-bg), var(--comment-modal-input-bg)) !important;
  border: 1px solid var(--comment-modal-input-border) !important;
  color: var(--comment-modal-text) !important;
  -webkit-text-fill-color: var(--comment-modal-text);
  caret-color: var(--comment-modal-text);
  box-shadow: none !important;
  forced-color-adjust: none;
}

.comment-modal-textarea::placeholder {
  color: var(--comment-modal-muted);
  -webkit-text-fill-color: var(--comment-modal-muted);
}

.comment-modal-textarea:focus {
  border-color: var(--comment-modal-input-border-focus) !important;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--comment-modal-input-border-focus) 16%, transparent) !important;
}

.comment-modal-counter {
  color: var(--comment-modal-muted);
}

.comment-modal-secondary-btn,
.comment-modal-primary-btn {
  appearance: none;
  -webkit-appearance: none;
  border: 1px solid transparent;
  background-clip: padding-box;
  forced-color-adjust: none;
}

.comment-modal-secondary-btn {
  background-color: var(--comment-modal-secondary-bg) !important;
  background-image: linear-gradient(var(--comment-modal-secondary-bg), var(--comment-modal-secondary-bg)) !important;
  color: var(--comment-modal-secondary-text) !important;
  -webkit-text-fill-color: var(--comment-modal-secondary-text);
}

.comment-modal-secondary-btn:hover {
  background-color: var(--comment-modal-secondary-hover) !important;
  background-image: linear-gradient(var(--comment-modal-secondary-hover), var(--comment-modal-secondary-hover)) !important;
}

.comment-modal-primary-btn {
  background-color: var(--comment-modal-primary-bg) !important;
  background-image: linear-gradient(var(--comment-modal-primary-bg), var(--comment-modal-primary-bg)) !important;
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff;
  box-shadow: var(--comment-modal-primary-shadow);
}

.comment-modal-primary-btn:hover:not(:disabled) {
  background-color: var(--comment-modal-primary-hover) !important;
  background-image: linear-gradient(var(--comment-modal-primary-hover), var(--comment-modal-primary-hover)) !important;
}

.comment-modal-primary-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.gallery-detail-modal .ant-modal-content {
  background-color: transparent !important;
  box-shadow: none !important;
}

.gallery-detail-modal .ant-modal-mask {
  background-color: rgba(0, 0, 0, 0.85) !important;
  backdrop-filter: blur(8px);
}
</style>
