<script setup lang="ts">
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import {
  Copy,
  Eye,
  EyeOff,
  Heart,
  MessageCircle,
  ThumbsDown,
  Trash2,
  Video,
  Wand2,
} from 'lucide-vue-next'
import api from '@/api'
import { useViewport } from '@/composables/useViewport'
import { useMainLayoutContentRef } from '@/composables/useWorkbenchScrollLock'
import { useGalleryComments } from '@/composables/useGalleryComments'
import { usePagedPostBrowser } from '@/composables/usePagedPostBrowser'
import { useGalleryPostInteractions } from '@/composables/useGalleryPostInteractions'
import { useScrollPrefetch } from '@/composables/useScrollPrefetch'
import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'
import { handleMediaCardImageError } from '@/utils/mediaCardFallback'
import { resolveMediaCardView } from '@/utils/mediaCardView'
import { useLegacyTemplateApply } from '@/composables/useLegacyTemplateApply'
import { usePostPromptCopy } from '@/composables/usePostPromptCopy'
import { usePagedScrollNavigation } from '@/composables/usePagedScrollNavigation'
import { useCurrentDetailMedia } from '@/composables/useCurrentDetailMedia'
import { formatGalleryTag } from '@/utils/galleryPresentation'
import PagedNavigation from '@/components/PagedNavigation.vue'
import DetailDesktopActions from '@/components/DetailDesktopActions.vue'
import GalleryDetailModal from '@/components/GalleryDetailModal.vue'
import GalleryMediaCard from '@/components/GalleryMediaCard.vue'
import ListStateBlock from '@/components/ListStateBlock.vue'

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
const { saveApplyContext } = useGalleryApplyContext()

