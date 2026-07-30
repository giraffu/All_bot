<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowRight, Check } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api'

interface Catalog {
  services: Record<string, { multipliers: Record<string, number>; billing_unit: string }>
  packages: { points: number; price_cny: number }[]
  purchases_enabled: boolean
}
const { t } = useI18n()
const catalog = ref<Catalog | null>(null)
onMounted(async () => (catalog.value = await api<Catalog>('/catalog')))
</script>

<template>
  <section class="pricing-page">
    <div class="page-hero compact-hero">
      <div class="eyebrow"><span></span>{{ t('pricing.eyebrow') }}</div>
      <h1>{{ t('pricing.title') }}</h1>
      <p>{{ t('pricing.subtitle') }}</p>
    </div>
    <div v-if="catalog" class="pricing-content">
      <div class="rate-grid">
        <article class="rate-card"><span>{{ t('pricing.image') }}</span><h2>2–4 <small>{{ t('common.points') }}</small></h2><p>{{ t('workspace.types.image_upscale') }} · 2× / 4×</p><Check :size="19" /></article>
        <article class="rate-card featured"><span>{{ t('pricing.duration') }}</span><h2>5 <small>/ 10s</small></h2><p>{{ t('workspace.types.video_upscale') }} · 2×</p><Check :size="19" /></article>
        <article class="rate-card"><span>{{ t('pricing.duration') }}</span><h2>3–5 <small>/ 10s</small></h2><p>{{ t('workspace.types.frame_interpolation') }} · 2× / 4×</p><Check :size="19" /></article>
      </div>
      <div class="package-section">
        <div class="section-heading"><span class="section-index">PACKS</span><h2>{{ t('pricing.packs') }}</h2><p>{{ t('pricing.unavailable') }}</p></div>
        <div class="package-grid">
          <article v-for="item in catalog.packages" :key="item.points">
            <span>CLARITY POINTS</span><h3>{{ item.points }}</h3><b>¥{{ item.price_cny }}</b>
            <RouterLink class="glass-button full" to="/support">{{ t('pricing.contact') }} <ArrowRight :size="15" /></RouterLink>
          </article>
        </div>
      </div>
    </div>
  </section>
</template>
