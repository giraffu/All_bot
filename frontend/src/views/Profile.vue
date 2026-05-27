<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore, type ThemePreference } from '@/stores/theme'
import { 
  Wallet,
  Activity,
  CalendarCheck,
  Zap,
  Award,
  User,
  Lock,
} from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { useViewport } from '@/composables/useViewport'
import { useTelegram } from '@/composables/useTelegram'
import { useI18n } from 'vue-i18n'
import { useQueueStatus } from '@/composables/useQueueStatus'
import { useBindPassword } from '@/composables/useBindPassword'
import { useAffiliateRedeem } from '@/composables/useAffiliateRedeem'
import { useProfileMetrics } from '@/composables/useProfileMetrics'
import { useProfileLanguage } from '@/composables/useProfileLanguage'
import { useProfileQuickActions } from '@/composables/useProfileQuickActions'
import { useProfileWelcomeSummary } from '@/composables/useProfileWelcomeSummary'
import { useDailyCheckin } from '@/composables/useDailyCheckin'
import ProfilePasswordOverlay from '@/components/profile/ProfilePasswordOverlay.vue'
import ProfileMetricCards from '@/components/profile/ProfileMetricCards.vue'
import ProfileQuickActionsPanel from '@/components/profile/ProfileQuickActionsPanel.vue'
import ProfileQueueStatusPanel from '@/components/profile/ProfileQueueStatusPanel.vue'
import ProfileRedeemOverlays from '@/components/profile/ProfileRedeemOverlays.vue'
import ProfileWelcomeBanner from '@/components/profile/ProfileWelcomeBanner.vue'

const authStore = useAuthStore()
const themeStore = useThemeStore()
const router = useRouter()
const { isMobile } = useViewport()
const { showMainButton, hideMainButton, hapticFeedback, isTMA } = useTelegram()
const { t, te, locale } = useI18n()
const { queueStatus, fetchQueueStatus } = useQueueStatus()
const { toggleLanguage } = useProfileLanguage(locale as { value: string })
const themeOptions = computed<{ label: string; value: ThemePreference }[]>(() => [
  { label: t('theme.system'), value: 'system' },
  { label: t('theme.light'), value: 'light' },
  { label: t('theme.dark'), value: 'dark' },
])

const selectedTheme = computed<ThemePreference>({
  get: () => themeStore.selectedTheme,
  set: (value) => themeStore.setTheme(value),
})

const {
  bindFormState,
  bindingLoading,
  showBindModal,
  handleBindPassword,
  handleBindPasswordModalOpen
} = useBindPassword({
  isMobile,
  user: computed(() => authStore.user),
  onPasswordBound: async () => {
    authStore.logout()
    await router.push({
      path: '/login',
      query: { mode: 'password', from: 'bind-password' }
    })
  },
  showMainButton,
  hideMainButton,
  hapticFeedback
})

const currentUser = computed(() => authStore.user)
const { identityExpireText, userGroupLabel, identityLabel } = useProfileWelcomeSummary({
  user: currentUser,
  t,
})

const resolveQueueTaskTypeLabel = (type: string | number) => {
  const normalizedType = String(type).replace(/-/g, '_')
  const taskTypeKey = `task_type.${normalizedType}`
  if (te(taskTypeKey)) {
    return t(taskTypeKey)
  }

  const taskKey = `task.${normalizedType}`
  if (te(taskKey)) {
    return t(taskKey)
  }

  return normalizedType
}

const { checkinLoading, handleCheckin } = useDailyCheckin({
  refreshUser: authStore.fetchUser
})
const {
  redeemCreditsLoading,
  redeemMembershipLoading,
  showRedeemCreditsModal,
  showRedeemMembershipModal,
  redeemCreditsForm,
  redeemMembershipForm,
  redeemCreditsPackages,
  membershipRedeemOptions,
  availableCommissionUsdt,
  totalCommissionUsdt,
  spentCommissionUsdt,
  openRedeemCreditsModal,
  openRedeemMembershipModal,
  handleRedeemCredits,
  handleRedeemMembership
} = useAffiliateRedeem({
  user: currentUser,
  refreshUser: authStore.fetchUser
})

const { statsCards, promotionCards } = useProfileMetrics({
  user: currentUser,
  t,
  totalCommissionUsdt,
  spentCommissionUsdt,
  availableCommissionUsdt,
  icons: {
    User,
    Zap,
    CalendarCheck,
    Award,
    Activity,
    Wallet
  }
})

