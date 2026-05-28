import { computed, type ComputedRef, type Ref } from 'vue'
import type { GalleryComment } from '@/composables/useGalleryComments'

type ValueRef<T> = Ref<T> | ComputedRef<T>

export interface GalleryDetailStandardActions {
  showDesktopReaction?: boolean
  showDesktopApply?: boolean
  showDesktopCopy?: boolean
  showMobileReaction?: boolean
  showMobileApply?: boolean
  showMobileCopy?: boolean
  showPromptPanelCopy?: boolean
  maskPromptText?: boolean
  promptVisibleRatio?: number
  desktopApplyPlacement?: 'before' | 'after'
  desktopApplyInline?: boolean
  applyLabel?: string
  applyLoading?: boolean
  applyLoadingLabel?: string
  applyHint?: string
  copyLabel?: string
  onLike?: () => void
  onDislike?: () => void
  onComment?: () => void
  onApply?: () => void
  onCopy?: () => void
}

interface GalleryDetailModalBindings<TPost> {
  open: boolean
  commentInputOpen: boolean
  newComment: string
  currentPost: TPost | null
  currentDetailMedia: unknown
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
  submittingComment: boolean
  infoContentClass?: string
  desktopCloseButtonClass?: string
  commentsSectionClass?: string
  mobileLeftClass?: string
  mobileRightClass?: string
  standardActions: GalleryDetailStandardActions | null
}

interface UseGalleryDetailModalAdapterOptions<TPost> {
  open: Ref<boolean>
  commentInputOpen: Ref<boolean>
  newComment: Ref<string>
  currentPost: Ref<TPost | null>
  currentDetailMedia: ValueRef<unknown>
  hasPrev: ValueRef<boolean>
  hasNext: ValueRef<boolean>
  isMobile: ValueRef<boolean>
  title: () => string
  noTagsText: () => string
  formatTag: (tag: string) => string
  comments: ValueRef<GalleryComment[]>
  commentsLoading: ValueRef<boolean>
  commentsError: ValueRef<string>
  commentsPage: ValueRef<number>
  commentsTotal: ValueRef<number>
  commentsHasMore: ValueRef<boolean>
  submittingComment: ValueRef<boolean>
  standardActions: ValueRef<GalleryDetailStandardActions | null>
  loadComments: (
    postId: number,
    options?: { page?: number; append?: boolean }
  ) => Promise<unknown>
  loadMoreComments: () => Promise<unknown> | void
  submitComment: () => Promise<unknown> | void
  goPrev: () => void
  goNext: () => void
  infoContentClass?: string
  desktopCloseButtonClass?: string
  commentsSectionClass?: string
  mobileLeftClass?: string
  mobileRightClass?: string
}

export function useGalleryDetailModalAdapter<TPost extends { id: number }>(
  options: UseGalleryDetailModalAdapterOptions<TPost>,
) {
  const retryInitialComments = async () => {
    if (options.currentPost.value) {
      await options.loadComments(options.currentPost.value.id, { page: 1, append: false })
    }
  }

  const detailModalListeners = {
    'update:open': (value: unknown) => {
      options.open.value = Boolean(value)
    },
    'update:commentInputOpen': (value: unknown) => {
      options.commentInputOpen.value = Boolean(value)
    },
    'update:newComment': (value: unknown) => {
      options.newComment.value = typeof value === 'string' ? value : ''
    },
    prev: options.goPrev,
    next: options.goNext,
    retryInitial: retryInitialComments,
    retryMore: options.loadMoreComments,
    loadMore: options.loadMoreComments,
    submitComment: options.submitComment,
  }

  const detailModalBindings = computed<GalleryDetailModalBindings<TPost>>(() => ({
    open: options.open.value,
    commentInputOpen: options.commentInputOpen.value,
    newComment: options.newComment.value,
    currentPost: options.currentPost.value,
    currentDetailMedia: options.currentDetailMedia.value,
    hasPrev: options.hasPrev.value,
    hasNext: options.hasNext.value,
    isMobile: options.isMobile.value,
    title: options.title(),
    noTagsText: options.noTagsText(),
    formatTag: options.formatTag,
    comments: options.comments.value,
    commentsLoading: options.commentsLoading.value,
    commentsError: options.commentsError.value,
    commentsPage: options.commentsPage.value,
    commentsTotal: options.commentsTotal.value,
    commentsHasMore: options.commentsHasMore.value,
    submittingComment: options.submittingComment.value,
    infoContentClass: options.infoContentClass,
    desktopCloseButtonClass: options.desktopCloseButtonClass,
    commentsSectionClass: options.commentsSectionClass,
    mobileLeftClass: options.mobileLeftClass,
    mobileRightClass: options.mobileRightClass,
    standardActions: options.standardActions.value,
  }))

  return {
    retryInitialComments,
    detailModalBindings,
    detailModalListeners,
  }
}
