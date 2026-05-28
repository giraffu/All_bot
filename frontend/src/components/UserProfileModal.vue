<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { Flame, Heart, Layers3, Sparkles, UserPlus, UserMinus } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { followUser, getPublicUserProfile, unfollowUser } from '@/api/social'
import GalleryDetailModal from '@/components/GalleryDetailModal.vue'
import GalleryMediaCard from '@/components/GalleryMediaCard.vue'
import { useCurrentDetailMedia } from '@/composables/useCurrentDetailMedia'
import { useDetailTemplateApply } from '@/composables/useDetailTemplateApply'
import { useGalleryComments } from '@/composables/useGalleryComments'
import { useGalleryDetailModalAdapter } from '@/composables/useGalleryDetailModalAdapter'
import { useGalleryPostInteractions } from '@/composables/useGalleryPostInteractions'
import { usePostPromptCopy } from '@/composables/usePostPromptCopy'
import { useViewport } from '@/composables/useViewport'
import { useTemplateApplyStore } from '@/stores/templateApply'
import type { GalleryPost as Post } from '@/types/gallery'
import { resolveMediaCardView } from '@/utils/mediaCardView'
import { formatGalleryTag } from '@/utils/galleryPresentation'
import type { PublicUserProfileResponse } from '@/types/social'

const props = defineProps<{
  open: boolean
  userId: number | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  followUpdated: [{ userId: number; isFollowing: boolean }]
}>()

const { t } = useI18n()
const { isMobile } = useViewport()
const templateApplyStore = useTemplateApplyStore()

const loading = ref(false)
const followLoading = ref(false)
const errorText = ref('')
const profile = ref<PublicUserProfileResponse | null>(null)
const recentPosts = ref<Post[]>([])
const detailVisible = ref(false)
const currentPost = ref<Post | null>(null)

const currentIndex = computed(() => {
  if (!currentPost.value) {
    return -1
  }
  return recentPosts.value.findIndex((post) => post.id === currentPost.value?.id)
})

const hasPrev = computed(() => currentIndex.value > 0)
const hasNext = computed(
  () => currentIndex.value >= 0 && currentIndex.value < recentPosts.value.length - 1,
)

const displayPosts = computed(() => recentPosts.value)

const loadProfile = async () => {
  if (!props.open || !props.userId) {
    return
  }

  loading.value = true
  errorText.value = ''
  try {
    const response = await getPublicUserProfile(props.userId)
    profile.value = response
    recentPosts.value = (response.recent_posts || []).map((post) => {
      const cardView = resolveMediaCardView(post, {
        normalizeGalleryThumbnail: true,
      })
      return {
        ...post,
        src: cardView.initialSrc,
        cardIsVideo: cardView.isVideo,
        cardPoster: cardView.posterSrc,
      }
    })
  } catch (error) {
    console.error(error)
    errorText.value = t('social.profile_load_failed')
  } finally {
    loading.value = false
  }
}

const toggleFollow = async () => {
  const user = profile.value?.user
  if (!user || user.is_self) {
    return
  }

  followLoading.value = true
  try {
    const response = user.is_following
      ? await unfollowUser(user.id)
      : await followUser(user.id)
    const nextFollowing = response.is_following
    profile.value = profile.value
      ? {
          ...profile.value,
          user: {
            ...profile.value.user,
            is_following: nextFollowing,
            followers_count: Math.max(
              0,
              profile.value.user.followers_count + (nextFollowing ? 1 : -1),
            ),
          },
        }
      : profile.value
    emit('followUpdated', { userId: user.id, isFollowing: nextFollowing })
    message.success(
      nextFollowing ? t('social.follow_success') : t('social.unfollow_success'),
    )
  } catch (error) {
    console.error(error)
    message.error(t('social.follow_action_failed'))
  } finally {
    followLoading.value = false
  }
}

