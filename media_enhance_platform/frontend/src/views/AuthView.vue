<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, ShieldCheck } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ initialMode?: 'login' | 'register' }>()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const mode = ref(props.initialMode || 'login')
const email = ref('')
const password = ref('')
const pending = ref(false)
const error = ref('')
const title = computed(() => t(mode.value === 'login' ? 'auth.loginTitle' : 'auth.registerTitle'))

async function submit() {
  pending.value = true
  error.value = ''
  try {
    if (mode.value === 'login') await auth.login(email.value, password.value)
    else await auth.register(email.value, password.value)
    await router.push((route.query.next as string) || '/workspace')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'request_failed'
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <section class="auth-page">
    <div class="auth-aside">
      <div class="eyebrow"><span></span>CLARITY WORKSPACE</div>
      <h1>{{ t('home.titleA') }}<em>{{ t('home.titleB') }}</em></h1>
      <div class="auth-orb"><ShieldCheck :size="42" /></div>
      <p>{{ t('home.privateDesc') }}</p>
    </div>
    <form class="auth-card" @submit.prevent="submit">
      <div>
        <span class="section-index">{{ mode === 'login' ? 'SIGN IN' : 'REGISTER' }}</span>
        <h2>{{ title }}</h2>
      </div>
      <label>{{ t('auth.email') }}<input v-model="email" type="email" required autocomplete="email" /></label>
      <label>{{ t('auth.password') }}<input v-model="password" type="password" required minlength="8" autocomplete="current-password" /></label>
      <p v-if="mode === 'register'" class="microcopy">
        {{ t('auth.terms') }}
        <RouterLink to="/legal/terms">{{ t('legal.terms') }}</RouterLink>
      </p>
      <p v-if="error" class="error-text">{{ error }}</p>
      <button class="primary-button large full" :disabled="pending" type="submit">
        {{ t(mode === 'login' ? 'auth.login' : 'auth.register') }} <ArrowRight :size="18" />
      </button>
      <button class="switch-auth" type="button" @click="mode = mode === 'login' ? 'register' : 'login'">
        {{ t(mode === 'login' ? 'auth.switchRegister' : 'auth.switchLogin') }}
      </button>
    </form>
  </section>
</template>
