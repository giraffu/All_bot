<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { MessageCircle, Send } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api'
import type { Task, Ticket } from '@/types'

const { t } = useI18n()
const tickets = ref<Ticket[]>([])
const tasks = ref<Task[]>([])
const subject = ref('')
const content = ref('')
const taskId = ref('')
const sent = ref(false)

async function load() {
  ;[tickets.value, tasks.value] = await Promise.all([api<Ticket[]>('/tickets'), api<Task[]>('/tasks')])
}
async function submit() {
  await api('/tickets', { method: 'POST', body: JSON.stringify({ subject: subject.value, content: content.value, task_id: taskId.value || null }) })
  subject.value = ''; content.value = ''; taskId.value = ''; sent.value = true
  await load()
}
onMounted(load)
</script>

<template>
  <section class="app-page narrow-page">
    <div class="app-heading"><div><span class="section-index">SUPPORT</span><h1>{{ t('support.title') }}</h1><p>{{ t('support.subtitle') }}</p></div></div>
    <div class="support-grid">
      <form class="panel-card" @submit.prevent="submit">
        <MessageCircle :size="25" />
        <label>{{ t('support.subject') }}<input v-model="subject" required minlength="3" /></label>
        <label>{{ t('support.task') }}<select v-model="taskId"><option value="">—</option><option v-for="task in tasks" :key="task.id" :value="task.id">{{ task.id.slice(0, 8) }} · {{ t(`workspace.types.${task.task_type}`) }}</option></select></label>
        <label>{{ t('support.content') }}<textarea v-model="content" required minlength="10" rows="6"></textarea></label>
        <button class="primary-button full" type="submit">{{ t('support.send') }}<Send :size="16" /></button>
        <p v-if="sent" class="success-text">✓</p>
      </form>
      <div class="panel-card">
        <h2>{{ t('support.history') }}</h2>
        <article v-for="ticket in tickets" :key="ticket.id" class="ticket-row">
          <span class="status-pill" :class="ticket.status">{{ ticket.status }}</span><h3>{{ ticket.subject }}</h3><p>{{ ticket.content }}</p><blockquote v-if="ticket.admin_reply">{{ ticket.admin_reply }}</blockquote>
        </article>
        <div v-if="!tickets.length" class="empty-state">{{ t('common.none') }}</div>
      </div>
    </div>
  </section>
</template>