const { quickActions } = useProfileQuickActions({
  user: currentUser,
  t,
  router,
  openRedeemCreditsModal,
  openRedeemMembershipModal,
  handleBindPasswordModalOpen,
  icons: {
    Wallet,
    Award,
    Lock,
  },
})

onMounted(async () => {
  await authStore.fetchUser()
  fetchQueueStatus()
})
</script>

<template>
  <div class="profile-container space-y-6">
    <ProfileWelcomeBanner
      :full-name="authStore.user?.full_name"
      :username="authStore.user?.username"
      :user-group-label="userGroupLabel"
      :identity-label="identityLabel"
      :identity-expire-text="identityExpireText"
      :credits="authStore.user?.credits || 0"
      :locale-value="locale"
      v-model:selected-theme="selectedTheme"
      :theme-options="themeOptions"
      :checkin-loading="checkinLoading"
      :on-toggle-language="toggleLanguage"
      :on-checkin="handleCheckin"
    />

    <ProfileQuickActionsPanel
      :title="$t('profile.quick_guide')"
      :description="$t('profile.quick_guide_desc')"
      :actions="quickActions"
    />

    <ProfileQueueStatusPanel
      :queue-status="queueStatus"
      :resolve-queue-task-type-label="resolveQueueTaskTypeLabel"
      :fetch-queue-status="fetchQueueStatus"
    />

    <div>
      <h2 class="profile-section-title text-xl font-bold mb-4 flex items-center drop-shadow-sm">
        <span class="w-1.5 h-6 bg-cyan-500 rounded-full mr-2 shadow-[0_0_8px_rgba(56,189,248,0.5)]"></span>
        {{ $t('profile.stats') }}
      </h2>
      
      <ProfileMetricCards :items="statsCards" :icon-size="isMobile ? 20 : 24" />
    </div>
    
    <div class="mt-8">
      <h2 class="profile-section-title text-xl font-bold mb-4 flex items-center drop-shadow-sm">
        <span class="w-1.5 h-6 bg-indigo-500 rounded-full mr-2 shadow-[0_0_8px_rgba(99,102,241,0.5)]"></span>
        {{ $t('profile.promotion_details') }}
      </h2>
      
      <ProfileMetricCards :items="promotionCards" :icon-size="isMobile ? 20 : 24" />
    </div>

    <ProfileRedeemOverlays
      :is-mobile="isMobile"
      v-model:show-redeem-credits-modal="showRedeemCreditsModal"
      v-model:show-redeem-membership-modal="showRedeemMembershipModal"
      :redeem-credits-loading="redeemCreditsLoading"
      :redeem-membership-loading="redeemMembershipLoading"
      :redeem-credits-form="redeemCreditsForm"
      :redeem-membership-form="redeemMembershipForm"
      :redeem-credits-packages="redeemCreditsPackages"
      :membership-redeem-options="membershipRedeemOptions"
      :available-commission-usdt="availableCommissionUsdt"
      :handle-redeem-credits="handleRedeemCredits"
      :handle-redeem-membership="handleRedeemMembership"
    />

    <ProfilePasswordOverlay
      :is-mobile="isMobile"
      :is-t-m-a="isTMA"
      v-model:show-bind-modal="showBindModal"
      :binding-loading="bindingLoading"
      :username="authStore.user?.username"
      :bind-form-state="bindFormState"
      :handle-bind-password="handleBindPassword"
    />
  </div>
</template>

<style scoped>
.profile-section-title {
  color: var(--theme-text-primary);
}

.welcome-banner {
  background-size: cover;
  background-position: center;
}
:deep(.ant-card) {
  background: transparent;
}
:deep(.ant-card-body) {
  padding: 16px;
}
:deep(.dark-modal .ant-modal-content) {
  background-color: #1e293b;
  border: 1px solid #334155;
}
:deep(.dark-modal .ant-modal-header) {
  background-color: #1e293b;
  border-bottom: 1px solid #334155;
}
:deep(.dark-modal .ant-modal-title) {
  color: #f1f5f9;
}
:deep(.dark-modal .ant-modal-close) {
  color: #94a3b8;
}
:deep(.dark-modal .ant-modal-footer) {
  border-top: 1px solid #334155;
}
:deep(.dark-drawer .ant-drawer-content) {
  background-color: #1e293b;
}
:deep(.dark-drawer .ant-drawer-header) {
  background-color: #1e293b;
  border-bottom: 1px solid #334155;
}
:deep(.dark-drawer .ant-drawer-title) {
  color: #f1f5f9;
}
:deep(.dark-drawer .ant-drawer-close) {
  color: #94a3b8;
}
</style>
