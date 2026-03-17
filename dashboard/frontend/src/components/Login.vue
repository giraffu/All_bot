<script setup>
import { ref } from 'vue'
import { login } from '../api/api'
import { UserOutlined, LockOutlined } from '@ant-design/icons-vue'

const emit = defineEmits(['login-success'])

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
    const res = await login(username.value, password.value)
    if (res.access_token) {
      localStorage.setItem('token', res.access_token)
      emit('login-success')
    }
  } catch (err) {
    error.value = '用户名或密码错误'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
    <div class="max-w-md w-full space-y-8 bg-white p-10 rounded-xl shadow-md">
      <div>
        <div class="mx-auto h-12 w-12 bg-blue-600 rounded-xl flex items-center justify-center text-white text-2xl font-bold">
          T
        </div>
        <h2 class="mt-6 text-center text-3xl font-extrabold text-gray-900">
          TeleBot Admin
        </h2>
        <p class="mt-2 text-center text-sm text-gray-600">
          请登录以访问管理后台
        </p>
      </div>
      <form class="mt-8 space-y-6" @submit.prevent="handleLogin">
        <div class="rounded-md shadow-sm -space-y-px">
          <div class="mb-4">
            <a-input 
              v-model:value="username" 
              size="large" 
              placeholder="用户名" 
              class="rounded-md"
            >
              <template #prefix><user-outlined class="text-gray-400" /></template>
            </a-input>
          </div>
          <div>
            <a-input-password 
              v-model:value="password" 
              size="large" 
              placeholder="密码" 
              class="rounded-md"
            >
              <template #prefix><lock-outlined class="text-gray-400" /></template>
            </a-input-password>
          </div>
        </div>

        <div v-if="error" class="text-red-500 text-sm text-center">
          {{ error }}
        </div>

        <div>
          <a-button 
            type="primary" 
            html-type="submit" 
            block 
            size="large" 
            :loading="loading"
            class="bg-blue-600 hover:bg-blue-700"
          >
            登录
          </a-button>
        </div>
      </form>
    </div>
  </div>
</template>
