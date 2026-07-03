<script setup lang="ts">
import { LogoutOutlined } from '@ant-design/icons-vue'

import QqccBotSettings from './components/QqccBotSettings.vue'
import QqccConfigLogin from './components/QqccConfigLogin.vue'
import {
  fetchQqccConfig,
  updateQqccConfig,
} from './api/qqccConfigApi'
import { useQqccConfigAuth } from './composables/useQqccConfigAuth'

const { isAuthenticated, clearAuthToken } = useQqccConfigAuth()

const handleLogout = () => {
  clearAuthToken()
}
</script>

<template>
  <qqcc-config-login v-if="!isAuthenticated" />
  <a-layout v-else class="qqcc-config-app">
    <a-layout-header class="qqcc-config-header">
      <div class="flex min-w-0 items-center gap-3">
        <div class="qqcc-config-logo">Q</div>
        <div class="min-w-0">
          <div class="qqcc-config-eyebrow">QQCC 控制面</div>
          <div class="qqcc-config-title">懒人Bot配置</div>
        </div>
      </div>
      <a-button class="qqcc-config-logout" @click="handleLogout">
        <template #icon><LogoutOutlined /></template>
        退出
      </a-button>
    </a-layout-header>
    <a-layout-content class="qqcc-config-content">
      <div class="qqcc-config-inner">
        <qqcc-bot-settings
          :fetch-config="fetchQqccConfig"
          :update-config="updateQqccConfig"
        />
      </div>
    </a-layout-content>
  </a-layout>
</template>

<style scoped>
:global(html),
:global(body),
:global(#app) {
  height: 100%;
  width: 100%;
  margin: 0;
  padding: 0;
  overflow: hidden;
}

:global(body) {
  display: block;
  min-width: 320px;
  background: #eef2f7;
  color: #111827;
}

.qqcc-config-app {
  height: 100vh;
  overflow: hidden;
  background:
    linear-gradient(180deg, #f8fafc 0%, #eef2f7 38%, #e8edf4 100%);
}

.qqcc-config-header {
  height: 64px;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex: none;
  background: rgba(255, 255, 255, 0.94);
  border-bottom: 1px solid #dbe4ef;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(10px);
}

.qqcc-config-logo {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  background: linear-gradient(135deg, #0f172a 0%, #2563eb 58%, #14b8a6 100%);
  font-weight: 800;
  letter-spacing: 0;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.22);
}

.qqcc-config-eyebrow {
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.1;
}

.qqcc-config-title {
  color: #0f172a;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.35;
}

.qqcc-config-logout {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.qqcc-config-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px;
}

.qqcc-config-inner {
  width: 100%;
  max-width: 1480px;
  margin: 0 auto;
}

@media (max-width: 768px) {
  .qqcc-config-header {
    height: 60px;
    padding: 0 12px;
  }

  .qqcc-config-logo {
    width: 34px;
    height: 34px;
    border-radius: 9px;
  }

  .qqcc-config-title {
    font-size: 15px;
  }

  .qqcc-config-eyebrow {
    display: none;
  }

  .qqcc-config-content {
    padding: 12px;
  }
}
</style>
