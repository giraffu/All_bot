<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, ShieldCheck } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ initialMode?: 'login' | 'register' }>()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const { t, te } = useI18n()
const mode = ref(props.initialMode || 'login')
const identifier = ref('')
const verifyCode = ref('')
const challengeId = ref('')
const password = ref('')
const pending = ref(false)
const sendPending = ref(false)
const resendAfter = ref(0)
const challengePhone = ref('')
const error = ref('')
const title = computed(() => t(mode.value === 'login' ? 'auth.loginTitle' : 'auth.registerTitle'))
let countdown: ReturnType<typeof setInterval> | undefined

function errorMessage(cause: unknown) {
  const code = cause instanceof Error ? cause.message : 'request_failed'
  return te(`auth.errors.${code}`) ? t(`auth.errors.${code}`) : code
}

function startCountdown(seconds: number) {
  resendAfter.value = seconds
  if (countdown) clearInterval(countdown)
  countdown = setInterval(() => {
    resendAfter.value -= 1
    if (resendAfter.value <= 0 && countdown) clearInterval(countdown)
  }, 1000)
}

async function sendCode() {
  sendPending.value = true
  error.value = ''
  try {
    const challenge = await auth.sendRegistrationCode(identifier.value)
    challengeId.value = challenge.challenge_id
    challengePhone.value = identifier.value
    startCountdown(challenge.resend_after)
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    sendPending.value = false
  }
}

function switchMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  identifier.value = ''
  verifyCode.value = ''
  challengeId.value = ''
  challengePhone.value = ''
  error.value = ''
  resendAfter.value = 0
  if (countdown) clearInterval(countdown)
}

watch(identifier, (value) => {
  if (!challengeId.value || value === challengePhone.value) return
  challengeId.value = ''
  verifyCode.value = ''
  resendAfter.value = 0
  if (countdown) clearInterval(countdown)
})

async function submit() {
  pending.value = true
  error.value = ''
  try {
    if (mode.value === 'login') await auth.login(identifier.value, password.value)
    else {
      if (!challengeId.value) throw new Error('verification_code_required')
      await auth.register(
        identifier.value,
        challengeId.value,
        verifyCode.value,
        password.value,
      )
    }
    await router.push((route.query.next as string) || '/workspace')
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    pending.value = false
  }
}

onBeforeUnmount(() => {
  if (countdown) clearInterval(countdown)
})
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
      <label>
        {{ t(mode === 'login' ? 'auth.loginIdentifier' : 'auth.phone') }}
        <input
          v-model="identifier"
          type="text"
          required
          :autocomplete="mode === 'login' ? 'username' : 'tel'"
          :inputmode="mode === 'register' ? 'tel' : 'text'"
          :placeholder="t(mode === 'login' ? 'auth.loginPlaceholder' : 'auth.phonePlaceholder')"
        />
      </label>
      <p v-if="mode === 'login'" class="microcopy">{{ t('auth.legacyEmailHint') }}</p>
      <div v-if="mode === 'register'" class="verification-row">
        <label>
          {{ t('auth.verifyCode') }}
          <input v-model="verifyCode" inputmode="numeric" required pattern="[0-9]{4,8}" autocomplete="one-time-code" />
        </label>
        <button class="glass-button code-button" type="button" :disabled="sendPending || resendAfter > 0" @click="sendCode">
          {{ resendAfter > 0 ? t('auth.resendCountdown', { seconds: resendAfter }) : t('auth.sendCode') }}
        </button>
      </div>
      <p v-if="mode === 'register' && challengeId" class="success-text microcopy">{{ t('auth.codeSent') }}</p>
      <label>{{ t('auth.password') }}<input v-model="password" type="password" required minlength="8" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" /></label>
      <p v-if="mode === 'register'" class="microcopy">
        {{ t('auth.terms') }}
        <RouterLink to="/legal/terms">{{ t('legal.terms') }}</RouterLink>
      </p>
      <p v-if="error" class="error-text">{{ error }}</p>
      <button class="primary-button large full" :disabled="pending" type="submit">
        {{ t(mode === 'login' ? 'auth.login' : 'auth.register') }} <ArrowRight :size="18" />
      </button>
      <button class="switch-auth" type="button" @click="switchMode">
        {{ t(mode === 'login' ? 'auth.switchRegister' : 'auth.switchLogin') }}
      </button>
    </form>
  </section>
</template>
