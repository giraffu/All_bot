<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import ProfileBackButton from '@/components/profile/ProfileBackButton.vue'

type RedeemCreditsPackage = {
  amountUsdt: number | string
  credits: number
  description: string
}

type MembershipRedeemOption = {
  key: string
  label: string
  amountUsdt: number | string
  description: string
}

const props = defineProps<{
  isMobile: boolean
  showRedeemCreditsModal: boolean
  showRedeemMembershipModal: boolean
  redeemCreditsLoading: boolean
  redeemMembershipLoading: boolean
  redeemCreditsForm: { amountUsdt: number | string | null }
  redeemMembershipForm: { optionKey: string }
  redeemCreditsPackages: readonly RedeemCreditsPackage[]
  membershipRedeemOptions: readonly MembershipRedeemOption[]
  availableCommissionUsdt: number | string
  handleRedeemCredits: () => void | Promise<void>
  handleRedeemMembership: () => void | Promise<void>
}>()

const emit = defineEmits<{
  'update:showRedeemCreditsModal': [value: boolean]
  'update:showRedeemMembershipModal': [value: boolean]
}>()

const { t } = useI18n()

const creditsOpen = computed({
  get: () => props.showRedeemCreditsModal,
  set: (value: boolean) => emit('update:showRedeemCreditsModal', value),
})

const membershipOpen = computed({
  get: () => props.showRedeemMembershipModal,
  set: (value: boolean) => emit('update:showRedeemMembershipModal', value),
})

const closeCredits = () => {
  creditsOpen.value = false
}

const closeMembership = () => {
  membershipOpen.value = false
}
</script>

