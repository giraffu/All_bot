<script setup>
import { SearchOutlined } from '@ant-design/icons-vue'

defineProps({
  filterIdentity: {
    type: String,
    default: null,
  },
  filterUserGroup: {
    type: String,
    default: null,
  },
  filterSubmissionBanned: {
    type: Boolean,
    default: false,
  },
  searchUserId: {
    type: String,
    default: '',
  },
  searchUsername: {
    type: String,
    default: '',
  },
  isUsernamePartial: {
    type: Boolean,
    default: true,
  },
  searchQuery: {
    type: String,
    default: '',
  },
  isQueryPartial: {
    type: Boolean,
    default: true,
  },
  totalUsers: {
    type: Number,
    default: 0,
  },
})

const emit = defineEmits([
  'update:filterIdentity',
  'update:filterUserGroup',
  'update:filterSubmissionBanned',
  'update:searchUserId',
  'update:searchUsername',
  'update:isUsernamePartial',
  'update:searchQuery',
  'update:isQueryPartial',
  'search',
])

const handleSearch = () => {
  emit('search')
}
</script>

<template>
  <div class="flex items-center gap-4 flex-wrap">
    <a-select
      :value="filterIdentity"
      placeholder="身份组"
      allow-clear
      class="w-32"
      @update:value="emit('update:filterIdentity', $event)"
      @change="handleSearch"
    >
      <a-select-option value="外门弟子">外门弟子</a-select-option>
      <a-select-option value="内门弟子">内门弟子</a-select-option>
      <a-select-option value="核心弟子">核心弟子</a-select-option>
      <a-select-option value="真传弟子">真传弟子</a-select-option>
    </a-select>

    <a-select
      :value="filterUserGroup"
      placeholder="修为"
      allow-clear
      class="w-32"
      @update:value="emit('update:filterUserGroup', $event)"
      @change="handleSearch"
    >
      <a-select-option value="凡人">凡人</a-select-option>
      <a-select-option value="练气期">练气期</a-select-option>
      <a-select-option value="筑基期">筑基期</a-select-option>
      <a-select-option value="金丹期">金丹期</a-select-option>
    </a-select>

    <a-checkbox
      :checked="filterSubmissionBanned"
      @update:checked="emit('update:filterSubmissionBanned', $event)"
      @change="handleSearch"
    >
      只看已禁止投稿用户
    </a-checkbox>

    <div class="flex items-center gap-2">
      <a-input
        :value="searchUserId"
        @update:value="emit('update:searchUserId', $event)"
        @input="handleSearch"
        placeholder="筛选用户ID"
        allow-clear
        class="w-36"
      >
        <template #prefix>
          <search-outlined class="text-gray-400" />
        </template>
      </a-input>
    </div>

    <div class="flex items-center gap-2">
      <a-input
        :value="searchUsername"
        @update:value="emit('update:searchUsername', $event)"
        @input="handleSearch"
        placeholder="搜索用户名"
        allow-clear
        class="w-40"
      >
        <template #prefix>
          <search-outlined class="text-gray-400" />
        </template>
      </a-input>
      <a-checkbox
        :checked="isUsernamePartial"
        @update:checked="emit('update:isUsernamePartial', $event)"
        @change="handleSearch"
      >
        部分匹配
      </a-checkbox>
    </div>

    <div class="flex items-center gap-2">
      <a-input
        :value="searchQuery"
        @update:value="emit('update:searchQuery', $event)"
        @input="handleSearch"
        placeholder="搜索昵称"
        allow-clear
        class="w-40"
      >
        <template #prefix>
          <search-outlined class="text-gray-400" />
        </template>
      </a-input>
      <a-checkbox
        :checked="isQueryPartial"
        @update:checked="emit('update:isQueryPartial', $event)"
        @change="handleSearch"
      >
        部分匹配
      </a-checkbox>
    </div>

    <a-tag color="blue">总计: {{ totalUsers }}</a-tag>
  </div>
</template>
