<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchSiteNoticeCenter } from '@/api'
import SiteNoticeCenterModal from '@/components/SiteNoticeCenterModal.vue'

interface SiteNoticeItem {
  id: number
  title: string
  content: string
  is_active: boolean
  is_pinned: boolean
  published_at?: string | null
  updated_at?: string | null
}

interface SiteNoticeCenterPayload {
  featured_notice: SiteNoticeItem | null
  notices: SiteNoticeItem[]
}

const { t } = useI18n()

const centerData = ref<SiteNoticeCenterPayload>({
  featured_notice: null,
  notices: [],
})
const modalOpen = ref(false)
const selectedNoticeId = ref<number | null>(null)
const dismissedVersions = ref<Record<string, string>>({})
const storageKey = 'allbot.siteNotice.dismissedVersions'

const notices = computed(() => centerData.value.notices ?? [])
const featuredNotice = computed(() => centerData.value.featured_notice)
const currentNoticeVersion = computed(
  () => featuredNotice.value?.updated_at ?? featuredNotice.value?.published_at ?? 'active'
)

const featuredVisible = computed(() => {
  if (!featuredNotice.value?.is_active) {
    return false
  }
  if (!featuredNotice.value.content.trim()) {
    return false
  }
  const dismissedVersion = dismissedVersions.value[String(featuredNotice.value.id)]
  return dismissedVersion !== currentNoticeVersion.value
})

const featuredPreview = computed(() => {
  const content = featuredNotice.value?.content.trim() ?? ''
  if (content.length <= 96) {
    return content
  }
  return `${content.slice(0, 96)}...`
})

const loadDismissedVersions = () => {
  if (typeof window === 'undefined') {
    return
  }
  try {
    dismissedVersions.value = JSON.parse(window.localStorage.getItem(storageKey) || '{}')
  } catch {
    dismissedVersions.value = {}
  }
}

const persistDismissedVersions = () => {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(storageKey, JSON.stringify(dismissedVersions.value))
}

const dismissNotice = () => {
  if (!featuredNotice.value) {
    return
  }
  dismissedVersions.value = {
    ...dismissedVersions.value,
    [String(featuredNotice.value.id)]: currentNoticeVersion.value,
  }
  persistDismissedVersions()
}

const openCenter = (noticeId?: number | null) => {
  if (notices.value.length === 0) {
    return
  }
  selectedNoticeId.value = noticeId ?? featuredNotice.value?.id ?? notices.value[0]?.id ?? null
  modalOpen.value = true
}

const loadNoticeCenter = async () => {
  try {
    const payload = await fetchSiteNoticeCenter()
    centerData.value = {
      featured_notice: payload.featured_notice ?? null,
      notices: payload.notices ?? [],
    }
    if (!selectedNoticeId.value && payload.featured_notice?.id) {
      selectedNoticeId.value = payload.featured_notice.id
    } else if (
      selectedNoticeId.value
      && !centerData.value.notices.some((notice) => notice.id === selectedNoticeId.value)
    ) {
      selectedNoticeId.value = centerData.value.notices[0]?.id ?? null
    }
  } catch {
    centerData.value = {
      featured_notice: null,
      notices: [],
    }
  }
}

onMounted(() => {
  loadDismissedVersions()
  void loadNoticeCenter()
})
</script>

<template>
  <div v-if="notices.length > 0">
    <div v-if="featuredVisible" class="site-notice-wrap px-2 pt-2 md:px-6 md:pt-4">
      <a-alert type="info" banner show-icon closable @close="dismissNotice">
        <template #message>
          <div class="site-notice-header">
            <div class="site-notice-title">
              <span class="text-sm font-semibold">{{ featuredNotice?.title || t('site_notice.label') }}</span>
              <span v-if="featuredNotice?.is_pinned" class="site-notice-pin">{{ t('site_notice.pinned') }}</span>
            </div>
            <a-button type="link" size="small" class="site-notice-open" @click.stop="openCenter(featuredNotice?.id)">
              {{ t('site_notice.open') }}
            </a-button>
          </div>
        </template>
        <template #description>
          <div class="site-notice-content whitespace-pre-wrap">
            {{ featuredPreview }}
          </div>
        </template>
      </a-alert>
    </div>

    <div v-else class="site-notice-minibar px-2 pt-2 md:px-6 md:pt-4">
      <a-button type="link" class="site-notice-minibar-button" @click="openCenter()">
        {{ t('site_notice.open_history', { count: notices.length }) }}
      </a-button>
    </div>

    <SiteNoticeCenterModal
      v-model:open="modalOpen"
      v-model:selectedNoticeId="selectedNoticeId"
      :notices="notices"
    />
  </div>
</template>

<style scoped>
.site-notice-wrap :deep(.ant-alert) {
  border: 1px solid rgba(250, 173, 20, 0.26);
  border-radius: 16px;
  background:
    linear-gradient(135deg, rgba(250, 173, 20, 0.18), rgba(255, 255, 255, 0.08)),
    var(--theme-panel-bg);
  box-shadow: var(--theme-shadow);
}

.site-notice-wrap :deep(.ant-alert-message),
.site-notice-wrap :deep(.ant-alert-description),
.site-notice-wrap :deep(.ant-alert-icon),
.site-notice-wrap :deep(.ant-alert-close-icon) {
  color: var(--theme-text-primary);
}

.site-notice-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.site-notice-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.site-notice-pin {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 2px 8px;
  background: rgba(250, 173, 20, 0.16);
  color: #fbbf24;
  font-size: 12px;
  font-weight: 600;
}

.site-notice-open {
  padding-inline: 0;
  color: var(--theme-text-primary);
}

.site-notice-content {
  margin-top: 4px;
  line-height: 1.6;
}

.site-notice-minibar {
  display: flex;
  justify-content: flex-end;
}

.site-notice-minibar-button {
  padding-inline: 0;
  color: var(--theme-text-secondary);
}
</style>
