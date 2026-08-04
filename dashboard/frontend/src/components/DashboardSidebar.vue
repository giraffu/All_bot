<script setup>
defineProps({
  collapsed: {
    type: Boolean,
    default: false,
  },
  menuItems: {
    type: Array,
    required: true,
  },
  activeTab: {
    type: Array,
    required: true,
  },
  logoutIcon: {
    type: [Object, Function],
    required: true,
  },
  mobile: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits([
  'update:collapsed',
  'update:activeTab',
  'logout',
])
</script>

<template>
  <a-layout-sider
    :collapsed="collapsed"
    :trigger="null"
    collapsible
    theme="dark"
    class="sidebar-shadow z-50"
    :class="{
      'dashboard-sidebar-mobile': mobile,
      'dashboard-sidebar-mobile-open': mobile && !collapsed,
    }"
    width="240"
    :inert="mobile && collapsed"
    @update:collapsed="emit('update:collapsed', $event)"
  >
    <div class="logo-container">
      <div class="logo-icon">T</div>
      <span v-if="!collapsed" class="logo-text">TeleBot Admin</span>
    </div>

    <a-menu
      :selected-keys="activeTab"
      theme="dark"
      mode="inline"
      @update:selectedKeys="emit('update:activeTab', $event)"
    >
      <a-menu-item
        v-for="item in menuItems"
        :key="item.key"
        :disabled="item.disabled"
        @click="emit('update:activeTab', [item.key])"
      >
        <template #icon>
          <component :is="item.icon" />
        </template>
        <span>{{ item.label }}</span>
      </a-menu-item>
    </a-menu>

    <div v-if="!collapsed" class="sidebar-footer">
      <div class="text-xs text-gray-500 mb-2">v1.2.0-stable</div>
      <a-button
        type="link"
        danger
        block
        class="flex items-center justify-center gap-2 p-0 h-auto"
        @click="emit('logout')"
      >
        <component :is="logoutIcon" /> 退出登录
      </a-button>
    </div>
  </a-layout-sider>
</template>

<style scoped>
:deep(.ant-layout-sider-children) {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
}

:deep(.ant-menu) {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-bottom: 96px;
}

@media (max-width: 767px) {
  .dashboard-sidebar-mobile {
    position: fixed !important;
    inset: 0 auto 0 0;
    z-index: 50;
    width: min(82vw, 300px) !important;
    max-width: 300px;
    height: 100dvh;
    transform: translateX(-105%);
    transition: transform 180ms ease;
    visibility: hidden;
  }

  .dashboard-sidebar-mobile-open {
    transform: translateX(0);
    visibility: visible;
  }

  :deep(.ant-layout-sider-children) {
    width: min(82vw, 300px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .dashboard-sidebar-mobile {
    transition: none;
  }
}
</style>
