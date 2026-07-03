<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { ExternalLink, Search, UserMinus, UserPlus, Users } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import {
  followUser,
  getMyFollowers,
  getMyFollowing,
  searchUsers,
  unfollowUser,
} from '@/api/social'
import { useViewport } from '@/composables/useViewport'
import type { PublicUserSummary } from '@/types/social'
import UserProfileModal from '@/components/UserProfileModal.vue'
import ProfileBackButton from '@/components/profile/ProfileBackButton.vue'

type SocialListMode = 'following' | 'followers' | 'search'

const props = withDefaults(
  defineProps<{
    open: boolean
    mode?: SocialListMode
  }>(),
  {
    mode: 'following',
  },
)

const emit = defineEmits<{
  'update:open': [value: boolean]
  followUpdated: [{ userId: number; isFollowing: boolean }]
}>()

const { t } = useI18n()
const { isMobile } = useViewport()

const loading = ref(false)
const errorText = ref('')
const items = ref<PublicUserSummary[]>([])
const profileOpen = ref(false)
const activeProfileUserId = ref<number | null>(null)
const actionLoadingUserId = ref<number | null>(null)
const searchQuery = ref('')
const searchHasRun = ref(false)

const isFollowersMode = computed(() => props.mode === 'followers')
const isSearchMode = computed(() => props.mode === 'search')
const modalTitle = computed(() => {
  if (isSearchMode.value) {
    return t('social.find_friends')
  }

  return isFollowersMode.value ? t('social.my_followers') : t('social.my_following')
})
const emptyText = computed(() => {
  if (errorText.value) {
    return errorText.value
  }

  if (isSearchMode.value) {
    return searchHasRun.value ? t('social.no_search_results') : t('social.search_idle')
  }

  return isFollowersMode.value ? t('social.no_followers') : t('social.no_following')
})

const loadSocialList = async () => {
  if (!props.open) {
    return
  }

  if (isSearchMode.value) {
    const query = searchQuery.value.trim()
    errorText.value = ''

    if (!query) {
      items.value = []
      searchHasRun.value = false
      return
    }

    loading.value = true
    searchHasRun.value = true
    try {
      const response = await searchUsers({ q: query, limit: 20 })
      items.value = response.items ?? []
    } catch (error) {
      console.error(error)
      items.value = []
      errorText.value = t('social.search_load_failed')
    } finally {
      loading.value = false
    }
    return
  }

  loading.value = true
  errorText.value = ''
  try {
    const response = isFollowersMode.value
      ? await getMyFollowers()
      : await getMyFollowing()
    items.value = response.items ?? []
  } catch (error) {
    console.error(error)
    errorText.value = isFollowersMode.value
      ? t('social.followers_load_failed')
      : t('social.following_load_failed')
  } finally {
    loading.value = false
  }
}

const updateItemFollowState = (userId: number, isFollowing: boolean) => {
  items.value = items.value.map((item) =>
    item.id === userId
      ? {
          ...item,
          is_following: isFollowing,
          followers_count: Math.max(
            0,
            item.followers_count + (isFollowing ? 1 : -1),
          ),
        }
      : item,
  )
}

const shouldUnfollowItem = (item: PublicUserSummary) =>
  props.mode === 'following' || item.is_following

const getFollowActionLabel = (item: PublicUserSummary) => {
  if (shouldUnfollowItem(item)) {
    return t('social.unfollow')
  }

  return props.mode === 'followers' ? t('social.follow_back') : t('social.follow')
}

const handleToggleFollow = async (item: PublicUserSummary) => {
  const shouldUnfollow = shouldUnfollowItem(item)
  actionLoadingUserId.value = item.id
  try {
    const response = shouldUnfollow
      ? await unfollowUser(item.id)
      : await followUser(item.id)

    if (props.mode === 'following' && !response.is_following) {
      items.value = items.value.filter((currentItem) => currentItem.id !== item.id)
    } else {
      updateItemFollowState(item.id, response.is_following)
    }

    emit('followUpdated', { userId: item.id, isFollowing: response.is_following })
    message.success(
      response.is_following ? t('social.follow_success') : t('social.unfollow_success'),
    )
  } catch (error) {
    console.error(error)
    message.error(t('social.follow_action_failed'))
  } finally {
    actionLoadingUserId.value = null
  }
}

