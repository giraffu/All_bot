<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

interface SiteNoticeItem {
  id: number
  title: string
  content: string
  is_active: boolean
  is_pinned: boolean
  published_at?: string | null
  updated_at?: string | null
}

const props = defineProps<{
  open: boolean
  notices: SiteNoticeItem[]
  selectedNoticeId: number | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'update:selectedNoticeId': [value: number | null]
}>()

const { t } = useI18n()

const selectedNotice = computed(() => {
  if (props.notices.length === 0) {
    return null
  }
  return props.notices.find((notice) => notice.id === props.selectedNoticeId) ?? props.notices[0]
})

const handleSelectNotice = (noticeId: number) => {
  emit('update:selectedNoticeId', noticeId)
}

const handleClose = () => {
  emit('update:open', false)
}

const formatTime = (value?: string | null) => {
  if (!value) {
    return t('site_notice.unknown_time')
  }
  return new Date(value).toLocaleString()
}

const previewContent = (content: string) => {
  const normalized = content.trim()
  if (normalized.length <= 48) {
    return normalized
  }
  return `${normalized.slice(0, 48)}...`
}

const previewTitle = (title: string) => {
  const normalized = title.trim()
  if (normalized.length <= 10) {
    return normalized
  }
  return `${normalized.slice(0, 10)}...`
}
</script>

<template>
  <a-modal
    :open="open"
    :title="t('site_notice.center_title')"
    :footer="null"
    :width="960"
    wrapClassName="site-notice-modal-wrap"
    destroyOnClose
    @cancel="handleClose"
  >
    <div v-if="notices.length > 0" class="site-notice-center">
      <aside class="site-notice-history">
        <div class="site-notice-history-title">{{ t('site_notice.history') }}</div>
        <button
          v-for="notice in notices"
          :key="notice.id"
          type="button"
          class="site-notice-history-item"
          :class="{ 'site-notice-history-item--active': selectedNotice?.id === notice.id }"
          @click="handleSelectNotice(notice.id)"
        >
          <div class="site-notice-history-head">
            <span class="site-notice-history-name" :title="notice.title">{{ previewTitle(notice.title) }}</span>
            <span v-if="notice.is_pinned" class="site-notice-history-pin">{{ t('site_notice.pinned') }}</span>
          </div>
          <div class="site-notice-history-time">{{ formatTime(notice.published_at || notice.updated_at) }}</div>
        </button>
      </aside>

      <section class="site-notice-detail">
        <template v-if="selectedNotice">
          <div class="site-notice-detail-head">
            <div>
              <div class="site-notice-detail-title">{{ selectedNotice.title }}</div>
              <div class="site-notice-detail-meta">
                <span>{{ t('site_notice.published_at') }}: {{ formatTime(selectedNotice.published_at || selectedNotice.updated_at) }}</span>
                <span v-if="selectedNotice.is_pinned" class="site-notice-detail-pin">{{ t('site_notice.pinned') }}</span>
              </div>
            </div>
          </div>
          <div class="site-notice-detail-content whitespace-pre-wrap">
            {{ selectedNotice.content }}
          </div>
        </template>
      </section>
    </div>

    <a-empty v-else :description="t('site_notice.empty')" />
  </a-modal>
</template>

<style>
.site-notice-modal-wrap {
  --notice-modal-surface: rgba(15, 23, 42, 0.96);
  --notice-modal-header: rgba(15, 23, 42, 0.96);
  --notice-modal-border: rgba(51, 65, 85, 0.95);
  --notice-modal-divider: rgba(71, 85, 105, 0.42);
  --notice-modal-shadow: 0 24px 60px rgba(2, 6, 23, 0.4);
  --notice-modal-title: #f8fafc;
  --notice-modal-text: #e2e8f0;
  --notice-modal-text-secondary: #cbd5e1;
  --notice-modal-text-muted: #94a3b8;
  --notice-history-item-bg: rgba(30, 41, 59, 0.9);
  --notice-history-item-hover-bg: rgba(51, 65, 85, 0.98);
  --notice-history-item-active-bg: rgba(250, 173, 20, 0.18);
  --notice-history-item-border: rgba(100, 116, 139, 0.4);
  --notice-history-item-active-border: rgba(250, 173, 20, 0.45);
  --notice-history-item-active-accent: #fbbf24;
  --notice-history-item-active-text: #fde68a;
  --notice-history-item-active-time: #fef3c7;
}

html[data-theme='light'] .site-notice-modal-wrap {
  --notice-modal-surface: rgba(255, 255, 255, 0.98);
  --notice-modal-header: rgba(255, 255, 255, 0.98);
  --notice-modal-border: rgba(203, 213, 225, 0.92);
  --notice-modal-divider: rgba(226, 232, 240, 0.96);
  --notice-modal-shadow: 0 24px 60px rgba(15, 23, 42, 0.14);
  --notice-modal-title: #0f172a;
  --notice-modal-text: #0f172a;
  --notice-modal-text-secondary: #334155;
  --notice-modal-text-muted: #64748b;
  --notice-history-item-bg: rgba(248, 250, 252, 0.98);
  --notice-history-item-hover-bg: rgba(241, 245, 249, 0.98);
  --notice-history-item-active-bg: rgba(254, 243, 199, 0.82);
  --notice-history-item-border: rgba(203, 213, 225, 0.95);
  --notice-history-item-active-border: rgba(245, 158, 11, 0.6);
  --notice-history-item-active-accent: #f59e0b;
  --notice-history-item-active-text: #b45309;
  --notice-history-item-active-time: #92400e;
}

