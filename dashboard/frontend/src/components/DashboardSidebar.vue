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
    width="240"
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
