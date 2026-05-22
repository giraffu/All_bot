// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'

import { useGalleryDetailModalAdapter } from '@/composables/useGalleryDetailModalAdapter'

describe('useGalleryDetailModalAdapter', () => {
  it('keeps bindings in sync and forwards modal callbacks to the supplied handlers', async () => {
    const open = ref(true)
    const commentInputOpen = ref(false)
    const newComment = ref('old comment')
    const currentPost = ref({ id: 7, title: 'demo' })
    const currentDetailMedia = computed(() => ({ src: 'demo.png' }))
    const hasPrev = computed(() => false)
    const hasNext = computed(() => true)
    const isMobile = computed(() => false)
    const comments = computed(() => [])
    const commentsLoading = computed(() => false)
    const commentsError = computed(() => '')
    const commentsPage = computed(() => 1)
    const commentsTotal = computed(() => 0)
    const commentsHasMore = computed(() => false)
    const submittingComment = computed(() => false)
    const standardActions = computed(() => ({
      showDesktopReaction: true,
    }))
    const loadComments = vi.fn().mockResolvedValue(undefined)
    const loadMoreComments = vi.fn().mockResolvedValue(undefined)
    const submitComment = vi.fn().mockResolvedValue(undefined)
    const goPrev = vi.fn()
    const goNext = vi.fn()

    const { detailModalBindings, detailModalListeners, retryInitialComments } =
      useGalleryDetailModalAdapter({
        open,
        commentInputOpen,
        newComment,
        currentPost,
        currentDetailMedia,
        hasPrev,
        hasNext,
        isMobile,
        title: () => '详情标题',
        noTagsText: () => '无标签',
        formatTag: (tag: string) => tag.toUpperCase(),
        comments,
        commentsLoading,
        commentsError,
        commentsPage,
        commentsTotal,
        commentsHasMore,
        submittingComment,
        standardActions,
        loadComments,
        loadMoreComments,
        submitComment,
        goPrev,
        goNext,
        infoContentClass: 'info-class',
        desktopCloseButtonClass: 'desktop-close',
        commentsSectionClass: 'comments-class',
        mobileLeftClass: 'mobile-left',
        mobileRightClass: 'mobile-right',
      })

    expect(detailModalBindings.value.open).toBe(true)
    expect(detailModalBindings.value.currentPost?.id).toBe(7)
    expect(detailModalBindings.value.currentDetailMedia).toEqual({ src: 'demo.png' })
    expect(detailModalBindings.value.title).toBe('详情标题')
    expect(detailModalBindings.value.standardActions?.showDesktopReaction).toBe(true)

    detailModalListeners['update:open'](false)
    detailModalListeners['update:commentInputOpen'](true)
    detailModalListeners['update:newComment']('new comment')
    detailModalListeners.prev()
    detailModalListeners.next()
    await detailModalListeners.retryInitial()
    await detailModalListeners.retryMore()
    await detailModalListeners.loadMore()
    await detailModalListeners.submitComment()
    await retryInitialComments()

    expect(open.value).toBe(false)
    expect(commentInputOpen.value).toBe(true)
    expect(newComment.value).toBe('new comment')
    expect(goPrev).toHaveBeenCalledTimes(1)
    expect(goNext).toHaveBeenCalledTimes(1)
    expect(loadComments).toHaveBeenCalledTimes(2)
    expect(loadComments).toHaveBeenNthCalledWith(1, 7, { page: 1, append: false })
    expect(loadComments).toHaveBeenNthCalledWith(2, 7, { page: 1, append: false })
    expect(loadMoreComments).toHaveBeenCalledTimes(2)
    expect(submitComment).toHaveBeenCalledTimes(1)
  })
})
