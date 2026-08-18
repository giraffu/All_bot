<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ArrowUpRight, Languages, Sparkles } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const { locale, t } = useI18n()
const localeLabel = computed(() => (locale.value === 'zh' ? 'EN' : '中文'))

function toggleLocale() {
  locale.value = locale.value === 'zh' ? 'en' : 'zh'
  localStorage.setItem('clarity_locale', locale.value)
  document.documentElement.lang = locale.value === 'zh' ? 'zh-CN' : 'en'
}

async function logout() {
  await auth.logout()
  await router.push('/')
}
</script>

<template>
  <div class="site-shell">
    <header class="topbar">
      <RouterLink class="brand" to="/">
        <span class="brand-mark"><Sparkles :size="17" /></span>
        <span>{{ t('brand.name') }}</span>
      </RouterLink>
      <nav class="desktop-nav">
        <RouterLink to="/#product">{{ t('nav.product') }}</RouterLink>
        <RouterLink v-if="auth.isAuthenticated" to="/workspace">{{ t('nav.workspace') }}</RouterLink>
        <RouterLink to="/pricing">{{ t('nav.pricing') }}</RouterLink>
        <RouterLink v-if="auth.isAuthenticated" to="/support">{{ t('nav.support') }}</RouterLink>
      </nav>
      <div class="nav-actions">
        <button class="language-button" type="button" @click="toggleLocale">
          <Languages :size="16" />
          {{ localeLabel }}
        </button>
        <template v-if="auth.isAuthenticated">
          <RouterLink v-if="auth.isAdmin" class="text-button" to="/admin">{{ t('nav.admin') }}</RouterLink>
          <button class="text-button" type="button" @click="logout">{{ t('nav.logout') }}</button>
          <RouterLink class="primary-button compact" to="/workspace">
            {{ auth.user?.available_points }} {{ t('common.points') }}
            <ArrowUpRight :size="15" />
          </RouterLink>
        </template>
        <template v-else>
          <RouterLink class="text-button" to="/login">{{ t('nav.login') }}</RouterLink>
          <RouterLink class="primary-button compact" to="/register">
            {{ t('nav.start') }}
            <ArrowUpRight :size="15" />
          </RouterLink>
        </template>
      </div>
    </header>
    <main>
      <RouterView />
    </main>
    <footer class="footer">
      <div class="brand footer-brand">
        <span class="brand-mark"><Sparkles :size="15" /></span>
        <span>{{ t('brand.name') }}</span>
      </div>
      <div class="footer-links">
        <RouterLink to="/legal/terms">{{ t('legal.terms') }}</RouterLink>
        <RouterLink to="/legal/privacy">{{ t('legal.privacy') }}</RouterLink>
        <RouterLink to="/legal/copyright">{{ t('legal.copyright') }}</RouterLink>
      </div>
      <span class="muted">© 2026 {{ t('brand.name') }} · {{ t('brand.secondary') }}</span>
      <a
        class="icp-link"
        href="https://beian.miit.gov.cn/"
        target="_blank"
        rel="noopener noreferrer"
      >{{ t('legal.icp') }}</a>
    </footer>
  </div>
</template>
