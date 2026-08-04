<script setup>
import {
  UserOutlined,
  MenuUnfoldOutlined,
  MenuFoldOutlined,
  ReloadOutlined,
  BellOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'

const props = defineProps({
  collapsed: {
    type: Boolean,
    default: false,
  },
  currentTabTitle: {
    type: String,
    default: '',
  },
  searchQuery: {
    type: String,
    default: '',
  },
  refreshLoading: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits([
  'update:collapsed',
  'update:searchQuery',
  'search',
  'refresh',
  'logout',
])

const toggleCollapsed = () => {
  emit('update:collapsed', !props.collapsed)
}
</script>

<template>
  <a-layout-header class="dashboard-header bg-white border-b px-6 flex justify-between items-center h-16 shrink-0 z-40">
    <div class="flex items-center gap-4">
      <component
        :is="collapsed ? MenuUnfoldOutlined : MenuFoldOutlined"
        class="trigger dashboard-menu-trigger text-lg cursor-pointer hover:text-blue-600 transition-colors"
        role="button"
        tabindex="0"
        aria-label="切换导航菜单"
        @click="toggleCollapsed"
        @keydown.enter.prevent="toggleCollapsed"
        @keydown.space.prevent="toggleCollapsed"
      />
      <a-breadcrumb class="hidden sm:block">
        <a-breadcrumb-item>首页</a-breadcrumb-item>
        <a-breadcrumb-item>{{ currentTabTitle }}</a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <div class="flex items-center gap-6">
      <div class="hidden md:flex items-center bg-gray-100 rounded-full px-4 py-1.5 gap-2 border border-transparent focus-within:border-blue-400 focus-within:bg-white transition-all">
        <search-outlined class="text-gray-400" />
        <input
          :value="searchQuery"
          type="text"
          placeholder="输入任务ID回车搜索..."
          class="bg-transparent border-none outline-none text-sm w-48 text-gray-600 placeholder-gray-400"
          @input="emit('update:searchQuery', $event.target.value)"
          @keyup.enter="emit('search')"
        />
      </div>

      <div class="flex items-center gap-3">
        <a-badge dot color="green">
          <a-button shape="circle" size="small" class="flex items-center justify-center border-none shadow-none">
            <template #icon><bell-outlined /></template>
          </a-button>
        </a-badge>

        <a-tooltip title="刷新数据">
          <a-button
            shape="circle"
            size="small"
            :loading="refreshLoading"
            class="flex items-center justify-center border-none shadow-none"
            @click="emit('refresh')"
          >
            <template #icon><reload-outlined /></template>
          </a-button>
        </a-tooltip>
      </div>

      <div class="h-8 w-px bg-gray-200"></div>
      <a-dropdown placement="bottomRight">
        <div class="flex items-center gap-2 cursor-pointer group">
          <a-avatar style="background-color: #1890ff">
            <template #icon><user-outlined /></template>
          </a-avatar>
          <span class="text-gray-600 group-hover:text-blue-600 transition-colors">管理员</span>
        </div>
        <template #overlay>
          <a-menu>
            <a-menu-item>个人中心</a-menu-item>
            <a-menu-item danger @click="emit('logout')">退出登录</a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </div>
  </a-layout-header>
</template>

<style scoped>
@media (max-width: 767px) {
  .dashboard-header {
    height: 56px !important;
    padding-inline: 12px !important;
  }

  .dashboard-menu-trigger {
    display: inline-flex;
    width: 40px;
    height: 40px;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    font-size: 20px;
    -webkit-tap-highlight-color: transparent;
  }

  .dashboard-header > div:last-child {
    gap: 10px !important;
  }

  .dashboard-header :deep(.ant-badge),
  .dashboard-header :deep(.ant-divider),
  .dashboard-header .h-8.w-px,
  .dashboard-header :deep(.ant-dropdown-trigger span) {
    display: none;
  }
}
</style>
