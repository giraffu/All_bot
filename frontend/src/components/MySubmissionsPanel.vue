<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import {
  Eye,
  EyeOff,
  Trash2,
  Video,
} from 'lucide-vue-next'
import api from '@/api'
import { useViewport } from '@/composables/useViewport'
import { useMainLayoutContentRef } from '@/composables/useWorkbenchScrollLock'
import { useTemplateApplyStore } from '@/stores/templateApply'
import { useGalleryComments } from '@/composables/useGalleryComments'
import { usePagedPostBrowser } from '@/composables/usePagedPostBrowser'
import { useGalleryPostInteractions } from '@/composables/useGalleryPostInteractions'
import { useScrollPrefetch } from '@/composables/useScrollPrefetch'
import { handleMediaCardImageError } from '@/utils/mediaCardFallback'
import { resolveMediaCardView } from '@/utils/mediaCardView'
import { useDetailTemplateApply } from '@/composables/useDetailTemplateApply'
import { useGalleryDetailModalAdapter } from '@/composables/useGalleryDetailModalAdapter'
import { usePostPromptCopy } from '@/composables/usePostPromptCopy'
import { usePagedScrollNavigation } from '@/composables/usePagedScrollNavigation'
import { useCurrentDetailMedia } from '@/composables/useCurrentDetailMedia'
import { formatGalleryTag } from '@/utils/galleryPresentation'
import GalleryDetailModal from '@/components/GalleryDetailModal.vue'
import GalleryMediaCard from '@/components/GalleryMediaCard.vue'
import HeaderPaginationBar from '@/components/HeaderPaginationBar.vue'
import PostCardMetricsBar from '@/components/PostCardMetricsBar.vue'
import PostBrowserShell from '@/components/PostBrowserShell.vue'
import PostTagPreview from '@/components/PostTagPreview.vue'
import SubmissionManageButtons from '@/components/SubmissionManageButtons.vue'
import StickyHeaderSection from '@/components/StickyHeaderSection.vue'

interface Post {
  id: number
  task_id: string
  media_type: string
  width: number
  height: number
  duration: number
  tags: string[]
  likes_count: number
  dislikes_count: number
  applied_count: number
  comments_count: number
  thumbnail_url: string
  media_url: string
  created_at: string
  has_liked: boolean
  has_disliked: boolean
  is_active: boolean
  prompt: string
  src?: string
  cardIsVideo?: boolean
  cardPoster?: string
}

const props = withDefaults(
  defineProps<{
    taskType?: string
  }>(),
  {
    taskType: 'all',
  },
)
const templateApplyStore = useTemplateApplyStore()

