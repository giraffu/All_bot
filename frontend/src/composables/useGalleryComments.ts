import { ref, computed, watch, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { getGalleryCommentsPage } from '@/api/gallery'
import type { GalleryPost } from '@/types/gallery'

export interface CommentUser {
  id: number
  author_name: string
}

export interface GalleryComment {
  id: number
  content: string
  created_at: string
  user: CommentUser
}

export function useGalleryComments(
  currentPost: Ref<any | null>,
  posts: Ref<GalleryPost[]>,
  detailVisible?: Ref<boolean>
) {
  const { t } = useI18n()
  const comments = ref<GalleryComment[]>([])
  const commentsLoading = ref(false)
  const commentsError = ref('')
  const commentsPage = ref(1)
  const commentsTotal = ref(0)
  const commentsHasMore = computed(() => comments.value.length < commentsTotal.value)
  const showCommentInput = ref(false)
  const newComment = ref('')
  const submittingComment = ref(false)
  let currentCommentsRequestId = 0

  const invalidateCommentsRequests = () => {
    currentCommentsRequestId++
    commentsLoading.value = false
  }

  const mergeComments = (items: GalleryComment[], append: boolean) => {
    const merged = append ? [...comments.value, ...items] : items
    const seen = new Set<number>()
    return merged.filter((item) => {
      if (seen.has(item.id)) return false
      seen.add(item.id)
      return true
    })
  }

  const getCommentErrorMessage = (error: any, fallbackKey: string) => {
    const status = error?.response?.status
    if (status === 429) return t('gallery.comments.rate_limit')
    if (status === 404) return ''
    return t(fallbackKey)
  }

  const resetCommentComposer = () => {
    showCommentInput.value = false
    newComment.value = ''
  }

  const syncPostCommentsCount = (postId: number, nextCount: number) => {
    if (currentPost.value?.id === postId) {
      currentPost.value.comments_count = nextCount
    }

    const postInList = posts.value.find(post => post.id === postId)
    if (postInList && postInList !== currentPost.value) {
      postInList.comments_count = nextCount
    }
  }

  const loadComments = async (
    postId: number,
    options: { page?: number; append?: boolean } = {}
  ) => {
    const pageToLoad = options.page ?? 1
    const append = options.append ?? false
    const requestId = ++currentCommentsRequestId
    commentsError.value = ''
    commentsLoading.value = true

    try {
      const data = await getGalleryCommentsPage({
        postId,
        page: pageToLoad,
        size: 20,
      })

      if (requestId !== currentCommentsRequestId || currentPost.value?.id !== postId) {
        return false
      }

      commentsPage.value = data.page
      commentsTotal.value = data.total
      comments.value = mergeComments(data.items as GalleryComment[], append)
      return true
    } catch (error) {
      console.error('Failed to load comments:', error)
      if (requestId === currentCommentsRequestId) {
        commentsError.value = getCommentErrorMessage(error, 'gallery.comments.load_failed')
      }
      return false
    } finally {
      if (requestId === currentCommentsRequestId) {
        commentsLoading.value = false
      }
    }
  }

  const loadMoreComments = async () => {
    if (commentsHasMore.value && !commentsLoading.value && currentPost.value) {
      const nextPage = commentsPage.value + 1
      await loadComments(currentPost.value.id, { page: nextPage, append: true })
    }
  }

  const submitComment = async () => {
    if (!newComment.value.trim() || !currentPost.value) return
    const submitPostId = currentPost.value.id
    const trimmedContent = newComment.value.trim()
    submittingComment.value = true
    try {
      const res = await api.post(`/gallery/posts/${submitPostId}/comments`, {
        content: trimmedContent
      })

      const postInList = posts.value.find(post => post.id === submitPostId)
      const baseCount = currentPost.value?.id === submitPostId
        ? (currentPost.value.comments_count || 0)
        : (postInList?.comments_count || 0)
      syncPostCommentsCount(submitPostId, baseCount + 1)

      if (currentPost.value?.id === submitPostId) {
        invalidateCommentsRequests()
        commentsError.value = ''
        commentsPage.value = 1
        comments.value = mergeComments([res.data, ...comments.value], false)
        commentsTotal.value++
        void loadComments(submitPostId, { page: 1, append: false })

        newComment.value = ''
        showCommentInput.value = false
      }

      message.success(t('gallery.comments.submit_success'))
    } catch (error: any) {
      const msg = getCommentErrorMessage(error, 'gallery.comments.submit_failed')
      if (msg) {
        message.error(msg)
      }
    } finally {
      submittingComment.value = false
    }
  }

  watch(currentPost, (newPost) => {
    resetCommentComposer()
    if (newPost) {
      invalidateCommentsRequests()
      commentsError.value = ''
      comments.value = []
      commentsPage.value = 1
      commentsTotal.value = 0
      loadComments(newPost.id, { page: 1, append: false })
    } else {
      invalidateCommentsRequests()
      commentsError.value = ''
      comments.value = []
      commentsPage.value = 1
      commentsTotal.value = 0
    }
  })

  if (detailVisible) {
    watch(detailVisible, (visible) => {
      if (!visible) {
        resetCommentComposer()
        currentPost.value = null
      }
    })
  }

  return {
    comments,
    commentsLoading,
    commentsError,
    commentsPage,
    commentsTotal,
    commentsHasMore,
    showCommentInput,
    newComment,
    submittingComment,
    loadComments,
    loadMoreComments,
    submitComment
  }
}
