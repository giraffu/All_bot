<script setup lang="ts">
import { computed } from 'vue'

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

const creditsOpen = computed({
  get: () => props.showRedeemCreditsModal,
  set: (value: boolean) => emit('update:showRedeemCreditsModal', value),
})

const membershipOpen = computed({
  get: () => props.showRedeemMembershipModal,
  set: (value: boolean) => emit('update:showRedeemMembershipModal', value),
})
</script>

<template>
  <a-modal
    v-if="!isMobile"
    v-model:open="creditsOpen"
    title="返佣兑换灵石"
    :confirmLoading="redeemCreditsLoading"
    @ok="handleRedeemCredits"
    okText="确认兑换"
    cancelText="取消"
    :okButtonProps="{ class: 'bg-emerald-600 hover:bg-emerald-500 border-none shadow-lg shadow-emerald-600/30' }"
    class="dark-modal"
  >
    <div class="py-4 space-y-4">
      <p class="text-slate-300 text-sm">当前可兑换返佣：<span class="font-bold text-emerald-300">{{ availableCommissionUsdt }} USDT</span></p>
      <p class="text-slate-400 text-sm">仅支持固定套餐：1 / 3 / 6 / 10 / 15 / 20 USDT。</p>
      <div>
        <label class="block text-slate-300 mb-2 text-sm">选择兑换套餐</label>
        <a-radio-group v-model:value="redeemCreditsForm.amountUsdt" class="w-full space-y-2">
          <div
            v-for="item in redeemCreditsPackages"
            :key="item.amountUsdt"
            class="rounded-lg border border-slate-600 bg-slate-800/50 px-3 py-3"
          >
            <a-radio :value="item.amountUsdt">
              <span class="text-slate-100 font-medium">{{ item.amountUsdt }} USDT</span>
              <span class="ml-2 text-emerald-300">{{ item.credits }} 灵石</span>
            </a-radio>
            <p class="mt-2 text-xs text-slate-400">{{ item.description }}</p>
          </div>
        </a-radio-group>
      </div>
    </div>
  </a-modal>

  <a-modal
    v-if="!isMobile"
    v-model:open="membershipOpen"
    title="返佣兑换身份"
    :confirmLoading="redeemMembershipLoading"
    @ok="handleRedeemMembership"
    okText="确认兑换"
    cancelText="取消"
    :okButtonProps="{ class: 'bg-violet-600 hover:bg-violet-500 border-none shadow-lg shadow-violet-600/30' }"
    class="dark-modal"
  >
    <div class="py-4 space-y-4">
      <p class="text-slate-300 text-sm">当前可兑换返佣：<span class="font-bold text-violet-300">{{ availableCommissionUsdt }} USDT</span></p>
      <div>
        <label class="block text-slate-300 mb-2 text-sm">选择兑换档位</label>
        <a-radio-group v-model:value="redeemMembershipForm.optionKey" class="w-full space-y-2">
          <div
            v-for="option in membershipRedeemOptions"
            :key="option.key"
            class="rounded-lg border border-slate-600 bg-slate-800/50 px-3 py-3"
          >
            <a-radio :value="option.key">
              <span class="text-slate-100 font-medium">{{ option.label }}</span>
              <span class="ml-2 text-cyan-300">{{ option.amountUsdt }} USDT</span>
            </a-radio>
            <p class="mt-2 text-xs text-slate-400">{{ option.description }}</p>
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
    title="返佣兑换灵石"
    class="dark-drawer"
    :bodyStyle="{ background: '#1e293b' }"
    :headerStyle="{ background: '#1e293b', borderBottom: '1px solid #334155', color: '#f1f5f9' }"
  >
    <div class="py-4 space-y-4 px-2 pb-10">
      <p class="text-slate-300 text-sm">当前可兑换返佣：<span class="font-bold text-emerald-300">{{ availableCommissionUsdt }} USDT</span></p>
      <p class="text-slate-400 text-sm">仅支持固定套餐：1 / 3 / 6 / 10 / 15 / 20 USDT。</p>
      <a-radio-group v-model:value="redeemCreditsForm.amountUsdt" class="w-full space-y-2">
        <div
          v-for="item in redeemCreditsPackages"
          :key="item.amountUsdt"
          class="rounded-lg border border-slate-600 bg-slate-800/50 px-3 py-3"
        >
          <a-radio :value="item.amountUsdt">
            <span class="text-slate-100 font-medium">{{ item.amountUsdt }} USDT</span>
            <span class="ml-2 text-emerald-300">{{ item.credits }} 灵石</span>
          </a-radio>
          <p class="mt-2 text-xs text-slate-400">{{ item.description }}</p>
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
    title="返佣兑换身份"
    class="dark-drawer"
    :bodyStyle="{ background: '#1e293b' }"
    :headerStyle="{ background: '#1e293b', borderBottom: '1px solid #334155', color: '#f1f5f9' }"
  >
    <div class="py-4 space-y-4 px-2 pb-10">
      <p class="text-slate-300 text-sm">当前可兑换返佣：<span class="font-bold text-violet-300">{{ availableCommissionUsdt }} USDT</span></p>
      <a-radio-group v-model:value="redeemMembershipForm.optionKey" class="w-full space-y-2">
        <div
          v-for="option in membershipRedeemOptions"
          :key="option.key"
          class="rounded-lg border border-slate-600 bg-slate-800/50 px-3 py-3"
        >
          <a-radio :value="option.key">
            <span class="text-slate-100 font-medium">{{ option.label }}</span>
            <span class="ml-2 text-cyan-300">{{ option.amountUsdt }} USDT</span>
          </a-radio>
          <p class="mt-2 text-xs text-slate-400">{{ option.description }}</p>
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
