<script setup lang="ts">
import { ref } from 'vue'
import { LockOutlined, UserOutlined } from '@ant-design/icons-vue'

import { loginQqccConfig } from '../api/qqccConfigApi'
import { setQqccConfigAuthToken } from '../composables/useQqccConfigAuth'

const emit = defineEmits<{
  login: []
}>()

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

const handleLogin = async () => {
  if (!username.value || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }

  loading.value = true
  error.value = ''

  try {
    const res = await loginQqccConfig(username.value, password.value)
    if (res.access_token) {
      setQqccConfigAuthToken(res.access_token)
      emit('login')
    }
  } catch {
    error.value = '用户名或密码错误'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-50 px-4 py-12">
    <div class="w-full max-w-md rounded-lg bg-white p-8 shadow-sm border border-slate-200">
      <div class="mb-8">
        <div
          class="mx-auto flex h-12 w-12 items-center justify-center rounded-lg bg-slate-900 text-lg font-semibold text-white"
        >
          Q
        </div>
        <h1 class="mt-5 text-center text-2xl font-semibold text-slate-900">
          QQCC 懒人Bot配置
        </h1>
      </div>
      <form class="space-y-5" @submit.prevent="handleLogin">
        <a-input v-model:value="username" size="large" placeholder="用户名">
          <template #prefix><user-outlined class="text-slate-400" /></template>
        </a-input>
        <a-input-password v-model:value="password" size="large" placeholder="密码">
          <template #prefix><lock-outlined class="text-slate-400" /></template>
        </a-input-password>
        <div v-if="error" class="text-center text-sm text-red-500">
          {{ error }}
        </div>
        <a-button type="primary" html-type="submit" block size="large" :loading="loading">
          登录
        </a-button>
      </form>
    </div>
  </div>
</template>
