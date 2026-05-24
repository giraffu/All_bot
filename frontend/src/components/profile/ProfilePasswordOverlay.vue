<script setup lang="ts">
import { computed } from 'vue'

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

const bindOpen = computed({
  get: () => props.showBindModal,
  set: (value: boolean) => emit('update:showBindModal', value),
})
</script>

<template>
  <a-modal
    v-if="!isMobile"
    v-model:open="bindOpen"
    :title="username ? '修改密咒' : '设置道号与密咒'"
    :confirmLoading="bindingLoading"
    @ok="handleBindPassword"
    okText="确认"
    cancelText="取消"
    :okButtonProps="{ class: 'bg-indigo-600 hover:bg-indigo-500 border-none shadow-lg shadow-indigo-600/30' }"
    class="dark-modal"
  >
    <div class="py-4 space-y-4">
      <p class="text-slate-400 text-sm mb-4">
        设置道号与密咒后，你可以在 Web 端直接破界登录，无需依赖 Telegram 客户端。
      </p>

      <div>
        <label class="block text-slate-300 mb-1 text-sm">道号 (账号)</label>
        <a-input
          v-model:value="bindFormState.username"
          placeholder="请输入 3-20 位的道号"
          class="bg-slate-500/50 border-slate-400 text-white placeholder-slate-500 focus:border-indigo-500"
        />
        <p class="text-slate-500 text-xs mt-1">如果你是首次结契，你可以自定义你喜欢的道号。一旦设置后，以后修改密咒时道号不可更改（需保持一致）。</p>
      </div>

      <div>
        <label class="block text-slate-300 mb-1 text-sm">密咒 (密码)</label>
        <a-input-password
          v-model:value="bindFormState.password"
          placeholder="请输入至少 6 位的密咒"
          class="bg-slate-500/50 border-slate-400 text-white placeholder-slate-500 focus:border-indigo-500"
        />
      </div>
    </div>
  </a-modal>

  <a-drawer
    v-else
    v-model:open="bindOpen"
    placement="bottom"
    :height="'auto'"
    :title="username ? '修改密咒' : '设置道号与密咒'"
    class="dark-drawer"
    :bodyStyle="{ background: '#1e293b' }"
    :headerStyle="{ background: '#1e293b', borderBottom: '1px solid #334155', color: '#f1f5f9' }"
  >
    <div class="py-4 space-y-4 px-2 pb-10">
      <p class="text-slate-400 text-sm mb-4">
        设置道号与密咒后，你可以在 Web 端直接破界登录，无需依赖 Telegram 客户端。
      </p>

      <div>
        <label class="block text-slate-300 mb-1 text-sm">道号 (账号)</label>
        <a-input
          v-model:value="bindFormState.username"
          placeholder="请输入 3-20 位的道号"
          class="bg-slate-500/50 border-slate-400 text-white placeholder-slate-500 focus:border-indigo-500 h-10"
        />
        <p class="text-slate-500 text-xs mt-1">如果你是首次结契，你可以自定义你喜欢的道号。一旦设置后，以后修改密咒时道号不可更改（需保持一致）。</p>
      </div>

      <div>
        <label class="block text-slate-300 mb-1 text-sm">密咒 (密码)</label>
        <a-input-password
          v-model:value="bindFormState.password"
          placeholder="请输入至少 6 位的密咒"
          class="bg-slate-500/50 border-slate-400 text-white placeholder-slate-500 focus:border-indigo-500 h-10"
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
