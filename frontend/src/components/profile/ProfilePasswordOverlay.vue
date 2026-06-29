<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import ProfileBackButton from '@/components/profile/ProfileBackButton.vue'

const props = defineProps<{
  isMobile: boolean
  isTMA: boolean
  showBindModal: boolean
  bindingLoading: boolean
  username?: string | null
  bindFormState: {
    username: string
    password: string
  }
  handleBindPassword: () => void | Promise<void>
}>()

const emit = defineEmits<{
  'update:showBindModal': [value: boolean]
}>()

const { t } = useI18n()

const bindOpen = computed({
  get: () => props.showBindModal,
  set: (value: boolean) => emit('update:showBindModal', value),
})

const modalTitle = computed(() => (props.username ? '修改密咒' : '设置道号与密咒'))

const closeBind = () => {
  bindOpen.value = false
}
</script>

<template>
  <a-modal
    v-if="!isMobile"
    v-model:open="bindOpen"
    :closable="false"
    :confirmLoading="bindingLoading"
    @ok="handleBindPassword"
    okText="确认"
    cancelText="取消"
    :okButtonProps="{ class: 'bg-indigo-600 hover:bg-indigo-500 border-none shadow-lg shadow-indigo-600/30' }"
    class="dark-modal profile-action-modal"
  >
    <template #title>
      <div class="profile-action-header">
        <ProfileBackButton :label="t('profile.back_to_profile')" @click="closeBind" />
        <span class="profile-action-title">{{ modalTitle }}</span>
      </div>
    </template>

    <div class="py-4 space-y-4">
      <p class="profile-action-muted text-sm mb-4">
        设置道号与密咒后，你可以在 Web 端直接破界登录，无需依赖 Telegram 客户端。
      </p>

      <div>
        <label class="profile-action-label block mb-1 text-sm">道号 (账号)</label>
        <a-input
          v-model:value="bindFormState.username"
          placeholder="请输入 3-20 位的道号"
          class="profile-action-input"
        />
        <p class="profile-action-muted text-xs mt-1">如果你是首次结契，你可以自定义你喜欢的道号。一旦设置后，以后修改密咒时道号不可更改（需保持一致）。</p>
      </div>

      <div>
        <label class="profile-action-label block mb-1 text-sm">密咒 (密码)</label>
        <a-input-password
          v-model:value="bindFormState.password"
          placeholder="请输入至少 6 位的密咒"
          class="profile-action-input"
        />
      </div>
    </div>
  </a-modal>

  <a-drawer
    v-else
    v-model:open="bindOpen"
    placement="bottom"
    :height="'auto'"
    :closable="false"
    class="dark-drawer profile-action-drawer"
    :bodyStyle="{ background: 'var(--theme-card-strong-bg)' }"
    :headerStyle="{ background: 'var(--theme-card-strong-bg)', borderBottom: '1px solid var(--theme-border)', color: 'var(--theme-text-primary)' }"
  >
    <template #title>
      <div class="profile-action-header">
        <ProfileBackButton :label="t('profile.back_to_profile')" @click="closeBind" />
        <span class="profile-action-title">{{ modalTitle }}</span>
      </div>
    </template>

    <div class="py-4 space-y-4 px-2 pb-10">
      <p class="profile-action-muted text-sm mb-4">
        设置道号与密咒后，你可以在 Web 端直接破界登录，无需依赖 Telegram 客户端。
      </p>

      <div>
        <label class="profile-action-label block mb-1 text-sm">道号 (账号)</label>
        <a-input
          v-model:value="bindFormState.username"
          placeholder="请输入 3-20 位的道号"
          class="profile-action-input h-10"
        />
        <p class="profile-action-muted text-xs mt-1">如果你是首次结契，你可以自定义你喜欢的道号。一旦设置后，以后修改密咒时道号不可更改（需保持一致）。</p>
      </div>

      <div>
        <label class="profile-action-label block mb-1 text-sm">密咒 (密码)</label>
        <a-input-password
          v-model:value="bindFormState.password"
          placeholder="请输入至少 6 位的密咒"
          class="profile-action-input h-10"
        />
      </div>

      <a-button
        v-if="!isTMA"
        type="primary"
        @click="handleBindPassword"
        :loading="bindingLoading"
        class="w-full mt-4 h-12 bg-indigo-600 hover:bg-indigo-500 border-none shadow-lg shadow-indigo-600/30 text-lg font-bold"
      >
        确认结契
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

.profile-action-label {
  color: var(--theme-text-secondary);
}

.profile-action-muted {
  color: var(--theme-text-muted);
}

:deep(.profile-action-input),
:deep(.profile-action-input .ant-input),
:deep(.profile-action-input input) {
  background-color: var(--theme-card-strong-bg) !important;
  border-color: var(--theme-border) !important;
  color: var(--theme-text-primary) !important;
  -webkit-text-fill-color: var(--theme-text-primary) !important;
}

:deep(.profile-action-input::placeholder),
:deep(.profile-action-input input::placeholder) {
  color: var(--theme-input-placeholder) !important;
  -webkit-text-fill-color: var(--theme-input-placeholder) !important;
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
