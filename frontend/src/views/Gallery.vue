<script setup lang="ts">
import PostBrowserShell from '@/components/PostBrowserShell.vue'
import GalleryDetailContainer from '@/components/gallery/GalleryDetailContainer.vue'
import GalleryFiltersContainer from '@/components/gallery/GalleryFiltersContainer.vue'
import GalleryWaterfallContainer from '@/components/gallery/GalleryWaterfallContainer.vue'
import { useGalleryPageState } from '@/composables/useGalleryPageState'

const {
  GALLERY_LORA_MODEL_NONE,
  breakpoints,
  posts,
  loading,
  errorMessage,
  currentPage,
  totalPages,
  taskTypeTabs,
  taskType,
  timeRange,
  sortBy,
  hasAddonSubfilters,
  currentLoraModels,
  loraModel,
  isMobile,
  galleryDetailModalBindings,
  galleryDetailModalListeners,
  userProfileVisible,
  activeProfileUserId,
  followLoadingUserId,
  handleTaskTypeChange,
  handleTimeRangeChange,
  handleSortChange,
  handleLoraModelChange,
  goToPage,
  loadPosts,
  openDetail,
  openUserProfile,
  handleAuthorFollow,
  syncFollowStateForAuthor,
  handleImageError,
  handleInteract,
  handleWaterfallAfterRender,
  formatTag,
} = useGalleryPageState()
</script>

<template>
  <PostBrowserShell
    :loading="loading"
    :error-text="posts.length === 0 ? errorMessage : ''"
    :show-retry="posts.length === 0 && !!errorMessage"
    :empty="posts.length === 0"
    :empty-text="$t('gallery.no_posts')"
    :retry-text="$t('gallery.comments.retry')"
    @retry="loadPosts(true)"
  >
    <template #header>
      <GalleryFiltersContainer
        :task-type-tabs="taskTypeTabs"
        :task-type="taskType"
        :time-range="timeRange"
        :sort-by="sortBy"
        :has-addon-subfilters="hasAddonSubfilters"
        :current-lora-models="currentLoraModels"
        :lora-model="loraModel"
        :lora-model-none-value="GALLERY_LORA_MODEL_NONE"
        :current-page="currentPage"
        :total-pages="totalPages"
        :is-mobile="isMobile"
        :loading="loading"
        @task-type-change="handleTaskTypeChange"
        @time-range-change="handleTimeRangeChange"
        @sort-change="handleSortChange"
        @lora-model-change="handleLoraModelChange"
        @page-change="goToPage"
      />
    </template>

    <GalleryWaterfallContainer
      :posts="posts"
      :breakpoints="breakpoints"
      :is-mobile="isMobile"
      :format-tag="formatTag"
      @open-detail="openDetail"
      @image-error="handleImageError"
      @interact="handleInteract"
      @after-render="handleWaterfallAfterRender"
    />
  </PostBrowserShell>

  <GalleryDetailContainer
    :detail-bindings="galleryDetailModalBindings"
    :detail-listeners="galleryDetailModalListeners"
    :follow-loading-user-id="followLoadingUserId"
    :user-profile-visible="userProfileVisible"
    :active-profile-user-id="activeProfileUserId"
    @open-user-profile="openUserProfile"
    @author-follow="handleAuthorFollow"
    @update:user-profile-visible="userProfileVisible = $event"
    @follow-updated="syncFollowStateForAuthor($event.userId, $event.isFollowing)"
  />
</template>

<style>
.mobile-full-modal {
  padding: 0 !important;
  margin: 0 !important;
}
.mobile-full-modal .ant-modal {
  top: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
  height: 100vh !important;
  max-width: 100% !important;
}
.mobile-full-modal .ant-modal-content {
  border-radius: 0 !important;
  height: 100vh !important;
  overflow-y: auto !important;
  background-color: var(--detail-modal-shell-bg, var(--theme-card-strong-bg)) !important;
}
.mobile-full-modal .ant-modal-body {
  height: 100% !important;
}

/* Safe area support for iOS */
@supports (padding-bottom: env(safe-area-inset-bottom)) {
  .safe-area-bottom {
    padding-bottom: calc(0.75rem + env(safe-area-inset-bottom));
  }
}
</style>