const { isMobile } = useViewport()
const { t } = useI18n()
const layoutContentRef = useMainLayoutContentRef()
const size = ref(20)
const {
  posts,
  loading,
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
const { copyPrompt } = usePostPromptCopy(t)
const { applying, applyFromCurrentPost } = useLegacyTemplateApply<Post>({
  currentPost,
  closeDetail: () => {
    detailVisible.value = false
  },
  saveApplyContext,
  t
})

const formatTag = (tag: string) => formatGalleryTag(tag, t)

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

const handleApply = async () => {
  await applyFromCurrentPost({
    endpoint: (post) => `/gallery/posts/${post.id}/apply-context`,
    source: 'submissions'
  })
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

</script>

<template>
  <div class="gallery-container text-slate-200">
    <div class="sticky top-0 z-40 -mx-3 px-3 md:-mx-6 md:px-6 pt-3 pb-2 mb-3">
      <div class="flex justify-center">
        <div class="rounded-2xl border border-slate-700/50 bg-slate-950/55 px-3 py-2 shadow-[0_6px_18px_rgba(2,6,23,0.25)]">
          <PagedNavigation
            :current-page="currentPage"
            :total-pages="totalPages"
            :disabled="loading"
            :compact="isMobile"
            @change="goToPage"
          />
        </div>
      </div>
    </div>

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

            <div class="flex flex-wrap gap-1.5 mb-8">
              <span
                v-for="tag in post.tags.slice(0, 4)"
                :key="tag"
                class="text-[10px] bg-cyan-500/20 border border-cyan-500/30 text-cyan-100 px-2 py-0.5 rounded-full backdrop-blur-md"
              >
                {{ formatTag(tag) }}
              </span>
              <span v-if="post.tags.length > 4" class="text-[10px] text-slate-300 px-1">...</span>
            </div>
          </div>
        </template>
        <template #bottom>
          <div class="absolute bottom-0 left-0 right-0 p-3 bg-black/60 backdrop-blur-md border-t border-white/10 flex justify-between items-center z-10 translate-y-0">
            <div class="flex items-center space-x-3">
              <div class="flex items-center text-slate-300 hover:text-pink-400 transition-colors" @click.stop="handleInteract(post, 'like')">
                <Heart :size="14" class="mr-1" :class="{ 'fill-pink-500 text-pink-500': post.has_liked }" />
                <span class="text-xs font-medium">{{ post.likes_count }}</span>
              </div>
              <div class="flex items-center text-slate-300 hover:text-slate-100 transition-colors" @click.stop="handleInteract(post, 'dislike')">
                <ThumbsDown :size="14" class="mr-1" :class="{ 'fill-slate-400 text-slate-400': post.has_disliked }" />
                <span class="text-xs font-medium">{{ post.dislikes_count }}</span>
              </div>
            </div>
            <div class="flex items-center text-indigo-300">
              <Wand2 :size="14" class="mr-1" />
              <span class="text-xs font-medium">{{ post.applied_count }}</span>
            </div>
          </div>
        </template>
      </GalleryMediaCard>
    </div>

    <ListStateBlock
      :loading="loading"
      :empty="posts.length === 0"
      :empty-text="t('my_posts.no_submissions')"
    />

    <GalleryDetailModal
      v-model:open="detailVisible"
      v-model:comment-input-open="showCommentInput"
      v-model:new-comment="newComment"
      :current-post="currentPost"
      :current-detail-media="currentDetailMedia"
      :has-prev="hasPrev"
      :has-next="hasNext"
      :is-mobile="isMobile"
      :title="t('gallery.modal.title')"
      :no-tags-text="t('my_notes.no_tags')"
      :format-tag="formatTag"
      :comments="comments"
      :comments-loading="commentsLoading"
      :comments-error="commentsError"
      :comments-page="commentsPage"
      :comments-total="commentsTotal"
      :comments-has-more="commentsHasMore"
      :submitting-comment="submittingComment"
      info-content-class="p-4 lg:p-6 flex-1 flex flex-col overflow-y-auto scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent"
      desktop-close-button-class="z-10"
      comments-section-class="mt-6 flex flex-col min-h-[200px] lg:flex-1 lg:max-h-none lg:overflow-hidden border-t border-slate-700 lg:border-slate-400/30 pt-4"
      mobile-left-class="flex items-center gap-4"
      mobile-right-class="ml-2"
      @prev="goPrev"
      @next="goNext"
      @retry-initial="currentPost && loadComments(currentPost.id, { page: 1, append: false })"
      @retry-more="loadMoreComments"
      @load-more="loadMoreComments"
      @submit-comment="submitComment"
    >
      <template #before-comments="{ post, openCommentInput }">
        <div class="hidden lg:flex flex-col space-y-4 mb-4 pt-4 border-t border-slate-700 lg:border-slate-400/30">
          <div class="flex space-x-2">
            <button @click="handleInteract(post, 'like')" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
              <Heart :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="post.has_liked ? 'fill-pink-500 text-pink-500' : 'text-slate-400 group-hover:text-pink-400'" />
              <span class="font-medium" :class="post.has_liked ? 'text-pink-400' : 'text-slate-300'">{{ post.likes_count }}</span>
            </button>
            <button @click="handleInteract(post, 'dislike')" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
              <ThumbsDown :size="20" class="mr-2 transition-transform group-hover:scale-110" :class="post.has_disliked ? 'fill-slate-400 text-slate-400' : 'text-slate-400 group-hover:text-slate-200'" />
              <span class="font-medium" :class="post.has_disliked ? 'text-slate-400' : 'text-slate-300'">{{ post.dislikes_count }}</span>
            </button>
            <button @click="openCommentInput()" class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500/50 hover:bg-slate-500 transition-all flex items-center justify-center group">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mr-2 transition-transform group-hover:scale-110 text-slate-400 group-hover:text-blue-400"><path d="m3 21 1.9-5.7a8.5 8.5 0 1 1 3.8 3.8z"/></svg>
              <span class="font-medium text-slate-300">{{ post.comments_count || 0 }}</span>
            </button>
          </div>

          <div class="flex space-x-2">
            <button
              @click="toggleStatus(post)"
              class="flex-1 py-3 rounded-xl border border-slate-400 bg-slate-500 hover:bg-slate-400 transition-all flex items-center justify-center text-sm font-medium"
              :class="post.is_active ? 'text-orange-400' : 'text-green-400'"
            >
              <EyeOff v-if="post.is_active" :size="18" class="mr-2" />
              <Eye v-else :size="18" class="mr-2" />
              {{ post.is_active ? t('my_posts.put_off_shelf') : t('my_posts.put_on_shelf') }}
            </button>
            <button
              @click="deletePost(post)"
              class="flex-1 py-3 rounded-xl border border-red-500/30 bg-red-500/10 hover:bg-red-500/20 transition-all flex items-center justify-center text-sm font-medium text-red-400 group"
            >
              <Trash2 :size="18" class="mr-2 transition-transform group-hover:scale-110" />
              {{ t('my_posts.delete') }}
            </button>
          </div>
        </div>
      </template>

      <template #after-comments="{ post }">
        <DetailDesktopActions container-class="mt-auto" bottom-class="pt-4 border-t border-slate-700 lg:border-slate-400/30">
          <template #bottom>
            <div class="flex space-x-2">
              <button
                v-if="post.prompt?.trim()"
                @click="copyPrompt(post)"
                class="flex-1 py-4 rounded-xl bg-slate-500 hover:bg-slate-400 text-white font-medium shadow-sm transition-all flex items-center justify-center border border-slate-400"
              >
                <Copy :size="18" class="mr-2" />
                {{ t('my_posts.copy_prompt') }}
              </button>
              <button
                @click="handleApply"
                :disabled="applying"
                class="flex-1 py-4 rounded-xl bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white font-bold text-lg shadow-[0_0_20px_rgba(56,189,248,0.4)] transition-all transform hover:scale-[1.02] flex items-center justify-center relative overflow-hidden group"
              >
                <div class="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300"></div>
                <Wand2 v-if="!applying" :size="22" class="mr-2 relative z-10" />
                <div v-else class="inline-block w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2 relative z-10"></div>
                <span class="relative z-10">{{ applying ? '...' : t('gallery.modal.apply_btn') }}</span>
              </button>
            </div>
          </template>
        </DetailDesktopActions>

        <div class="lg:hidden mt-auto pt-6 pb-2">
          <div class="flex space-x-3">
            <button
              @click="toggleStatus(post)"
              class="flex-1 py-2.5 rounded-lg border border-slate-700 bg-slate-800/80 transition-all flex items-center justify-center text-xs font-medium"
              :class="post.is_active ? 'text-orange-400' : 'text-green-400'"
            >
              <EyeOff v-if="post.is_active" :size="16" class="mr-1.5" />
              <Eye v-else :size="16" class="mr-1.5" />
              {{ post.is_active ? t('my_posts.put_off_shelf') : t('my_posts.put_on_shelf') }}
            </button>
            <button
              @click="deletePost(post)"
              class="flex-1 py-2.5 rounded-lg border border-red-900/50 bg-red-900/20 transition-all flex items-center justify-center text-xs font-medium text-red-400"
            >
              <Trash2 :size="16" class="mr-1.5" />
              {{ t('my_posts.delete') }}
            </button>
          </div>
        </div>
      </template>

      <template #mobile-left="{ post, openCommentInput }">
        <button @click="handleInteract(post, 'like')" class="flex items-center gap-1.5 transition-all" :class="post.has_liked ? 'text-pink-500' : 'text-slate-300'">
          <Heart :size="20" :class="{'fill-pink-500': post.has_liked}" />
          <span class="text-xs font-medium">{{ post.likes_count }}</span>
        </button>
        <button @click="handleInteract(post, 'dislike')" class="flex items-center gap-1.5 transition-all" :class="post.has_disliked ? 'text-slate-400' : 'text-slate-300'">
          <ThumbsDown :size="20" :class="{'fill-slate-400': post.has_disliked}" />
          <span class="text-xs font-medium">{{ post.dislikes_count }}</span>
        </button>
        <button @click="openCommentInput()" class="flex items-center gap-1.5 transition-all text-slate-300">
          <MessageCircle :size="20" />
          <span class="text-xs font-medium">{{ post.comments_count || 0 }}</span>
        </button>
        <button v-if="post.prompt?.trim()" @click="copyPrompt(post)" class="flex items-center gap-1.5 transition-all text-slate-300 ml-2">
          <Copy :size="20" />
        </button>
      </template>

      <template #mobile-right>
        <button
          @click="handleApply"
          :disabled="applying"
          class="px-5 py-2 rounded-full bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-sm shadow-lg flex items-center"
        >
          <Wand2 v-if="!applying" :size="16" class="mr-1.5" />
          <div v-else class="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-1.5"></div>
          {{ applying ? '...' : t('gallery.modal.apply_btn') }}
        </button>
      </template>
    </GalleryDetailModal>
  </div>
</template>