const currentDetailMedia = useCurrentDetailMedia(currentPost, {
  normalizeGalleryThumbnail: true,
})
const formatTag = (tag: string) => formatGalleryTag(tag, t)
const { copyPrompt } = usePostPromptCopy(t)
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
} = useGalleryComments(currentPost, recentPosts, detailVisible)
const { applying, handleApply } = useDetailTemplateApply<Post>({
  currentPost,
  detailVisible,
  itemId: (post) => post.id,
  source: 'gallery',
  templateApplyStore,
  t,
})
const detailStandardActions = computed(() => ({
  showDesktopReaction: true,
  showDesktopApply: true,
  showDesktopCopy: false,
  showMobileReaction: true,
  showMobileApply: true,
  showMobileCopy: false,
  showPromptPanelCopy: false,
  maskPromptText: true,
  promptVisibleRatio: 0.5,
  desktopApplyPlacement: 'before' as const,
  applyLabel: t('gallery.modal.apply_btn'),
  applyLoading: applying.value,
  applyHint: t('gallery.modal.apply_hint'),
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
  onApply: () => {
    void handleApply()
  },
  onCopy: () => {
    if (currentPost.value) {
      copyPrompt(currentPost.value)
    }
  },
}))
const {
  detailModalBindings,
  detailModalListeners,
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
  standardActions: detailStandardActions,
  loadComments,
  loadMoreComments,
  submitComment,
  goPrev: () => {
    if (currentIndex.value > 0) {
      currentPost.value = recentPosts.value[currentIndex.value - 1] ?? null
    }
  },
  goNext: () => {
    if (currentIndex.value >= 0 && currentIndex.value < recentPosts.value.length - 1) {
      currentPost.value = recentPosts.value[currentIndex.value + 1] ?? null
    }
  },
})

const openPostDetail = (post: Post) => {
  currentPost.value = post
  detailVisible.value = true
}

watch(
  () => [props.open, props.userId],
  () => {
    if (props.open && props.userId) {
      void loadProfile()
    } else if (!props.open) {
      profile.value = null
      recentPosts.value = []
      errorText.value = ''
    }
  },
  { immediate: true },
)
</script>