const openUserProfile = (userId: number) => {
  activeProfileUserId.value = userId
  profileOpen.value = true
}

const handleSearch = () => {
  void loadSocialList()
}

const handleProfileFollowUpdated = (payload: { userId: number; isFollowing: boolean }) => {
  if (props.mode === 'following' && !payload.isFollowing) {
    items.value = items.value.filter((item) => item.id !== payload.userId)
  } else {
    updateItemFollowState(payload.userId, payload.isFollowing)
  }
  emit('followUpdated', payload)
}

const closeModal = () => {
  emit('update:open', false)
}

watch(
  () => [props.open, props.mode],
  ([isOpen]) => {
    if (isOpen) {
      void loadSocialList()
    } else {
      errorText.value = ''
      items.value = []
      searchQuery.value = ''
      searchHasRun.value = false
    }
  },
  { immediate: true },
)
</script>

<template>
  <a-modal
    :open="open"
    :footer="null"
    :closable="false"
    :width="isMobile ? '100%' : 760"
    :style="isMobile ? { top: 0, padding: 0, margin: 0, maxWidth: '100%' } : { top: '32px' }"
    class="profile-following-modal"
    destroyOnClose
    @update:open="emit('update:open', $event)"
  >
    <div class="profile-following-modal__panel p-5 sm:p-6">
      <div class="profile-following-modal__header mb-4">
        <ProfileBackButton :label="t('profile.back_to_profile')" @click="closeModal" />
        <div class="flex items-center gap-2 min-w-0">
          <Users :size="18" class="profile-following-modal__icon shrink-0" />
          <h3 class="profile-following-modal__title text-lg font-bold truncate">
            {{ modalTitle }}
          </h3>
        </div>
      </div>

      <form
        v-if="isSearchMode"
        class="profile-following-modal__search mb-4"
        @submit.prevent="handleSearch"
      >
        <label
          class="profile-following-modal__search-input-wrap"
          for="profile-user-search-input"
        >
          <Search :size="16" class="profile-following-modal__search-icon" />
          <input
            id="profile-user-search-input"
            v-model="searchQuery"
            data-testid="profile-user-search-input"
            class="profile-following-modal__search-input"
            type="search"
            :placeholder="t('social.search_placeholder')"
            autocomplete="off"
            @keydown.enter.prevent="handleSearch"
          />
        </label>
        <a-button
          data-testid="profile-user-search-submit"
          class="profile-following-modal__search-btn"
          :loading="loading"
          @click="handleSearch"
        >
          <span class="profile-following-modal__action-content">
            <Search :size="16" class="profile-following-modal__action-icon" />
            <span>{{ t('social.search') }}</span>
          </span>
        </a-button>
      </form>

      <a-spin :spinning="loading">
        <div v-if="items.length" class="space-y-3">
          <div
            v-for="item in items"
            :key="item.id"
            class="profile-following-modal__card rounded-2xl p-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
          >
            <div class="flex items-start gap-3">
              <button
                type="button"
                class="profile-following-modal__avatar w-12 h-12 rounded-xl flex items-center justify-center text-base font-bold shrink-0"
                @click="openUserProfile(item.id)"
              >
                {{ item.author_name.charAt(0).toUpperCase() }}
              </button>
              <div class="space-y-1">
                <button
                  type="button"
                  class="profile-following-modal__name text-left text-base font-semibold"
                  @click="openUserProfile(item.id)"
                >
                  {{ item.author_name }}
                </button>
                <div class="profile-following-modal__meta text-sm">
                  {{ item.current_identity }} · {{ item.user_group }} · {{ t('social.checkin_days') }} {{ item.checkin_count }}
                </div>
                <div class="profile-following-modal__meta text-xs">
                  {{ t('social.public_posts') }} {{ item.total_public_posts }} · {{ t('social.followers') }} {{ item.followers_count }}
                </div>
              </div>
            </div>

            <div class="profile-following-modal__actions">
              <a-button
                class="profile-following-modal__action-btn"
                @click="openUserProfile(item.id)"
              >
                <span class="profile-following-modal__action-content">
                  <ExternalLink :size="16" class="profile-following-modal__action-icon" />
                  <span>{{ t('social.open_profile') }}</span>
                </span>
              </a-button>
              <a-button
                class="profile-following-modal__action-btn"
                :danger="shouldUnfollowItem(item)"
                :loading="actionLoadingUserId === item.id"
                @click="handleToggleFollow(item)"
              >
                <span class="profile-following-modal__action-content">
                  <component
                    :is="shouldUnfollowItem(item) ? UserMinus : UserPlus"
                    :size="16"
                    class="profile-following-modal__action-icon"
                  />
                  <span>
                    {{ getFollowActionLabel(item) }}
                  </span>
                </span>
              </a-button>
            </div>
          </div>
        </div>

        <div
          v-else
          class="profile-following-modal__empty rounded-2xl p-8 text-center text-sm"
        >
          {{ emptyText }}
        </div>
      </a-spin>
    </div>

    <UserProfileModal
      v-model:open="profileOpen"
      :user-id="activeProfileUserId"
      @follow-updated="handleProfileFollowUpdated"
    />
  </a-modal>
