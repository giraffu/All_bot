<script setup lang="ts">
import { Clock, Globe, Palette, Wallet } from 'lucide-vue-next'
import type { ThemePreference } from '@/stores/theme'

defineProps<{
  fullName?: string | null
  username?: string | null
  userGroupLabel: string
  identityLabel: string
  identityExpireText: string
  credits: number
  localeValue: string
  selectedTheme: ThemePreference
  themeOptions: Array<{ label: string; value: ThemePreference }>
  checkinLoading: boolean
  onToggleLanguage: () => void
  onCheckin: () => void
}>()

const emit = defineEmits<{
  'update:selectedTheme': [value: ThemePreference]
}>()

const handleThemeChange = (value: ThemePreference) => {
  emit('update:selectedTheme', value)
}
</script>

<template>
  <div class="welcome-banner rounded-xl p-5 md:p-8 shadow-lg relative overflow-hidden">
    <div class="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center">
      <div class="w-full md:w-auto">
        <h1 class="welcome-title text-xl md:text-3xl font-bold mb-3 md:mb-2">
          {{ $t('profile.welcome_back', { name: username || fullName || '道友' }) }}
        </h1>

        <div class="flex flex-wrap items-center gap-2 mb-3 md:mb-2 text-sm md:text-lg">
          <div class="welcome-chip flex items-center rounded px-2.5 py-1">
            <span class="welcome-chip-label mr-1.5">{{ $t('profile.group') }}:</span>
            <span class="welcome-chip-value font-bold">{{ userGroupLabel }}</span>
          </div>
          <div class="welcome-chip flex items-center rounded px-2.5 py-1">
            <span class="welcome-chip-label mr-1.5">{{ $t('profile.identity') }}:</span>
            <span class="welcome-chip-value font-bold">{{ identityLabel }}</span>
          </div>
          <button
            class="welcome-action-button flex items-center rounded px-2.5 py-1 cursor-pointer transition-all"
            @click="onToggleLanguage"
          >
            <Globe :size="16" class="welcome-action-icon mr-1.5" />
            <span class="welcome-action-text font-bold text-sm">
              {{ localeValue === 'zh' ? 'English' : '中文' }}
            </span>
          </button>
          <div class="theme-switcher welcome-action-button flex items-center rounded px-2 py-1 transition-all">
            <Palette :size="16" class="theme-switcher-icon welcome-action-icon mr-1.5 shrink-0" />
            <a-select
              :value="selectedTheme"
              size="small"
              class="theme-select"
              :options="themeOptions"
              :bordered="false"
              :popupClassName="'app-theme-overlay'"
              :aria-label="$t('theme.switcher_label')"
              @update:value="handleThemeChange"
            />
          </div>
        </div>

        <div class="welcome-expire text-xs md:text-sm flex items-center">
          <Clock :size="14" class="welcome-expire-icon mr-1.5" />
          <span>{{ identityExpireText }}</span>
        </div>
      </div>

      <div class="welcome-side mt-5 md:mt-0 w-full md:w-auto flex flex-col items-end gap-3 pt-4 md:pt-0">
        <div class="welcome-wallet-card flex items-center px-4 py-2 md:px-5 md:py-3 rounded-lg shadow-inner w-full md:w-auto justify-between md:justify-start">
          <div class="flex items-center">
            <Wallet :size="20" class="welcome-wallet-icon mr-2 md:mr-3" />
            <div class="flex flex-col">
              <span class="welcome-credits-label text-[10px] md:text-xs font-medium leading-none mb-1">{{ $t('profile.credits') }}</span>
              <span class="welcome-credits-value text-lg md:text-2xl font-bold leading-none">{{ credits }}</span>
            </div>
          </div>
        </div>
        <a-button
          type="primary"
          :loading="checkinLoading"
          class="welcome-checkin-btn border-none font-bold px-6 w-full shadow-lg transition-all transform hover:-translate-y-0.5 h-10 md:h-auto z-50 pointer-events-auto"
          @click="onCheckin"
        >
          {{ $t('profile.checkin_btn') }}
        </a-button>
      </div>
    </div>

    <div class="absolute -top-24 -right-24 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none"></div>
    <div class="absolute -bottom-24 right-12 w-48 h-48 bg-cyan-500/10 rounded-full blur-2xl pointer-events-none"></div>
  </div>
</template>

