<script setup lang="ts">
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { ExternalLink, UserMinus, Users } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { getMyFollowing, unfollowUser } from '@/api/social'
import { useViewport } from '@/composables/useViewport'
import type { PublicUserSummary } from '@/types/social'
import UserProfileModal from '@/components/UserProfileModal.vue'

const props = defineProps<{
  open: boolean
}>()

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
const unfollowingUserId = ref<number | null>(null)

const loadFollowing = async () => {
  if (!props.open) {
    return
  }

  loading.value = true
  errorText.value = ''
  try {
    const response = await getMyFollowing()
    items.value = response.items
  } catch (error) {
    console.error(error)
    errorText.value = t('social.following_load_failed')
  } finally {
    loading.value = false
  }
}

const handleUnfollow = async (userId: number) => {
  unfollowingUserId.value = userId
  try {
    await unfollowUser(userId)
    items.value = items.value.filter((item) => item.id !== userId)
    emit('followUpdated', { userId, isFollowing: false })
    message.success(t('social.unfollow_success'))
  } catch (error) {
    console.error(error)
    message.error(t('social.follow_action_failed'))
  } finally {
    unfollowingUserId.value = null
  }
}

const openUserProfile = (userId: number) => {
  activeProfileUserId.value = userId
  profileOpen.value = true
}

const handleProfileFollowUpdated = (payload: { userId: number; isFollowing: boolean }) => {
  if (!payload.isFollowing) {
    items.value = items.value.filter((item) => item.id !== payload.userId)
  }
  emit('followUpdated', payload)
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      void loadFollowing()
    } else {
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
    :width="isMobile ? '100%' : 760"
    :style="isMobile ? { top: 0, padding: 0, margin: 0, maxWidth: '100%' } : { top: '32px' }"
    class="profile-following-modal"
    destroyOnClose
    @update:open="emit('update:open', $event)"
  >
    <div class="profile-following-modal__panel p-5 sm:p-6">
      <div class="flex items-center gap-2 mb-4">
        <Users :size="18" class="profile-following-modal__icon" />
        <h3 class="profile-following-modal__title text-lg font-bold">
          {{ t('social.my_following') }}
        </h3>
      </div>

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
                danger
                :loading="unfollowingUserId === item.id"
                @click="handleUnfollow(item.id)"
              >
                <span class="profile-following-modal__action-content">
                  <UserMinus :size="16" class="profile-following-modal__action-icon" />
                  <span>{{ t('social.unfollow') }}</span>
                </span>
              </a-button>
            </div>
          </div>
        </div>

        <div
          v-else
          class="profile-following-modal__empty rounded-2xl p-8 text-center text-sm"
        >
          {{ errorText || t('social.no_following') }}
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
.profile-following-modal__panel {
  background: var(--theme-card-bg);
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
</style>