</template>

<style scoped>
.profile-following-modal__header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-height: 2.625rem;
}

.profile-following-modal__panel {
  background: #0f172a;
}

.profile-following-modal__icon {
  color: #2563eb;
}

.profile-following-modal__title,
.profile-following-modal__name {
  color: var(--theme-text-primary);
}

.profile-following-modal__meta {
  color: var(--theme-text-secondary);
}

.profile-following-modal__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.profile-following-modal__search {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.625rem;
}

.profile-following-modal__search-input-wrap {
  display: flex;
  align-items: center;
  min-width: 0;
  height: 2.5rem;
  padding: 0 0.75rem;
  border: 1px solid var(--theme-border);
  border-radius: 0.5rem;
  background: var(--theme-card-strong-bg);
}

.profile-following-modal__search-icon {
  flex: 0 0 auto;
  margin-right: 0.5rem;
  color: var(--theme-text-secondary);
}

.profile-following-modal__search-input {
  min-width: 0;
  width: 100%;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--theme-text-primary);
}

.profile-following-modal__search-input::placeholder {
  color: var(--theme-text-secondary);
}

.profile-following-modal__search-btn {
  min-width: 5.5rem;
}

.profile-following-modal__card,
.profile-following-modal__empty {
  background: var(--theme-card-strong-bg);
  border: 1px solid var(--theme-border);
}

.profile-following-modal__action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
}

.profile-following-modal__action-content {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  line-height: 1;
}

.profile-following-modal__action-icon {
  flex-shrink: 0;
}

.profile-following-modal__avatar {
  background: linear-gradient(135deg, #06b6d4, #4f46e5);
  color: #fff;
  box-shadow: 0 10px 20px rgba(79, 70, 229, 0.22);
}

@media (max-width: 420px) {
  .profile-following-modal__search {
    grid-template-columns: minmax(0, 1fr);
  }

  .profile-following-modal__search-btn {
    width: 100%;
  }
}

:global(.profile-following-modal .ant-modal-content) {
  background-color: #0f172a !important;
  color: var(--theme-text-primary) !important;
}

:global(html[data-theme='light']) .profile-following-modal__panel {
  background: #ffffff;
}

:global(html[data-theme='light'] .profile-following-modal .ant-modal-content) {
  background-color: #ffffff !important;
}
</style>