.site-notice-modal-wrap .ant-modal-content {
  background-color: var(--notice-modal-surface) !important;
  background-image: linear-gradient(var(--notice-modal-surface), var(--notice-modal-surface)) !important;
  border: 1px solid var(--notice-modal-border) !important;
  box-shadow: var(--notice-modal-shadow) !important;
  color: var(--notice-modal-text) !important;
}

.site-notice-modal-wrap .ant-modal-header {
  background: var(--notice-modal-header) !important;
  border-bottom: none !important;
  padding-bottom: 6px !important;
}

.site-notice-modal-wrap .ant-modal-title {
  color: var(--notice-modal-title) !important;
}

.site-notice-modal-wrap .ant-modal-close {
  color: var(--notice-modal-text-muted) !important;
}

.site-notice-modal-wrap .ant-modal-close:hover {
  color: var(--notice-modal-title) !important;
}

.site-notice-modal-wrap .ant-modal-body {
  color: var(--notice-modal-text);
}
</style>

<style scoped>
.site-notice-center {
  display: grid;
  grid-template-columns: 168px minmax(0, 1fr);
  gap: 14px;
  min-height: 420px;
}

.site-notice-history {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-right: 6px;
  border-right: 1px solid var(--notice-modal-divider);
  overflow: auto;
}

.site-notice-history-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--notice-modal-text-secondary);
}

.site-notice-history-item {
  position: relative;
  width: 100%;
  text-align: left;
  border: 1px solid var(--notice-history-item-border);
  border-radius: 12px;
  padding: 10px 9px;
  background: var(--notice-history-item-bg);
  transition: border-color 0.2s ease, transform 0.2s ease, background 0.2s ease;
}

.site-notice-history-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 999px;
  background: transparent;
  transition: background 0.2s ease, box-shadow 0.2s ease;
}

.site-notice-history-item:hover,
.site-notice-history-item--active {
  border-color: var(--notice-history-item-active-border);
  background: var(--notice-history-item-active-bg);
  transform: translateY(-1px);
}

.site-notice-history-item--active {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--notice-history-item-active-border) 45%, transparent);
}

.site-notice-history-item--active::before {
  background: var(--notice-history-item-active-accent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--notice-history-item-active-accent) 28%, transparent);
}

.site-notice-history-item:hover:not(.site-notice-history-item--active) {
  background: var(--notice-history-item-hover-bg);
}

.site-notice-history-head {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.site-notice-history-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--notice-modal-title);
  line-height: 1.4;
  word-break: break-all;
}

.site-notice-history-item--active .site-notice-history-name {
  color: var(--notice-history-item-active-text);
}

.site-notice-history-pin,
.site-notice-detail-pin {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 2px 8px;
  background: rgba(250, 173, 20, 0.18);
  color: #fbbf24;
  font-size: 12px;
  font-weight: 600;
}

.site-notice-history-time {
  margin-top: 6px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--notice-modal-text-secondary);
  word-break: break-all;
}

.site-notice-history-item--active .site-notice-history-time {
  color: var(--notice-history-item-active-time);
  font-weight: 600;
}

.site-notice-detail {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.site-notice-detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--notice-modal-divider);
}

.site-notice-detail-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--notice-modal-title);
}

.site-notice-detail-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--notice-modal-text-secondary);
}

.site-notice-detail-content {
  flex: 1;
  margin-top: 16px;
  line-height: 1.8;
  color: var(--notice-modal-text);
  overflow: auto;
}

@media (max-width: 768px) {
  .site-notice-center {
    grid-template-columns: 116px minmax(0, 1fr);
    gap: 12px;
    min-height: 360px;
  }

  .site-notice-history {
    max-height: 100%;
    padding-right: 6px;
    border-right: 1px solid var(--notice-modal-divider);
    border-bottom: none;
  }

  .site-notice-history-item {
    padding: 9px 8px;
  }

  .site-notice-history-head {
    flex-direction: column;
    gap: 4px;
    align-items: flex-start;
  }

  .site-notice-history-name {
    font-size: 12px;
  }

  .site-notice-history-pin {
    padding: 1px 6px;
    font-size: 11px;
  }

  .site-notice-history-time {
    font-size: 10px;
  }

  .site-notice-detail-title {
    font-size: 18px;
  }

  .site-notice-detail-meta {
    font-size: 12px;
  }

  .site-notice-detail-content {
    font-size: 14px;
    line-height: 1.7;
  }
}
</style>
