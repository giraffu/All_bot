<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { FileWarning, Send } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { api } from '@/api'

const route = useRoute()
const { t } = useI18n()
const document = computed(() => String(route.params.document))
const title = computed(() => t(`legal.${document.value}`))
const email = ref('')
const subject = ref('')
const content = ref('')
const done = ref(false)
async function complain() {
  await api('/legal/copyright-complaints', { method: 'POST', body: JSON.stringify({ email: email.value, subject: subject.value, content: content.value }) })
  done.value = true
}
</script>

<template>
  <section class="legal-page">
    <div class="legal-heading"><span class="draft-badge"><FileWarning :size="15" />{{ t('legal.draft') }}</span><h1>{{ title }}</h1><p>{{ t('legal.frame') }}</p></div>
    <div v-if="document !== 'copyright'" class="legal-frame">
      <aside><a href="#overview">01 · Overview</a><a href="#data">02 · Data</a><a href="#rights">03 · Rights</a><a href="#contact">04 · Contact</a></aside>
      <article>
        <section id="overview"><span>01</span><h2>Overview / 概述</h2><p>{{ t('legal.frame') }}</p></section>
        <section id="data"><span>02</span><h2>Data & media / 数据与素材</h2><div class="legal-placeholder"></div><div class="legal-placeholder short"></div></section>
        <section id="rights"><span>03</span><h2>User rights / 用户权利</h2><div class="legal-placeholder"></div><div class="legal-placeholder"></div></section>
        <section id="contact"><span>04</span><h2>Operator contact / 运营主体</h2><p>TO BE COMPLETED BEFORE PUBLIC LAUNCH</p></section>
      </article>
    </div>
    <form v-else class="copyright-form" @submit.prevent="complain">
      <p>{{ t('legal.copyrightIntro') }}</p>
      <label>{{ t('legal.email') }}<input v-model="email" type="email" required /></label>
      <label>{{ t('support.subject') }}<input v-model="subject" required minlength="3" /></label>
      <label>{{ t('support.content') }}<textarea v-model="content" required minlength="20" rows="8"></textarea></label>
      <button class="primary-button" type="submit">{{ t('support.send') }}<Send :size="16" /></button>
      <p v-if="done" class="success-text">✓ Submitted</p>
    </form>
  </section>
</template>
