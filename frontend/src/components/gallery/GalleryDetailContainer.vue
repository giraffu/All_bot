<script setup lang="ts">
import GalleryDetailModal from '@/components/GalleryDetailModal.vue'
import UserProfileModal from '@/components/UserProfileModal.vue'
import type { GalleryPost } from '@/types/gallery'
import { warnIfPropsExceedBudget } from '@/utils/componentPropsBudget'

const props = defineProps<{
  detailBindings: any
  detailListeners: any
  followLoadingUserId: number | null
  userProfileVisible: boolean
  activeProfileUserId: number | null
}>()

warnIfPropsExceedBudget('GalleryDetailContainer', Object.keys(props).length)

const emit = defineEmits<{
  (e: 'openUserProfile', userId?: number | null): void
  (e: 'authorFollow', post: GalleryPost): void
  (e: 'update:userProfileVisible', value: boolean): void
  (e: 'followUpdated', payload: { userId: number; isFollowing: boolean }): void
}>()
</script>

<template>
  <GalleryDetailModal
    v-bind="detailBindings"
    v-on="detailListeners"
  >
    <template #mobile-header="{ post }">
      <div class="gallery-author-mobile flex items-center justify-between gap-3 w-full">
        <button
          type="button"
          class="gallery-author-mobile__identity flex items-center gap-2 min-w-0"
          @click.stop="emit('openUserProfile', post.author_id)"
        >
          <div class="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-500 to-indigo-500 flex items-center justify-center text-white font-bold text-xs shrink-0">
            {{ post.author_name ? post.author_name.charAt(0).toUpperCase() : '修' }}
          </div>
          <span class="gallery-author-mobile__name font-semibold text-sm truncate">
            {{ post.author_name || $t('social.anonymous_user') }}
          </span>
        </button>
        <a-button
          v-if="post.author_id"
          type="primary"
          size="small"
          class="gallery-author-mobile__follow-btn shrink-0"
          :loading="followLoadingUserId === post.author_id"
          @click.stop="emit('authorFollow', post)"
        >
          {{ post.is_following_author ? $t('social.unfollow') : $t('social.follow') }}
        </a-button>
      </div>
    </template>

    <template #before-comments-extra="{ post }">
      <div class="gallery-author-card rounded-2xl p-4 mb-4">
        <div class="flex items-center justify-between gap-3">
          <button
            type="button"
            class="gallery-author-card__identity flex items-center gap-3 min-w-0"
            @click.stop="emit('openUserProfile', post.author_id)"
          >
            <div class="gallery-author-card__avatar w-11 h-11 rounded-2xl flex items-center justify-center text-white font-bold shrink-0">
              {{ post.author_name ? post.author_name.charAt(0).toUpperCase() : '修' }}
            </div>
            <div class="min-w-0 text-left">
              <div class="gallery-author-card__name text-sm font-semibold truncate">
                {{ post.author_name || $t('social.anonymous_user') }}
              </div>
              <div v-if="post.author_username" class="gallery-author-card__meta text-xs truncate">
                @{{ post.author_username }}
              </div>
            </div>
          </button>

          <a-button
            v-if="post.author_id"
            type="primary"
            class="gallery-author-card__follow-btn"
            :loading="followLoadingUserId === post.author_id"
            @click.stop="emit('authorFollow', post)"
          >
            {{ post.is_following_author ? $t('social.unfollow') : $t('social.follow') }}
          </a-button>
        </div>
      </div>
    </template>
  </GalleryDetailModal>

  <UserProfileModal
    :open="userProfileVisible"
    :user-id="activeProfileUserId"
    @update:open="emit('update:userProfileVisible', $event)"
    @follow-updated="emit('followUpdated', $event)"
  />
</template>

<style scoped>
.gallery-author-mobile__identity,
.gallery-author-card__identity {
  background: transparent;
  border: none;
  padding: 0;
}

.gallery-author-mobile__name,
.gallery-author-card__name {
  color: var(--theme-text-primary);
}

.gallery-author-card {
  background: var(--theme-card-strong-bg);
  border: 1px solid var(--theme-border);
}

.gallery-author-card__avatar {
  background: linear-gradient(135deg, #06b6d4, #4f46e5);
  box-shadow: 0 10px 20px rgba(79, 70, 229, 0.24);
}

.gallery-author-card__meta {
  color: var(--theme-text-secondary);
}

.gallery-author-mobile__follow-btn,
.gallery-author-card__follow-btn {
  background: linear-gradient(90deg, #2563eb, #4f46e5) !important;
  border: none !important;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.18);
}
</style>
