import { computed, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { getMyLibraryPosts } from '@/api/gallery'
import { useCurrentDetailMedia } from '@/composables/useCurrentDetailMedia'
import { useDetailTemplateApply } from '@/composables/useDetailTemplateApply'
import { useGalleryComments } from '@/composables/useGalleryComments'
import { useGalleryPostInteractions } from '@/composables/useGalleryPostInteractions'
import { usePagedPostBrowser } from '@/composables/usePagedPostBrowser'
import { usePostPromptCopy } from '@/composables/usePostPromptCopy'
import { useTemplateApplyStore } from '@/stores/templateApply'
import type { GalleryPost, LibraryCollectionScope } from '@/types/gallery'
import { formatGalleryTag } from '@/utils/galleryPresentation'
import {
  resolveGalleryTemplateApplyDisabledMessage,
  resolveGalleryTemplateApplyDisabledReason,
} from '@/utils/galleryTemplateApply'
import { resolveMediaCardView } from '@/utils/mediaCardView'

type MaybeGetter<T> = T | (() => T)

const resolveValue = <T>(value: MaybeGetter<T>): T =>
  typeof value === 'function' ? (value as () => T)() : value

interface UseMyLibraryPostBrowserOptions<Post extends GalleryPost> {
  pageSize: Ref<number>
  scope: MaybeGetter<LibraryCollectionScope>
  taskType: MaybeGetter<string | undefined>
  t: (key: string) => string
  templateApplySource: MaybeGetter<'favorites' | 'gallery' | 'submissions'>
  detailItemId: (post: Post) => number | string
  detailEntryEntityId?: (post: Post) => number | string | null
  ignoreTemplateApplyNotFound?: boolean
  resolveCommentsPostId?: (post: Post | null) => number | null
  resolveCardViewOptions?: (
    scope: LibraryCollectionScope
  ) => Parameters<typeof resolveMediaCardView>[1]
  shouldIgnoreInteractionError?: (error: any) => boolean
  resolveInteractionSuccessMessage: (action: 'like' | 'dislike', state: string) => string
}

export function useMyLibraryPostBrowser<Post extends GalleryPost>(
  options: UseMyLibraryPostBrowserOptions<Post>,
) {
  const templateApplyStore = useTemplateApplyStore()
  const {
    posts,
    loading,
    errorMessage,
    currentPage,
    totalPages,
    detailVisible,
    currentPost,
    hasPrev,
    hasNext,
    clearBrowserState,
    goNext,
    goPrev,
    goToPage,
    loadPosts,
    openDetail,
    prefetchNextPage,
  } = usePagedPostBrowser<Post>({
    pageSize: options.pageSize,
    fetchPageData: async (pageNumber) => {
      const scope = resolveValue(options.scope)
      const data = await getMyLibraryPosts({
        scope,
        page: pageNumber,
        size: options.pageSize.value,
        taskType: resolveValue(options.taskType),
      })
      const items = data.items as Post[]

      return {
        items: items.map((post) => {
          const cardView = resolveMediaCardView(
            post,
            options.resolveCardViewOptions?.(scope),
          )
          return {
            ...post,
            src: cardView.initialSrc,
            cardIsVideo: cardView.isVideo,
            cardPoster: cardView.posterSrc,
          }
        }),
        total: data.total,
        pages: data.pages,
      }
    },
    onFetchError: (error) => {
      console.error(error)
      message.error(options.t('my_notes.load_failed'))
    },
    getFetchErrorMessage: () => options.t('my_notes.load_failed'),
  })

  const {
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
    submitComment,
  } = useGalleryComments(currentPost, posts, detailVisible, {
    resolvePostId: options.resolveCommentsPostId
      ? (post) => options.resolveCommentsPostId?.(post ?? null) ?? null
      : undefined,
  })

  const { handleInteract } = useGalleryPostInteractions<Post>({
    resolveSuccessMessage: options.resolveInteractionSuccessMessage,
    shouldIgnoreError: options.shouldIgnoreInteractionError,
    onError: (error) => {
      console.error(error)
    },
  })

  const currentPostRef = currentPost as Ref<Post | null>
  const currentTemplateApplyDisabledReason = computed(() =>
    resolveGalleryTemplateApplyDisabledReason(currentPost.value)
  )
  const currentTemplateApplyDisabledMessage = computed(() =>
    currentTemplateApplyDisabledReason.value
      ? resolveGalleryTemplateApplyDisabledMessage(
          options.t,
          currentTemplateApplyDisabledReason.value
        )
      : ''
  )
  const { applying, handleApply } = useDetailTemplateApply<Post>({
    currentPost: currentPostRef,
    detailVisible,
    itemId: options.detailItemId,
    source: () => resolveValue(options.templateApplySource),
    entryEntityId: options.detailEntryEntityId,
    templateApplyStore,
    t: options.t,
    ignoreNotFound: options.ignoreTemplateApplyNotFound,
    isApplyDisabled: (post) => resolveGalleryTemplateApplyDisabledReason(post) !== null,
    getApplyDisabledMessage: (post) =>
      resolveGalleryTemplateApplyDisabledMessage(
        options.t,
        resolveGalleryTemplateApplyDisabledReason(post)
      ),
  })

  const currentDetailMedia = useCurrentDetailMedia(currentPostRef)
  const formatTag = (tag: string) => formatGalleryTag(tag, options.t)
  const { copyPrompt } = usePostPromptCopy(options.t)

  const favoriteSupportsPostDetail = computed(() => {
    if (resolveValue(options.scope) !== 'favorite') {
      return true
    }

    const post = currentPost.value
    if (!post) {
      return false
    }

    return Number(post.id) > 0 && post.is_active !== false
  })

  return {
    posts,
    loading,
    errorMessage,
    currentPage,
    totalPages,
    detailVisible,
    currentPost,
    hasPrev,
    hasNext,
    clearBrowserState,
    goNext,
    goPrev,
    goToPage,
    loadPosts,
    openDetail,
    prefetchNextPage,
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
    submitComment,
    handleInteract,
    applying,
    handleApply,
    currentTemplateApplyDisabledReason,
    currentTemplateApplyDisabledMessage,
    currentDetailMedia,
    formatTag,
    copyPrompt,
    favoriteSupportsPostDetail,
  }
}