<style scoped>
.welcome-banner {
  --banner-bg: linear-gradient(135deg, rgba(79, 70, 229, 0.92), rgba(168, 85, 247, 0.9), rgba(6, 182, 212, 0.86));
  --banner-border: rgba(129, 140, 248, 0.4);
  --banner-title: #f8fafc;
  --banner-chip-bg: rgba(255, 255, 255, 0.08);
  --banner-chip-border: rgba(255, 255, 255, 0.14);
  --banner-chip-label: rgba(226, 232, 240, 0.82);
  --banner-chip-value: #a5f3fc;
  --banner-action-bg: rgba(8, 145, 178, 0.12);
  --banner-action-bg-hover: rgba(8, 145, 178, 0.2);
  --banner-action-border: rgba(34, 211, 238, 0.3);
  --banner-action-text: #a5f3fc;
  --banner-expire: rgba(226, 232, 240, 0.82);
  --banner-expire-icon: rgba(148, 163, 184, 0.95);
  --banner-side-border: rgba(255, 255, 255, 0.18);
  --banner-wallet-bg: rgba(255, 255, 255, 0.18);
  --banner-wallet-border: rgba(255, 255, 255, 0.26);
  --banner-wallet-icon: #cffafe;
  --banner-credits-label: rgba(226, 232, 240, 0.82);
  --banner-credits-value: #f8fafc;
  --banner-checkin-bg: linear-gradient(90deg, #6366f1, #0891b2);
  --banner-checkin-bg-hover: linear-gradient(90deg, #4f46e5, #0e7490);
  background: var(--banner-bg);
  border: 1px solid var(--banner-border);
}

:global(html[data-theme='light']) .welcome-banner {
  --banner-bg: linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(239, 246, 255, 0.96), rgba(224, 242, 254, 0.95));
  --banner-border: rgba(125, 211, 252, 0.45);
  --banner-title: #0f172a;
  --banner-chip-bg: rgba(255, 255, 255, 0.72);
  --banner-chip-border: rgba(148, 163, 184, 0.24);
  --banner-chip-label: #475569;
  --banner-chip-value: #0369a1;
  --banner-action-bg: rgba(255, 255, 255, 0.88);
  --banner-action-bg-hover: rgba(224, 242, 254, 0.98);
  --banner-action-border: rgba(56, 189, 248, 0.3);
  --banner-action-text: #0f766e;
  --banner-expire: #475569;
  --banner-expire-icon: #64748b;
  --banner-side-border: rgba(148, 163, 184, 0.24);
  --banner-wallet-bg: rgba(255, 255, 255, 0.92);
  --banner-wallet-border: rgba(148, 163, 184, 0.24);
  --banner-wallet-icon: #0891b2;
  --banner-credits-label: #64748b;
  --banner-credits-value: #0f172a;
  --banner-checkin-bg: linear-gradient(90deg, #2563eb, #0891b2);
  --banner-checkin-bg-hover: linear-gradient(90deg, #1d4ed8, #0e7490);
}

.welcome-title {
  color: var(--banner-title);
  text-shadow: 0 2px 12px rgba(15, 23, 42, 0.12);
}

.welcome-chip {
  background: var(--banner-chip-bg);
  border: 1px solid var(--banner-chip-border);
  backdrop-filter: blur(10px);
}

.welcome-chip-label {
  color: var(--banner-chip-label);
}

.welcome-chip-value {
  color: var(--banner-chip-value);
}

.welcome-action-button {
  background: var(--banner-action-bg);
  border: 1px solid var(--banner-action-border);
  backdrop-filter: blur(10px);
}

.welcome-action-button:hover {
  background: var(--banner-action-bg-hover);
}

.welcome-action-icon,
.theme-switcher-icon {
  color: var(--banner-action-text);
}

.welcome-action-text {
  color: var(--banner-action-text);
}

.welcome-expire {
  color: var(--banner-expire);
}

.welcome-expire-icon {
  color: var(--banner-expire-icon);
}

.welcome-side {
  border-top: 1px solid var(--banner-side-border);
}

.welcome-wallet-card {
  background: var(--banner-wallet-bg);
  border: 1px solid var(--banner-wallet-border);
  backdrop-filter: blur(12px);
}

.welcome-wallet-icon {
  color: var(--banner-wallet-icon);
  filter: drop-shadow(0 0 8px rgba(6, 182, 212, 0.28));
}

.welcome-credits-label {
  color: var(--banner-credits-label);
}

.welcome-credits-value {
  color: var(--banner-credits-value);
}

.welcome-checkin-btn {
  background: var(--banner-checkin-bg) !important;
  color: #fff !important;
}

.welcome-checkin-btn:hover,
.welcome-checkin-btn:focus {
  background: var(--banner-checkin-bg-hover) !important;
}

.theme-switcher {
  min-width: 118px;
}

:deep(.theme-select) {
  min-width: 0;
  width: 100%;
}

:deep(.theme-select .ant-select-selector) {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
}

:deep(.theme-select .ant-select-selection-item),
:deep(.theme-select .ant-select-selection-placeholder) {
  color: var(--banner-action-text) !important;
  font-weight: 700;
  font-size: 0.875rem !important;
}

:deep(.theme-select .ant-select-arrow) {
  color: var(--banner-action-text) !important;
}

@media (min-width: 768px) {
  .welcome-side {
    border-top: 0;
  }
}
</style>
