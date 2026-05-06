<template>
  <div class="h-screen w-screen flex flex-col items-center justify-center bg-gray-900 text-white">
    <div class="text-6xl mb-6">🛠️</div>
    <h1 class="text-3xl font-bold mb-4">{{ $t('system.maintenance_title') }}</h1>
    <p class="text-gray-400 mb-8">{{ $t('system.maintenance_desc') }}</p>
    <a-button type="primary" @click="checkStatus">
      {{ $t('system.refresh') }}
    </a-button>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import api from '@/api'

const router = useRouter()
const checkStatus = async () => {
  try {
    // 请求一下 /api/health，如果不报错且不是 503，说明维护结束
    await api.get('/api/health')
    router.push('/')
  } catch (error) {
    // 依然维护中，无操作
  }
}
</script>