<template>
  <a-modal
    :open="open"
    :footer="null"
    :width="isMobile ? '100%' : 920"
    :style="isMobile ? { top: 0, padding: 0, margin: 0, maxWidth: '100%' } : { top: '32px' }"
    :bodyStyle="{ padding: 0 }"
    class="user-profile-modal"
    destroyOnClose
    @update:open="emit('update:open', $event)"
  >
    <div class="user-profile-modal__panel p-5 sm:p-6">
      <a-spin :spinning="loading">
        <div v-if="profile" class="space-y-5">
          <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div class="flex items-start gap-4">
              <div class="user-profile-modal__avatar w-14 h-14 rounded-2xl flex items-center justify-center text-xl font-bold shrink-0">
                {{ profile.user.author_name.charAt(0).toUpperCase() }}
              </div>
              <div class="space-y-2">
                <div>
                  <h3 class="user-profile-modal__name text-xl font-bold">
                    {{ profile.user.author_name }}
                  </h3>
                  <p v-if="profile.user.username" class="user-profile-modal__subtext text-sm">
                    @{{ profile.user.username }}
                  </p>
                </div>
                <div class="flex flex-wrap gap-2">
                  <span class="user-profile-modal__badge">{{ t('profile.identity') }}: {{ profile.user.current_identity }}</span>
                  <span class="user-profile-modal__badge">{{ t('profile.group') }}: {{ profile.user.user_group }}</span>
                  <span class="user-profile-modal__badge">{{ t('social.checkin_days') }}: {{ profile.user.checkin_count }}</span>
                </div>
              </div>
            </div>

            <a-button
              v-if="!profile.user.is_self"
              type="primary"
              size="large"
              class="user-profile-modal__follow-btn"
              :loading="followLoading"
              @click="toggleFollow"
            >
              <span class="user-profile-modal__follow-btn-content">
                <component
                  :is="profile.user.is_following ? UserMinus : UserPlus"
                  :size="16"
                  class="user-profile-modal__follow-btn-icon"
                />
                <span>{{ profile.user.is_following ? t('social.unfollow') : t('social.follow') }}</span>
              </span>
            </a-button>
          </div>

          <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div class="user-profile-modal__stat-card rounded-2xl p-4">
              <div class="user-profile-modal__stat-label text-xs">{{ t('social.public_posts') }}</div>
              <div class="user-profile-modal__stat-value text-lg font-bold flex items-center gap-2">
                <Layers3 :size="16" />
                {{ profile.user.total_public_posts }}
              </div>
            </div>
            <div class="user-profile-modal__stat-card rounded-2xl p-4">
              <div class="user-profile-modal__stat-label text-xs">{{ t('social.followers') }}</div>
              <div class="user-profile-modal__stat-value text-lg font-bold flex items-center gap-2">
                <Heart :size="16" />
                {{ profile.user.followers_count }}
              </div>
            </div>
            <div class="user-profile-modal__stat-card rounded-2xl p-4">
              <div class="user-profile-modal__stat-label text-xs">{{ t('social.following') }}</div>
              <div class="user-profile-modal__stat-value text-lg font-bold flex items-center gap-2">
                <UserPlus :size="16" />
                {{ profile.user.following_count }}
              </div>
            </div>
            <div class="user-profile-modal__stat-card rounded-2xl p-4">
              <div class="user-profile-modal__stat-label text-xs">{{ t('social.checkin_days') }}</div>
              <div class="user-profile-modal__stat-value text-lg font-bold flex items-center gap-2">
                <Flame :size="16" />
                {{ profile.user.checkin_count }}
              </div>
            </div>
          </div>

          <div class="space-y-3">
            <div class="flex items-center gap-2">
              <Sparkles :size="18" class="user-profile-modal__section-icon" />
              <h4 class="user-profile-modal__section-title text-lg font-semibold">
                {{ t('social.history_posts') }}
              </h4>
            </div>

            <div v-if="displayPosts.length" class="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <GalleryMediaCard
                v-for="post in displayPosts"
                :key="post.id"
                :item="post"
                :media-container-style="post.width && post.height ? { aspectRatio: `${post.width}/${post.height}` } : { aspectRatio: '1/1' }"
                overlay-visibility-class="opacity-100"
                @card-click="openPostDetail(post)"
              >
                <template #media>
                  <img
                    v-if="post.src"
                    :src="post.src"
                    class="w-full h-full object-cover absolute inset-0"
                    loading="lazy"
                  />
                  <div
                    v-else
                    class="absolute inset-0 flex items-center justify-center user-profile-modal__empty"
                  >
                    {{ t('social.no_media') }}
                  </div>
                </template>
                <template #overlay>
                  <div class="flex h-full items-end">
                    <div class="w-full flex items-center justify-between text-white text-xs">
                      <span>{{ post.task_type || post.media_type }}</span>
                      <span>{{ post.likes_count || 0 }} ❤</span>
                    </div>
                  </div>
                </template>
              </GalleryMediaCard>
            </div>

            <div v-else class="user-profile-modal__empty-state rounded-2xl p-6 text-center text-sm">
              {{ t('social.no_public_posts') }}
            </div>
          </div>
        </div>

        <div
          v-else-if="errorText"
          class="user-profile-modal__empty-state rounded-2xl p-8 text-center text-sm"
        >
          {{ errorText }}
        </div>
      </a-spin>
    </div>
  </a-modal>

  <GalleryDetailModal
    v-bind="detailModalBindings"
    v-on="detailModalListeners"
  />
</template>

<style scoped>
.user-profile-modal__panel {
  background: var(--theme-card-bg);
}

.user-profile-modal__avatar {
  background: linear-gradient(135deg, #06b6d4, #4f46e5);
  color: #fff;
  box-shadow: 0 12px 24px rgba(79, 70, 229, 0.24);
}

.user-profile-modal__name,
.user-profile-modal__section-title,
.user-profile-modal__stat-value {
  color: var(--theme-text-primary);
}

.user-profile-modal__subtext,
.user-profile-modal__stat-label {
  color: var(--theme-text-secondary);
}

.user-profile-modal__badge,
.user-profile-modal__stat-card,
.user-profile-modal__empty-state {
  background: var(--theme-card-strong-bg);
  border: 1px solid var(--theme-border);
  color: var(--theme-text-secondary);
}

.user-profile-modal__follow-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(90deg, #2563eb, #4f46e5) !important;
  border: none !important;
  box-shadow: 0 14px 28px rgba(59, 130, 246, 0.2);
  white-space: nowrap;
}

.user-profile-modal__follow-btn-content {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  line-height: 1;
}

.user-profile-modal__follow-btn-icon {
  flex-shrink: 0;
}

.user-profile-modal__section-icon {
  color: #2563eb;
}

.user-profile-modal__empty {
  color: var(--theme-text-muted);
}
</style>