const { isMobile } = useViewport()
const { t } = useI18n()
const layoutContentRef = useMainLayoutContentRef()
const size = ref(20)
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
  loadPosts,
  goToPage: browserGoToPage,
  goPrev,
  goNext,
  openDetail,
  prefetchNextPage,
} = usePagedPostBrowser<Post>({
  pageSize: size,
  fetchPageData: async (pageNumber) => {
    const res = await api.get('/gallery/my-posts', {
      params: {
        page: pageNumber,
        size: size.value,
        task_type: props.taskType === 'all' ? undefined : props.taskType,
      },
    })
    return {
      items: res.data.items.map((post: Post) => {
        const cardView = resolveMediaCardView(post)
        return {
          ...post,
          src: cardView.initialSrc,
          cardIsVideo: cardView.isVideo,
          cardPoster: cardView.posterSrc,
        }
      }),
      total: res.data.total,
      pages: res.data.pages,
    }
  },
  onFetchError: (error) => {
    console.error(error)
    message.error(t('my_notes.load_failed'))
  },
  getFetchErrorMessage: () => t('my_notes.load_failed'),
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
  submitComment
} = useGalleryComments(currentPost, posts, detailVisible)
const { handleInteract } = useGalleryPostInteractions<Post>({
  resolveSuccessMessage: (action, state) => {
    if (action === 'like') {
      return state === 'canceled' ? t('my_notes.like_removed') : t('my_notes.like_added')
    }
    return state === 'canceled' ? t('my_notes.dislike_removed') : t('my_notes.dislike_added')
  },
  onError: (error) => {
    console.error(error)
  },
})
const currentDetailMedia = useCurrentDetailMedia(currentPost)
const formatTag = (tag: string) => formatGalleryTag(tag, t)
const { copyPrompt } = usePostPromptCopy(t)
const { applying, handleApply, cancelPendingApply } = useDetailTemplateApply<Post>({
  currentPost,
  detailVisible,
  endpoint: (post) => `/gallery/posts/${post.id}/apply-context`,
  source: 'submissions',
  templateApplyStore,
  t
})
const submissionDetailStandardActions = computed(() => ({
  showDesktopReaction: true,
  showDesktopApply: true,
  showDesktopCopy: true,
  showMobileReaction: true,
  showMobileApply: true,
  showMobileCopy: true,
  desktopApplyPlacement: 'after' as const,
  desktopApplyInline: true,
  applyLabel: t('gallery.modal.apply_btn'),
  applyLoading: applying.value,
  copyLabel: t('my_posts.copy_prompt'),
  onLike: () => {
    if (currentPost.value) {
      void handleInteract(currentPost.value, 'like')
    }
  },
  onDislike: () => {
    if (currentPost.value) {
      void handleInteract(currentPost.value, 'dislike')
    }
  },
  onComment: () => {
    showCommentInput.value = true
  },
  onCopy: () => {
    if (currentPost.value) {
      void copyPrompt(currentPost.value)
    }
  },
  onApply: () => {
    void handleApply()
  },
}))
const {
  detailModalBindings: submissionDetailModalBindings,
  detailModalListeners: submissionDetailModalListeners,
} = useGalleryDetailModalAdapter({
  open: detailVisible,
  commentInputOpen: showCommentInput,
  newComment,
  currentPost,
  currentDetailMedia,
  hasPrev,
  hasNext,
  isMobile,
  title: () => t('gallery.modal.title'),
  noTagsText: () => t('my_notes.no_tags'),
  formatTag,
  comments,
  commentsLoading,
  commentsError,
  commentsPage,
  commentsTotal,
  commentsHasMore,
  submittingComment,
  standardActions: submissionDetailStandardActions,
  loadComments,
  loadMoreComments,
  submitComment,
  goPrev,
  goNext,
  infoContentClass:
    'p-4 lg:p-6 flex-1 flex flex-col overflow-y-auto scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent',
  desktopCloseButtonClass: 'z-10',
  commentsSectionClass:
    'mt-6 flex flex-col min-h-[200px] lg:flex-1 lg:max-h-none lg:overflow-hidden border-t border-slate-700 lg:border-slate-400/30 pt-4',
  mobileLeftClass: 'flex items-center gap-4',
  mobileRightClass: 'ml-2',
})

const { navigateToPage } = usePagedScrollNavigation({
  contentRef: layoutContentRef,
  goToPage: browserGoToPage
})

const goToPage = async (pageNumber: number) => {
  await navigateToPage(pageNumber)
}

const toggleStatus = async (post: Post) => {
  try {
    const newStatus = !post.is_active
    await api.put(`/gallery/posts/${post.id}/status`, null, {
      params: { is_active: newStatus },
    })
    post.is_active = newStatus
    message.success(newStatus ? t('my_notes.submission_published') : t('my_notes.submission_unpublished'))
  } catch (error: any) {
    if (error.response?.status === 404) {
      return
    }
    console.error(error)
    message.error(t('my_notes.action_failed'))
  }
}

const deletePost = async (post: Post) => {
  if (!window.confirm(t('my_notes.confirm_delete_submission'))) return

  try {
    await api.delete(`/gallery/posts/${post.id}`)
    posts.value = posts.value.filter((item) => item.id !== post.id)
    message.success(t('my_notes.delete_success'))
    if (currentPost.value?.id === post.id) {
      detailVisible.value = false
    }
  } catch (error: any) {
    if (error.response?.status === 404) {
      return
    }
    console.error(error)
    message.error(t('my_notes.delete_failed'))
  }
}

useScrollPrefetch(layoutContentRef, prefetchNextPage)

const handleImageError = (event: Event, post: Post) => {
  handleMediaCardImageError(event, post)
}

watch(
  () => props.taskType,
  () => {
    void loadPosts(true)
  },
  { immediate: true },
)

watch(
  detailVisible,
  (visible, previousVisible) => {
    if (!visible && previousVisible) {
      cancelPendingApply()
    }
  },
  { flush: 'sync' }
)

</script>

<template>
  <PostBrowserShell
    :loading="loading"
    :error-text="posts.length === 0 ? errorMessage : ''"
    :show-retry="posts.length === 0 && !!errorMessage"
    :empty="posts.length === 0"
    :empty-text="t('my_posts.no_submissions')"
    :retry-text="t('gallery.comments.retry')"
    @retry="loadPosts(true)"
  >
    <template #header>
      <StickyHeaderSection class-name="-mx-3 px-3 md:-mx-6 md:px-6 pb-2">
        <HeaderPaginationBar
          wrapper-class="flex justify-center"
          :current-page="currentPage"
          :total-pages="totalPages"
          :disabled="loading"
          :compact="isMobile"
          @change="goToPage"
        />
      </StickyHeaderSection>
    </template>

    <div class="columns-2 sm:columns-3 md:columns-4 lg:columns-5 gap-3 sm:gap-6 space-y-3 sm:space-y-6">
      <GalleryMediaCard
        v-for="post in posts"
        :key="post.id"
        :item="post"
        class="break-inside-avoid"
        media-container-class="relative w-full overflow-hidden bg-slate-500 aspect-auto min-h-[100px]"
        image-class="w-full h-auto object-cover transition-opacity duration-300"
        overlay-visibility-class="opacity-100 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity duration-300"
        @card-click="openDetail(post)"
        @image-error="handleImageError($event, post)"
      >
        <template #play-overlay>
          <div class="w-12 h-12 bg-black/50 backdrop-blur-md rounded-full flex items-center justify-center border border-white/20 shadow-lg">
            <Video :size="24" class="text-white" />
          </div>
        </template>
        <template #top-left>
          <div class="absolute top-2 left-2 flex items-center gap-2">
            <div
              class="bg-black/60 backdrop-blur-sm rounded-full px-2 py-1 shadow-sm border border-white/10 text-xs font-bold"
              :class="post.is_active ? 'text-green-400' : 'text-orange-400'"
            >
              {{ post.is_active ? t('my_posts.on_shelf') : t('my_posts.off_shelf') }}
            </div>
          </div>
        </template>
        <template #overlay>
          <div class="flex flex-col justify-between h-full">
            <div class="flex justify-end gap-2">
              <button
                @click.stop="toggleStatus(post)"
                class="p-2 rounded-full bg-black/50 hover:bg-black/80 text-white backdrop-blur-sm transition-all"
                :title="post.is_active ? t('my_posts.put_off_shelf') : t('my_posts.put_on_shelf')"
              >
                <Eye v-if="post.is_active" :size="16" class="text-green-400" />
                <EyeOff v-else :size="16" class="text-orange-400" />
              </button>
              <button
                @click.stop="deletePost(post)"
                class="p-2 rounded-full bg-black/50 hover:bg-red-500/80 text-white backdrop-blur-sm transition-all"
                :title="t('my_posts.delete')"
              >
                <Trash2 :size="16" />
              </button>
            </div>

            <PostTagPreview :tags="post.tags" :format-tag="formatTag" />
          </div>
        </template>
        <template #bottom>
          <PostCardMetricsBar
            :likes-count="post.likes_count"
            :dislikes-count="post.dislikes_count"
            :applied-count="post.applied_count"
            :has-liked="post.has_liked"
            :has-disliked="post.has_disliked"
            @like="handleInteract(post, 'like')"
            @dislike="handleInteract(post, 'dislike')"
          />
        </template>
      </GalleryMediaCard>
    </div>
  </PostBrowserShell>

    <GalleryDetailModal
      v-bind="submissionDetailModalBindings"
      v-on="submissionDetailModalListeners"
    >
      <template #before-comments-extra="{ post }">
        <div class="hidden lg:flex flex-col space-y-4 mb-4">
          <SubmissionManageButtons
            :is-active="post.is_active"
            :on-shelf-label="t('my_posts.put_on_shelf')"
            :off-shelf-label="t('my_posts.put_off_shelf')"
            :delete-label="t('my_posts.delete')"
            @toggle="toggleStatus(post)"
            @delete="deletePost(post)"
          />
        </div>
      </template>

      <template #after-comments-extra="{ post }">
        <div class="lg:hidden mt-auto pt-6 pb-2">
          <SubmissionManageButtons
            compact
            :is-active="post.is_active"
            :on-shelf-label="t('my_posts.put_on_shelf')"
            :off-shelf-label="t('my_posts.put_off_shelf')"
            :delete-label="t('my_posts.delete')"
            @toggle="toggleStatus(post)"
            @delete="deletePost(post)"
          />
        </div>
      </template>

    </GalleryDetailModal>
</template>
