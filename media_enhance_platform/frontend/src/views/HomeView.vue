<script setup lang="ts">
import { ArrowRight, Image, LockKeyhole, ScanLine, Upload, Video, WandSparkles } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <section class="hero">
    <div class="hero-glow glow-one"></div>
    <div class="hero-glow glow-two"></div>
    <div class="hero-content">
      <div class="eyebrow"><span></span>{{ t('home.eyebrow') }}</div>
      <h1>{{ t('home.titleA') }}<em>{{ t('home.titleB') }}</em></h1>
      <p>{{ t('home.subtitle') }}</p>
      <div class="hero-actions">
        <RouterLink class="primary-button large" to="/workspace">
          {{ t('home.cta') }} <ArrowRight :size="18" />
        </RouterLink>
        <RouterLink class="glass-button large" to="/pricing">{{ t('home.secondary') }}</RouterLink>
      </div>
      <div class="hero-stage" aria-hidden="true">
        <div class="stage-grid"></div>
        <div class="stage-card stage-source">
          <span>540p</span>
          <div class="soft-landscape"><i></i></div>
          <small>ORIGINAL</small>
        </div>
        <div class="stage-flow"><WandSparkles :size="28" /><b>AI</b></div>
        <div class="stage-card stage-result">
          <span>4K</span>
          <div class="sharp-landscape"><i></i></div>
          <small>ENHANCED</small>
        </div>
      </div>
    </div>
  </section>

  <section id="product" class="content-section product-section">
    <div class="section-heading">
      <span class="section-index">01</span>
      <h2>{{ t('nav.product') }}</h2>
      <p>{{ t('home.subtitle') }}</p>
    </div>
    <div class="feature-grid">
      <article class="feature-card feature-image">
        <div class="feature-icon"><Image :size="24" /></div>
        <span class="feature-number">01</span>
        <h3>{{ t('home.imageTitle') }}</h3>
        <p>{{ t('home.imageDesc') }}</p>
        <div class="feature-visual pixels">
          <span v-for="index in 48" :key="index"></span>
        </div>
      </article>
      <article class="feature-card feature-video">
        <div class="feature-icon"><Video :size="24" /></div>
        <span class="feature-number">02</span>
        <h3>{{ t('home.videoTitle') }}</h3>
        <p>{{ t('home.videoDesc') }}</p>
        <div class="feature-visual filmstrip">
          <i v-for="index in 5" :key="index"></i>
        </div>
      </article>
      <article class="feature-card feature-frame">
        <div class="feature-icon"><ScanLine :size="24" /></div>
        <span class="feature-number">03</span>
        <h3>{{ t('home.frameTitle') }}</h3>
        <p>{{ t('home.frameDesc') }}</p>
        <div class="feature-visual motion-lines">
          <i v-for="index in 7" :key="index"></i>
        </div>
      </article>
    </div>
  </section>

  <section class="content-section process-section">
    <div class="section-heading centered">
      <span class="section-index">02</span>
      <h2>{{ t('home.workflow') }}</h2>
    </div>
    <div class="process-line">
      <div class="process-step"><span><Upload :size="22" /></span><b>01</b><h3>{{ t('home.step1') }}</h3></div>
      <i></i>
      <div class="process-step"><span><WandSparkles :size="22" /></span><b>02</b><h3>{{ t('home.step2') }}</h3></div>
      <i></i>
      <div class="process-step"><span><ArrowRight :size="22" /></span><b>03</b><h3>{{ t('home.step3') }}</h3></div>
    </div>
  </section>

  <section class="content-section privacy-banner">
    <div class="privacy-icon"><LockKeyhole :size="27" /></div>
    <div><h2>{{ t('home.private') }}</h2><p>{{ t('home.privateDesc') }}</p></div>
    <RouterLink class="glass-button" to="/legal/privacy">{{ t('legal.privacy') }}</RouterLink>
  </section>
</template>
