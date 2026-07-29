<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const form = reactive({ username: '', password: '' })
const loading = ref(false)
const error = ref(false)

async function submit() {
  loading.value = true
  error.value = false
  try {
    await auth.login(form.username, form.password)
    await router.replace('/')
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-shell">
    <section class="login-visual">
      <div class="brand-mark">A</div>
      <p class="eyebrow">ALLBOT · LOCAL 3D LAB</p>
      <h1>{{ t('miniapp.brand') }}</h1>
      <p>{{ t('miniapp.tagline') }}</p>
      <div class="visual-figure">
        <span class="visual-ring ring-one" />
        <span class="visual-ring ring-two" />
        <span class="visual-body" />
      </div>
    </section>
    <section class="login-card">
      <p class="eyebrow">SECURE LAN ACCESS</p>
      <h2>{{ t('miniapp.login.title') }}</h2>
      <p class="muted">{{ t('miniapp.login.hint') }}</p>
      <form @submit.prevent="submit">
        <label>
          <span>{{ t('miniapp.login.username') }}</span>
          <input v-model.trim="form.username" autocomplete="username" required minlength="3" />
        </label>
        <label>
          <span>{{ t('miniapp.login.password') }}</span>
          <input v-model="form.password" type="password" autocomplete="current-password" required minlength="6" />
        </label>
        <p v-if="error" class="form-error">{{ t('miniapp.login.failed') }}</p>
        <button class="primary-button" type="submit" :disabled="loading">
          {{ loading ? '…' : t('miniapp.login.submit') }}
        </button>
      </form>
    </section>
  </main>
</template>