<template>
  <a-modal
    v-if="!isMobile"
    v-model:open="creditsOpen"
    :closable="false"
    :confirmLoading="redeemCreditsLoading"
    @ok="handleRedeemCredits"
    okText="确认兑换"
    cancelText="取消"
    :okButtonProps="{ class: 'bg-emerald-600 hover:bg-emerald-500 border-none shadow-lg shadow-emerald-600/30' }"
    class="dark-modal profile-action-modal"
  >
    <template #title>
      <div class="profile-action-header">
        <ProfileBackButton :label="t('profile.back_to_profile')" @click="closeCredits" />
        <span class="profile-action-title">返佣兑换灵石</span>
      </div>
    </template>

    <div class="py-4 space-y-4">
      <p class="profile-action-text text-sm">当前可兑换返佣：<span class="font-bold text-emerald-400">{{ availableCommissionUsdt }} USDT</span></p>
      <p class="profile-action-muted text-sm">仅支持固定套餐：1 / 3 / 6 / 10 / 15 / 20 USDT。</p>
      <div>
        <label class="profile-action-label block mb-2 text-sm">选择兑换套餐</label>
        <a-radio-group v-model:value="redeemCreditsForm.amountUsdt" class="w-full space-y-2">
          <div
            v-for="item in redeemCreditsPackages"
            :key="item.amountUsdt"
            class="profile-action-option-card rounded-lg px-3 py-3"
          >
            <a-radio :value="item.amountUsdt">
              <span class="profile-action-strong font-medium">{{ item.amountUsdt }} USDT</span>
              <span class="ml-2 text-emerald-300">{{ item.credits }} 灵石</span>
            </a-radio>
            <p class="profile-action-muted mt-2 text-xs">{{ item.description }}</p>
          </div>
        </a-radio-group>
      </div>
    </div>
  </a-modal>

  <a-modal
    v-if="!isMobile"
    v-model:open="membershipOpen"
    :closable="false"
    :confirmLoading="redeemMembershipLoading"
    @ok="handleRedeemMembership"
    okText="确认兑换"
    cancelText="取消"
    :okButtonProps="{ class: 'bg-violet-600 hover:bg-violet-500 border-none shadow-lg shadow-violet-600/30' }"
    class="dark-modal profile-action-modal"
  >
    <template #title>
      <div class="profile-action-header">
        <ProfileBackButton :label="t('profile.back_to_profile')" @click="closeMembership" />
        <span class="profile-action-title">返佣兑换身份</span>
      </div>
    </template>

    <div class="py-4 space-y-4">
      <p class="profile-action-text text-sm">当前可兑换返佣：<span class="font-bold text-violet-300">{{ availableCommissionUsdt }} USDT</span></p>
      <div>
        <label class="profile-action-label block mb-2 text-sm">选择兑换档位</label>
        <a-radio-group v-model:value="redeemMembershipForm.optionKey" class="w-full space-y-2">
          <div
            v-for="option in membershipRedeemOptions"
            :key="option.key"
            class="profile-action-option-card rounded-lg px-3 py-3"
          >
            <a-radio :value="option.key">
              <span class="profile-action-strong font-medium">{{ option.label }}</span>
              <span class="ml-2 text-cyan-300">{{ option.amountUsdt }} USDT</span>
            </a-radio>
            <p class="profile-action-muted mt-2 text-xs">{{ option.description }}</p>
          </div>
        </a-radio-group>
      </div>
    </div>
  </a-modal>

  <a-drawer
    v-if="isMobile"
    v-model:open="creditsOpen"
    placement="bottom"
    :height="'auto'"
    :closable="false"
    class="dark-drawer profile-action-drawer"
    :bodyStyle="{ background: 'var(--theme-card-strong-bg)' }"
    :headerStyle="{ background: 'var(--theme-card-strong-bg)', borderBottom: '1px solid var(--theme-border)', color: 'var(--theme-text-primary)' }"
  >
    <template #title>
      <div class="profile-action-header">
        <ProfileBackButton :label="t('profile.back_to_profile')" @click="closeCredits" />
        <span class="profile-action-title">返佣兑换灵石</span>
      </div>
    </template>

    <div class="py-4 space-y-4 px-2 pb-10">
      <p class="profile-action-text text-sm">当前可兑换返佣：<span class="font-bold text-emerald-400">{{ availableCommissionUsdt }} USDT</span></p>
      <p class="profile-action-muted text-sm">仅支持固定套餐：1 / 3 / 6 / 10 / 15 / 20 USDT。</p>
      <a-radio-group v-model:value="redeemCreditsForm.amountUsdt" class="w-full space-y-2">
        <div
          v-for="item in redeemCreditsPackages"
          :key="item.amountUsdt"
          class="profile-action-option-card rounded-lg px-3 py-3"
        >
          <a-radio :value="item.amountUsdt">
            <span class="profile-action-strong font-medium">{{ item.amountUsdt }} USDT</span>
            <span class="ml-2 text-emerald-300">{{ item.credits }} 灵石</span>
          </a-radio>
          <p class="profile-action-muted mt-2 text-xs">{{ item.description }}</p>
        </div>
      </a-radio-group>
      <a-button
        type="primary"
        block
        :loading="redeemCreditsLoading"
        @click="handleRedeemCredits"
        class="bg-emerald-600 hover:bg-emerald-500 border-none"
      >
        确认兑换
      </a-button>
    </div>
  </a-drawer>

  <a-drawer
    v-if="isMobile"
    v-model:open="membershipOpen"
    placement="bottom"
    :height="'auto'"
    :closable="false"
    class="dark-drawer profile-action-drawer"
    :bodyStyle="{ background: 'var(--theme-card-strong-bg)' }"
    :headerStyle="{ background: 'var(--theme-card-strong-bg)', borderBottom: '1px solid var(--theme-border)', color: 'var(--theme-text-primary)' }"
  >
    <template #title>
      <div class="profile-action-header">
        <ProfileBackButton :label="t('profile.back_to_profile')" @click="closeMembership" />
        <span class="profile-action-title">返佣兑换身份</span>
      </div>
    </template>

    <div class="py-4 space-y-4 px-2 pb-10">
      <p class="profile-action-text text-sm">当前可兑换返佣：<span class="font-bold text-violet-300">{{ availableCommissionUsdt }} USDT</span></p>
      <a-radio-group v-model:value="redeemMembershipForm.optionKey" class="w-full space-y-2">
        <div
          v-for="option in membershipRedeemOptions"
          :key="option.key"
          class="profile-action-option-card rounded-lg px-3 py-3"
        >
          <a-radio :value="option.key">
            <span class="profile-action-strong font-medium">{{ option.label }}</span>
            <span class="ml-2 text-cyan-300">{{ option.amountUsdt }} USDT</span>
          </a-radio>
          <p class="profile-action-muted mt-2 text-xs">{{ option.description }}</p>
        </div>
      </a-radio-group>
      <a-button
        type="primary"
        block
        :loading="redeemMembershipLoading"
        @click="handleRedeemMembership"
        class="bg-violet-600 hover:bg-violet-500 border-none"
      >
        确认兑换
      </a-button>
    </div>
  </a-drawer>
</template>

<style scoped>
.profile-action-header {
  display: flex;
  align-items: center;
  min-height: 2.5rem;
  gap: 0.75rem;
}

.profile-action-title {
  color: var(--theme-text-primary);
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.25;
}

.profile-action-text,
.profile-action-label {
  color: var(--theme-text-secondary);
}

.profile-action-strong {
  color: var(--theme-text-primary);
}

.profile-action-muted {
  color: var(--theme-text-muted);
}

.profile-action-option-card {
  background: var(--theme-panel-bg);
  border: 1px solid var(--theme-border);
}

:global(.profile-action-modal .ant-modal-content),
:global(.profile-action-drawer .ant-drawer-content) {
  background-color: var(--theme-card-strong-bg) !important;
  color: var(--theme-text-primary) !important;
}

:global(.profile-action-modal .ant-modal-header),
:global(.profile-action-modal .ant-modal-footer) {
  background-color: transparent !important;
  border-color: var(--theme-border) !important;
}

:global(.profile-action-modal .ant-modal-title),
:global(.profile-action-drawer .ant-drawer-title) {
  color: var(--theme-text-primary) !important;
}
</style>
